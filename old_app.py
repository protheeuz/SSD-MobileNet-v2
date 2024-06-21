# import MySQLdb
# import cv2
# from flask import Flask, Response, render_template, redirect, url_for, flash, request, jsonify
# from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
# from werkzeug.security import generate_password_hash, check_password_hash
# from datetime import datetime
# from db import app
# from models import create_admin, get_admin_by_username, create_report, get_reports
# from camera import VideoCamera
# from api import detect_objects
# import base64
# from io import BytesIO
# from PIL import Image
# import os
# import time
# import hashlib
# import threading
# import math

# app = Flask(__name__)
# app.secret_key = 'bd8c592b8fc3bd94861eda0932c8d7c2'

# # Konfigurasi database
# app.config['MYSQL_HOST'] = 'localhost'
# app.config['MYSQL_USER'] = 'root'
# app.config['MYSQL_PASSWORD'] = ''
# app.config['MYSQL_DB'] = 'db_perpustakaan'

# # Membuat koneksi ke database
# mysql = MySQLdb.connect(
#     host="localhost",
#     user="root",
#     passwd="",
#     db="db_perpustakaan"
# )

# login_manager = LoginManager(app)
# login_manager.login_view = 'login'

# class Admin(UserMixin):
#     def __init__(self, id, username, nama):
#         self.id = id
#         self.username = username
#         self.nama = nama

#     def is_active(self):
#         return True

#     def is_authenticated(self):
#         return True

#     def is_anonymous(self):
#         return False

#     def get_id(self):
#         return str(self.id)

# @login_manager.user_loader
# def load_user(user_id):
#     cursor = mysql.cursor()
#     cursor.execute("SELECT * FROM admin WHERE id = %s", [user_id])
#     admin = cursor.fetchone()
#     cursor.close()
#     if admin:
#         return Admin(id=admin[0], username=admin[1], nama=admin[2])
#     return None

# def get_admin_by_username(username):
#     cursor = mysql.cursor()
#     cursor.execute("SELECT * FROM admin WHERE username = %s", [username])
#     admin = cursor.fetchone()
#     cursor.close()
#     return admin

# # Daftar global untuk menyimpan objek yang terdeteksi dan waktu deteksinya
# detected_objects = {}

# def generate_unique_id(prediction):
#     id_str = f"{prediction['x']}{prediction['y']}{prediction['width']}{prediction['height']}"
#     return hashlib.md5(id_str.encode()).hexdigest()

# def clean_old_detections(max_age_seconds=10):
#     current_time = datetime.now()
#     to_delete = []
#     for obj_id, detection in detected_objects.items():
#         if (current_time - detection['time']).total_seconds() > max_age_seconds:
#             to_delete.append(obj_id)
#     for obj_id in to_delete:
#         del detected_objects[obj_id]

# def is_same_object(pred, threshold=50, time_threshold=5):
#     current_time = datetime.now()
#     for obj_id, detection in detected_objects.items():
#         old_pred = detection['prediction']
#         time_diff = (current_time - detection['time']).total_seconds()

#         # kalkualasi jarak antara centroid dari bounding box
#         # jika jarak berdekatan, kita anggap sebagai objek yang sama
#         distance = math.sqrt((pred['x'] - old_pred['x'])**2 + (pred['y'] - old_pred['y'])**2)

#         # kalkulasi overlap
#         # rasio overlap untuk pastiin objek yang sama gak terdeteksi 2x
#         x1_max = max(pred['x'] - pred['width'] / 2, old_pred['x'] - old_pred['width'] / 2)
#         y1_max = max(pred['y'] - pred['height'] / 2, old_pred['y'] - old_pred['height'] / 2)
#         x2_min = min(pred['x'] + pred['width'] / 2, old_pred['x'] + old_pred['width'] / 2)
#         y2_min = min(pred['y'] + pred['height'] / 2, old_pred['y'] + old_pred['height'] / 2)

#         overlap_width = max(0, x2_min - x1_max)
#         overlap_height = max(0, y2_min - y1_max)
#         overlap_area = overlap_width * overlap_height

#         area1 = pred['width'] * pred['height']
#         area2 = old_pred['width'] * old_pred['height']
#         total_area = area1 + area2 - overlap_area

#         overlap_ratio = overlap_area / total_area

