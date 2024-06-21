from werkzeug.security import generate_password_hash, check_password_hash

# Password yang akan di-hash
password = "mathtech123"

# Meng-hash password
hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
print("Hashed Password:", hashed_password)

# Memeriksa hash password
is_correct = check_password_hash(hashed_password, "mathtech123")
print("Password Check:", is_correct)
