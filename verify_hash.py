from werkzeug.security import generate_password_hash, check_password_hash

password = "admin123"
hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
print(f"Hashed Password: {hashed_password}")

is_correct = check_password_hash(hashed_password, password)
print(f"Password Check: {is_correct}")