#         if distance < threshold and overlap_ratio > 0.5 and time_diff < time_threshold:
#             return obj_id
#     return None

# def save_detection_to_db(predictions, mysql):
#     now = datetime.now()
#     hari = now.strftime("%A")
#     tanggal = now.date()
#     waktu = now.time()

#     clean_old_detections()
#     detected_ids = set()

#     for pred in predictions:
#         obj_id = is_same_object(pred)
#         if obj_id is None:
#             unique_id = generate_unique_id(pred)
#             detected_objects[unique_id] = {'time': now, 'prediction': pred}
#             detected_ids.add(unique_id)
#             # Simpan deteksi ke database
#             total_deteksi = 1
#             create_report(hari, tanggal, waktu, total_deteksi, mysql)
#             print(f"Deteksi berhasil dimasukkan ke database: {detected_objects[unique_id]}")
#         else:
#             detected_objects[obj_id]['time'] = now

# @app.route('/auth', methods=['GET', 'POST'])
# def auth():
#     action = request.args.get('action')
#     if action == 'register' and request.method == 'POST':
#         username = request.form.get('username')
#         nama = request.form.get('nama')
#         password = request.form.get('password')

#         try:
#             cursor = mysql.cursor()
#             cursor.execute("SELECT * FROM admin WHERE username = %s", [username])
#             existing_admin = cursor.fetchone()

#             if existing_admin:
#                 flash('Username sudah tersedia. Tolong gunakan username lain.', 'danger')
#                 return render_template('auth.html', action='register')
            
#             hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
#             cursor.execute("INSERT INTO admin (username, nama, password) VALUES (%s, %s, %s)", (username, nama, hashed_password))
#             mysql.commit()
#             cursor.close()

#             flash('Pendaftaran berhasil! Kamu bisa masuk sekarang.', 'success')
#             return redirect(url_for('auth', action='login'))

#         except Exception as e:
#             print(f"An error occurred: {e}")
#             flash('Duh, terdapat kesalahan, nih. Coba lagi ya.', 'danger')
#             return render_template('auth.html', action='register')

#     if action == 'login' and request.method == 'POST':
#         username = request.form.get('username')
#         password = request.form.get('password')
        
#         print(f"Username: {username}")
#         print(f"Password: {password}")

#         admin = get_admin_by_username(username)
        
#         if admin:
#             print(f"Admin Found: {admin[1]}")
#             print(f"Stored Hashed Password: {admin[3]}")
#             password_check = check_password_hash(admin[3], password)
#             print(f"Password Check: {password_check}")
#             if password_check:
#                 print("Password is correct")
#                 login_user(Admin(id=admin[0], username=admin[1], nama=admin[2]))
#                 print("Redirecting to dashboard...")
#                 return redirect(url_for('dashboard'))
#             else:
#                 print("Hm, sepertinya password kamu salah!")
#         else:
#             print("User tidak ditemukan, nih..")

#         flash('Kredensial salah', 'danger')
#         print("Kredensial salah")
#         return render_template('auth.html', action='login')

#     return render_template('auth.html', action=action)


# def register(username, nama, password):
#     try:
#         cursor = mysql.cursor()
#         cursor.execute("SELECT * FROM admin WHERE username = %s", [username])
#         existing_admin = cursor.fetchone()

#         if existing_admin:
#             flash('Username sudah tersedia. Tolong gunakan username lain.', 'danger')
#             return

#         hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
#         cursor.execute("INSERT INTO admin (username, nama, password) VALUES (%s, %s, %s)", (username, nama, hashed_password))
#         mysql.commit()
#         cursor.close()

#         flash('Pendaftaran berhasil! Kamu bisa masuk sekarang.', 'success')
#     except Exception as e:
#         print(f"An error occurred: {e}")
#         flash('Duh, terdapat kesalahan, nih. Coba lagi ya.', 'danger')

# def login(username, password):
#     admin = get_admin_by_username(username)
    
#     if admin:
#         if check_password_hash(admin[3], password):
#             login_user(Admin(id=admin[0], username=admin[1], nama=admin[2]))
#             return redirect(url_for('dashboard'))
    
#     flash('Invalid credentials', 'danger')

# @app.route('/logout')
# @login_required
# def logout():
#     logout_user()
#     return redirect(url_for('auth', action='login'))

