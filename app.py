import MySQLdb
import cv2
import numpy as np
from flask import Flask, Response, current_app, render_template, redirect, url_for, flash, request, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from db import app
from models import create_admin, get_admin_by_username, create_report
from camera import VideoCamera
from api import detect_objects
from pathlib import Path
import base64
from io import BytesIO
from PIL import Image
import os
import time
import hashlib
import threading
import math
import logging
from dateutil.parser import isoparse
from config import Config, get_db_connection

logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.secret_key = 'bd8c592b8fc3bd94861eda0932c8d7c2'

# Membuat koneksi ke database
mysql = get_db_connection()
if mysql is None:
    raise Exception("Database connection failed")

image_save_dir = os.path.join("static", "images")
os.makedirs(image_save_dir, exist_ok=True)
current_detected_people = 0
last_saved_detected_people = 0

login_manager = LoginManager(app)
login_manager.login_view = 'auth'

# variabel global buat simpan path gambar terakhir pendeteksian
last_detected_image_path = None

class Admin(UserMixin):
    def __init__(self, id, username, nama):
        self.id = id
        self.username = username
        self.nama = nama

    def is_active(self):
        return True

    def is_authenticated(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

@login_manager.user_loader
def load_user(user_id):
    try:
        cursor = mysql.cursor()
        cursor.execute("SELECT * FROM admin WHERE id = %s", [user_id])
        admin = cursor.fetchone()
        cursor.close()
        if admin:
            return Admin(id=admin[0], username=admin[1], nama=admin[2])
    except MySQLdb._exceptions.OperationalError as e:
        print(f"Error loading user: {e}")
        mysql.ping(True)
        cursor = mysql.cursor()
        cursor.execute("SELECT * FROM admin WHERE id = %s", [user_id])
        admin = cursor.fetchone()
        cursor.close()
        if admin:
            return Admin(id=admin[0], username=admin[1], nama=admin[2])
    return None

def get_admin_by_username(username):
    cursor = mysql.cursor()
    cursor.execute("SELECT * FROM admin WHERE username = %s", [username])
    admin = cursor.fetchone()
    cursor.close()
    return admin

# Daftar global untuk menyimpan objek yang terdeteksi dan waktu deteksinya
detected_objects = {}

def generate_unique_id(prediction):
    try:
        if 'bbox' in prediction:
            bbox = prediction['bbox']
            id_str = f"{bbox['x']}{bbox['y']}{bbox['width']}{bbox['height']}"
        else:
            id_str = f"{prediction['x']}{prediction['y']}{prediction['width']}{prediction['height']}"
        return hashlib.md5(id_str.encode()).hexdigest()
    except KeyError as e:
        print(f"Missing key in prediction: {e}, prediction: {prediction}")
        return None

def clean_old_detections(max_age_seconds=10):
    current_time = datetime.now()
    to_delete = []
    for obj_id, detection in detected_objects.items():
        detection_time = detection['time'].replace(tzinfo=None)
        if (current_time - detection_time).total_seconds() > max_age_seconds:
            to_delete.append(obj_id)
    for obj_id in to_delete:
        del detected_objects[obj_id]

def get_week_number(date_str):
    date = datetime.strptime(date_str, '%Y-%m-%d').date()
    year, week_num, weekday = date.isocalendar()
    return week_num

def is_same_object(pred, threshold=50, time_threshold=5):
    current_time = datetime.now()
    for obj_id, detection in detected_objects.items():
        old_pred = detection['prediction']
        if 'bbox' not in pred or 'bbox' not in old_pred:
            print(f"Missing 'bbox' in prediction or old prediction. Prediction: {pred}, Old Prediction: {old_pred}")
            continue
        time_diff = (current_time - detection['time']).total_seconds()
        distance = math.sqrt((pred['bbox']['x'] - old_pred['bbox']['x'])**2 + (pred['bbox']['y'] - old_pred['bbox']['y'])**2)
        x1_max = max(pred['bbox']['x'] - pred['bbox']['width'] / 2, old_pred['bbox']['x'] - old_pred['bbox']['width'] / 2)
        y1_max = max(pred['bbox']['y'] - pred['bbox']['height'] / 2, old_pred['bbox']['y'] - old_pred['bbox']['height'] / 2)
        x2_min = min(pred['bbox']['x'] + pred['bbox']['width'] / 2, old_pred['bbox']['x'] + old_pred['bbox']['width'] / 2)
        y2_min = min(pred['bbox']['y'] + pred['bbox']['height'] / 2, old_pred['bbox']['y'] + old_pred['bbox']['height'] / 2)
        overlap_width = max(0, x2_min - x1_max)
        overlap_height = max(0, y2_min - y1_max)
        overlap_area = overlap_width * overlap_height
        area1 = pred['bbox']['width'] * pred['bbox']['height']
        area2 = old_pred['bbox']['width'] * old_pred['bbox']['height']
        total_area = area1 + area2 - overlap_area
        overlap_ratio = overlap_area / total_area
        if distance < threshold and overlap_ratio > 0.5 and time_diff < time_threshold:
            print(f"Same object found: {obj_id}")
            return obj_id
    return None

def save_detection_to_db(predictions, mysql, frame):
    now = datetime.now()
    hari = now.strftime("%A")
    tanggal = now.date()
    waktu = now.time()

    clean_old_detections()
    detected_ids = set()
    total_deteksi = 0

    for pred in predictions:
        print(f"Processing prediction: {pred}")
        if 'bbox' not in pred:
            print(f"Prediction missing 'bbox': {pred}")
            pred['bbox'] = {
                'x': pred['x'],
                'y': pred['y'],
                'width': pred['width'],
                'height': pred['height']
            }

        bbox = pred['bbox']
        obj_id = is_same_object(pred)
        if obj_id is None:
            unique_id = generate_unique_id(pred)
            if unique_id:
                detected_objects[unique_id] = {'time': now, 'prediction': bbox, 'crossed_line': False}
                detected_ids.add(unique_id)
                total_deteksi += 1
                print(f"Deteksi berhasil dimasukkan ke database: {detected_objects[unique_id]}")
        else:
            detected_objects[obj_id]['time'] = now

    if total_deteksi > 0:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_filename = f"{timestamp}.jpg"
        image_path = os.path.join(image_save_dir, image_filename)
        image_path = image_path.replace("\\", "/")

        if isinstance(frame, np.ndarray):
            cv2.imwrite(image_path, frame)
            print(f"Image saved at: {image_path}")
        else:
            print("Frame is not a valid numpy array.")
            return

        create_report(hari, tanggal, waktu, total_deteksi, image_path, mysql)
        print(f"Total deteksi disimpan ke database: {total_deteksi}")
    else:
        print("Tidak ada deteksi baru yang perlu disimpan.")

def detect_and_save(frame, detection_line_position):
    predictions = detect_objects(frame)
    if predictions is not None:
        now = datetime.now()
        hari = now.strftime("%A")
        tanggal = now.date()
        waktu = now.time()

        clean_old_detections()
        detected_ids = set()

        for pred in predictions['predictions']:
            bbox = pred.get('bbox', pred)
            obj_id = is_same_object(bbox)
            if obj_id is None:
                unique_id = generate_unique_id(pred)
                if unique_id:
                    detected_objects[unique_id] = {'time': now, 'prediction': bbox, 'crossed_line': False}
                    detected_ids.add(unique_id)
                    total_deteksi = 1
                    create_report(hari, tanggal, waktu, total_deteksi, mysql)
                    print(f"Deteksi berhasil disimpan: {detected_objects[unique_id]}")
            else:
                detected_objects[obj_id]['time'] = now

            if bbox['y'] > detection_line_position and not detected_objects[unique_id]['crossed_line']:
                detected_objects[unique_id]['crossed_line'] = True

        save_last_detected_frame(frame)
        save_detection_to_db(predictions['predictions'], mysql)

@app.route('/save_last_detection', methods=['POST'])
@login_required
def save_last_detection():
    data = request.get_json()
    image_data = data['image']

    image_data = image_data.split(",")[1]
    image_bytes = base64.b64decode(image_data)
    last_frame_path = os.path.join(current_app.root_path, 'static', 'detections', 'last_detection.jpg')

    with open(last_frame_path, "wb") as f:
        f.write(image_bytes)

    return jsonify({"status": "success"})

@app.route('/delete_report/<int:report_id>', methods=['POST'])
def delete_report(report_id):
    try:
        cursor = mysql.cursor()
        cursor.execute("DELETE FROM report WHERE id = %s", (report_id,))
        mysql.commit()
        cursor.close()
        flash('Laporan berhasil dihapus', 'success')
    except Exception as e:
        flash('Terjadi kesalahan saat menghapus laporan', 'danger')
        print(f"Error: {e}")

    return redirect(url_for('dashboard'))

@app.route('/update_detected_people', methods=['POST'])
@login_required
def update_detected_people():
    global current_detected_people
    data = request.get_json()
    predictions = data['predictions']
    timestamp = data['timestamp']

    now = isoparse(timestamp)
    detected_people = 0

    clean_old_detections()

    for pred in predictions:
        if 'bbox' not in pred:
            print(f"Prediction missing 'bbox': {pred}")
            continue
        bbox = pred['bbox']
        if pred['class'] == 'pengunjung':
            obj_id = is_same_object(pred)
            if obj_id is None:
                unique_id = generate_unique_id(pred)
                if unique_id:
                    detected_objects[unique_id] = {'time': now, 'prediction': bbox, 'crossed_line': False}
                    detected_people += 1
            else:
                detected_objects[obj_id]['time'] = now

    current_detected_people = detected_people

    return jsonify({'status': 'success', 'detected_people': detected_people})

@login_required
def start_detection():
    camera = VideoCamera()
    frame, image = camera.get_frame()

    image_pil = Image.fromarray(image)
    image_pil.save("temp.jpg")

    result_image_base64, predictions = detect_objects("temp.jpg")

    os.remove("temp.jpg")

    now = datetime.now()
    hari = now.strftime("%A")
    tanggal = now.date()
    waktu = now.time()

    clean_old_detections()

    detected_ids = set()

    for pred in predictions:
        obj_id = is_same_object(pred)
        if obj_id is None:
            unique_id = generate_unique_id(pred)
            detected_objects[unique_id] = {'time': now, 'prediction': pred, 'crossed_line': False}
            detected_ids.add(unique_id)
            total_deteksi = 1
            create_report(hari, tanggal, waktu, total_deteksi, mysql)
        else:
            detected_objects[obj_id]['time'] = now

def generate_frames():
    last_detected_people = 0
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    frame_skip = 5
    frame_count = 0

    detection_line_position = int(480 / 2)

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.resize(frame, (320, 240))
        frame_count += 1

        cv2.line(frame, (0, detection_line_position), (320, detection_line_position), (0, 255, 255), 2)
        detections = detect_objects(frame)
        detected_people = sum(1 for detection in detections['predictions'] if detection['class'] == 'pengunjung')
        global current_detected_people
        current_detected_people = detected_people

        if detections is not None:
            for pred in detections['predictions']:
                x1 = int(pred['x'] - pred['width'] / 2)
                y1 = int(pred['y'] - pred['height'] / 2)
                x2 = int(pred['x'] + pred['width'] / 2)
                y2 = int(pred['y'] + pred['height'] / 2)
                class_name = pred['class']
                confidence = pred['confidence']
                unique_id = generate_unique_id(pred)

                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, f"{class_name} ({confidence:.2f}) ID: {unique_id}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 0), 1)
            if detected_people != last_detected_people:
                last_detected_people = detected_people
                if frame_count % frame_skip == 0 and detected_people != last_saved_detected_people:
                    if detected_people != 0:
                        frame_copy = frame.copy()
                        threading.Thread(target=save_detection_to_db, args=(detections['predictions'], mysql, frame_copy)).start()

        ret, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

    cap.release()

def save_last_detected_frame(frame):
    with app.app_context():
        last_frame_path = os.path.join(current_app.root_path, 'static', 'detections', 'last_detection.jpg')
        cv2.imwrite(last_frame_path, frame)

@app.route('/auth', methods=['GET', 'POST'])
def auth():
    action = request.args.get('action')
    if action == 'register' and request.method == 'POST':
        username = request.form.get('username')
        nama = request.form.get('nama')
        password = request.form.get('password')

        try:
            mysql.ping(True)
            cursor = mysql.cursor()
            cursor.execute("SELECT * FROM admin WHERE username = %s", [username])
            existing_admin = cursor.fetchone()

            if existing_admin:
                flash('Username sudah tersedia. Tolong gunakan username lain.', 'danger')
                return render_template('auth.html', action='register')

            hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
            cursor.execute("INSERT INTO admin (username, nama, password) VALUES (%s, %s, %s)", (username, nama, hashed_password))
            mysql.commit()
            cursor.close()

            flash('Pendaftaran berhasil! Kamu bisa masuk sekarang.', 'success')
            return redirect(url_for('auth', action='login'))

        except MySQLdb._exceptions.OperationalError as e:
            print(f"An error occurred: {e}")
            mysql.ping(True)
            flash('Duh, terdapat kesalahan, nih. Coba lagi ya.', 'danger')
            return render_template('auth.html', action='register')

    if action == 'login' and request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        print(f"Username: {username}")
        print(f"Password: {password}")

        try:
            mysql.ping(True)
            admin = get_admin_by_username(username)

            if admin:
                print(f"Admin Found: {admin[1]}")
                print(f"Stored Hashed Password: {admin[3]}")
                password_check = check_password_hash(admin[3], password)
                print(f"Password Check: {password_check}")
                if password_check:
                    print("Password is correct")
                    login_user(Admin(id=admin[0], username=admin[1], nama=admin[2]))
                    print("Redirecting to dashboard...")
                    return redirect(url_for('dashboard'))
                else:
                    print("Hm, sepertinya password kamu salah!")
            else:
                print("User tidak ditemukan, nih..")

            flash('Kredensial salah', 'danger')
            print("Kredensial salah")
            return render_template('auth.html', action='login')
        except MySQLdb._exceptions.OperationalError as e:
            print(f"An error occurred: {e}")
            mysql.ping(True)
            flash('Duh, terdapat kesalahan, nih. Coba lagi ya.', 'danger')
            return render_template('auth.html', action='login')

    return render_template('auth.html', action=action)

def register(username, nama, password):
    try:
        cursor = mysql.cursor()
        cursor.execute("SELECT * FROM admin WHERE username = %s", [username])
        existing_admin = cursor.fetchone()

        if existing_admin:
            flash('Username sudah tersedia. Tolong gunakan username lain.', 'danger')
            return

        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        cursor.execute("INSERT INTO admin (username, nama, password) VALUES (%s, %s, %s)", (username, nama, hashed_password))
        mysql.commit()
        cursor.close()

        flash('Pendaftaran berhasil! Kamu bisa masuk sekarang.', 'success')
    except Exception as e:
        print(f"An error occurred: {e}")
        flash('Duh, terdapat kesalahan, nih. Coba lagi ya.', 'danger')

def login(username, password):
    admin = get_admin_by_username(username)

    if admin:
        if check_password_hash(admin[3], password):
            login_user(Admin(id=admin[0], username=admin[1], nama=admin[2]))
            return redirect(url_for('dashboard'))

    flash('Invalid credentials', 'danger')

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    else:
        return redirect(url_for('auth', action='login'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth', action='login'))

@app.route('/dashboard')
@login_required
def dashboard():
    try:
        today = datetime.today().date()
        cursor = mysql.cursor()
        cursor.execute("SELECT COUNT(*) FROM report WHERE tanggal = %s", [today])
        visits_today = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM report")
        total_deteksi = cursor.fetchone()[0]
        cursor.execute("SELECT AVG(total_deteksi) FROM report")
        rata_rata_pengunjung = cursor.fetchone()[0]
        cursor.execute("SELECT tanggal, SUM(total_deteksi) FROM report GROUP BY tanggal")
        report_data = cursor.fetchall()
        chart_labels = [str(row[0]) for row in report_data]
        chart_data = [row[1] for row in report_data]
        week_report = {}
        for row in report_data:
            week_number = get_week_number(str(row[0]))
            if ("Minggu " + str(week_number) in week_report):
                week_report["Minggu " + str(week_number)] += row[1]
            else:
                week_report["Minggu " + str(week_number)] = row[1]
        week_report = dict(sorted(week_report.items()))
        week_report_labels = list(week_report.keys())
        week_report_data = list(week_report.values())
        cursor.execute("SELECT * FROM report ORDER BY tanggal DESC, waktu DESC")
        reports = cursor.fetchall()
        cursor.close()
        return render_template('dashboard.html',
                               visits_today=visits_today,
                               total_deteksi=total_deteksi,
                               rata_rata_pengunjung=rata_rata_pengunjung,
                               chart_labels=chart_labels,
                               chart_data=chart_data,
                               week_report_labels=week_report_labels,
                               week_report_data=week_report_data,
                               reports=reports)
    except Exception as e:
        logging.error(f"Error in dashboard: {e}")
        return "Terjadi kesalahan pada server", 500

@app.route('/detect')
@login_required
def detect():
    try:
        return render_template('detect.html')
    except MySQLdb._exceptions.OperationalError as e:
        print(f"Error rendering detect.html: {e}")
        mysql.ping(True)
        return render_template('detect.html')
    except Exception as e:
        logging.error(f"Error rendering detect.html: {e}")
        return "Terjadi kesalahan pada server", 500

@app.route('/detected_people')
def detected_people():
    global current_detected_people
    if(current_detected_people > 0):
        print(current_detected_people)
    return jsonify({'detected_people': current_detected_people})

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    app.run(debug=True)