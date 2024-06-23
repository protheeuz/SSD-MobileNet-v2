import secrets

class Config:
    SECRET_KEY = secrets.token_hex(16)
    MYSQL_HOST = 'localhost'
    MYSQL_USER = 'wilson'
    MYSQL_PASSWORD = 'db_perpustakaan'
    MYSQL_DB = 'db_perpustakaan'
