import MySQLdb
from werkzeug.security import generate_password_hash
from db import mysql

def create_admin(username, nama, password):
    cursor = mysql.connection.cursor()
    hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
    print("Hashed Password:", hashed_password)
    cursor.execute("INSERT INTO admin (username, nama, password) VALUES (%s, %s, %s)", (username, nama, hashed_password))
    mysql.connection.commit()
    cursor.close()

def get_admin_by_username(username):
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT * FROM admin WHERE username = %s", [username])
    admin = cursor.fetchone()
    cursor.close()
    return admin

def create_report(hari, tanggal, waktu, total_deteksi, image_path, mysql):
    try:
        image_path = image_path.replace("\\", "/")  # Ensure the path uses forward slashes
        cursor = mysql.cursor()
        query = "INSERT INTO report (hari, tanggal, waktu, total_deteksi, image_path) VALUES (%s, %s, %s, %s, %s)"
        cursor.execute(query, (hari, tanggal, waktu, total_deteksi, image_path))
        mysql.commit()
        cursor.close()
        print(f"Report created: {hari}, {tanggal}, {waktu}, {total_deteksi}, {image_path}")
    except Exception as e:
        print(f"Error creating report: {e}")