import secrets

class Config:
    SECRET_KEY = secrets.token_hex(16)
    MYSQL_HOST = 'localhost'
    MYSQL_USER = 'root'
    MYSQL_PASSWORD = ''
    MYSQL_DB = 'db_perpustakaan'
    
    
    
print(secrets.token_hex(16))



