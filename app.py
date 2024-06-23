import MySQLdb
import cv2
import numpy as np
from flask import Flask, Response, render_template, redirect, url_for, flash, request, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from flask_socketio import SocketIO, emit
from datetime import datetime
from api import detect_objects
import base64
import os
import hashlib
import threading
import math
import logging
from dateutil.parser import isoparse
from config import Config, get_db_connection

logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)
app.secret_key = 'bd8c592b8fc3bd94861eda0932c8d7c2'

# Membuat koneksi ke database
mysql = get_db_connection()
if mysql is None:
    raise Exception("Database connection failed")

image_save_dir = os.path.join("static", "images")
os.makedirs(image_save_dir, exist_ok=True)
current_detected_people = 0

login_manager = LoginManager(app)
login_manager.login_view = 'auth'

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
        mysql.ping(True)  # This will reconnect if the connection is lost
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
            pred['bbox'] = {'x': pred['x'], 'y': pred['y'], 'width': pred['width'], 'height': pred['height']}
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
@login_required
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

@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('video_stream')
def handle_video_stream(data):
    global current_detected_people
    header, encoded = data.split(",", 1)
    img_data = base64.b64decode(encoded)
    nparr = np.frombuffer(img_data, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    predictions = detect_objects(frame)
    detected_people = sum(1 for pred in predictions['predictions'] if pred['class'] == 'pengunjung')
    current_detected_people = detected_people
    emit('detected_people', {'detected_people': detected_people})

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
    if current_detected_people > 0:
        print(current_detected_people)
    return jsonify({'detected_people': current_detected_people})

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)