# @app.route('/dashboard')
# @login_required
# def dashboard():
#     today = datetime.today().date()
#     cursor = mysql.cursor()

#     # Total deteksi hari ini
#     cursor.execute("SELECT COUNT(*) FROM report WHERE tanggal = %s", [today])
#     visits_today = cursor.fetchone()[0]

#     # Total deteksi keseluruhan
#     cursor.execute("SELECT COUNT(*) FROM report")
#     total_deteksi = cursor.fetchone()[0]

#     # Rata-rata pengunjung
#     cursor.execute("SELECT AVG(total_deteksi) FROM report")
#     rata_rata_pengunjung = cursor.fetchone()[0]

#     # Data untuk grafik
#     cursor.execute("SELECT tanggal, SUM(total_deteksi) FROM report GROUP BY tanggal")
#     report_data = cursor.fetchall()
#     chart_labels = [str(row[0]) for row in report_data]
#     chart_data = [row[1] for row in report_data]

#     # Semua laporan, urutkan berdasarkan tanggal dan waktu terbaru
#     cursor.execute("SELECT * FROM report ORDER BY tanggal DESC, waktu DESC")
#     reports = cursor.fetchall()

#     cursor.close()
#     return render_template('dashboard.html', 
#                            visits_today=visits_today, 
#                            total_deteksi=total_deteksi,
#                            rata_rata_pengunjung=rata_rata_pengunjung, 
#                            chart_labels=chart_labels,
#                            chart_data=chart_data, 
#                            reports=reports)


# @app.route('/detect')
# @login_required
# def detect():
#     return render_template('detect.html')

# @app.route('/start_detection')
# @login_required
# def start_detection():
#     camera = VideoCamera()
#     frame, image = camera.get_frame()

#     image_pil = Image.fromarray(image)
#     image_pil.save("temp.jpg")

#     result_image_base64, predictions = detect_objects("temp.jpg")

#     os.remove("temp.jpg")

#     now = datetime.now()
#     hari = now.strftime("%A")
#     tanggal = now.date()
#     waktu = now.time()

#     clean_old_detections()

#     detected_ids = set()

#     for pred in predictions:
#         obj_id = is_same_object(pred)
#         if obj_id is None:
#             unique_id = generate_unique_id(pred)
#             detected_objects[unique_id] = {'time': now, 'prediction': pred}
#             detected_ids.add(unique_id)
#             # Simpan deteksi ke database
#             total_deteksi = 1
#             create_report(hari, tanggal, waktu, total_deteksi, mysql)
#         else:
#             detected_objects[obj_id]['time'] = now

#     return jsonify({"image": result_image_base64, "detections": len(detected_ids)})

# @app.route('/video_feed')
# def video_feed():
#     return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

# def generate_frames():
#     cap = cv2.VideoCapture(0)
#     cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)  
#     cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480) 
#     frame_skip = 5  
#     frame_count = 0

#     while cap.isOpened():
#         ret, frame = cap.read()
#         if not ret:
#             break

#         # Reduce resolusi untuk performance video
#         frame = cv2.resize(frame, (320, 240))

#         if frame_count % frame_skip == 0:
#             threading.Thread(target=detect_and_save, args=(frame,)).start()

#         frame_count += 1

#         # Menggambar bounding box tiap kali terdeteksi
#         predictions = detect_objects(frame)
#         if predictions is not None:
#             for pred in predictions['predictions']:
#                 x1 = int(pred['x'] - pred['width'] / 2)
#                 y1 = int(pred['y'] - pred['height'] / 2)
#                 x2 = int(pred['x'] + pred['width'] / 2)
#                 y2 = int(pred['y'] + pred['height'] / 2)
#                 class_name = pred['class']
#                 confidence = pred['confidence']
#                 unique_id = generate_unique_id(pred)

#                 cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
#                 cv2.putText(frame, f"{class_name} ({confidence:.2f}) ID: {unique_id}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 0), 1)

#         ret, buffer = cv2.imencode('.jpg', frame)
#         frame_bytes = buffer.tobytes()
#         yield (b'--frame\r\n'
#                b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

#     cap.release()
#     cv2.destroyAllWindows()

# def detect_and_save(frame):
#     predictions = detect_objects(frame)
#     if predictions is not None:
#         save_detection_to_db(predictions['predictions'], mysql)

# if __name__ == '__main__':
#     app.run(debug=True)
