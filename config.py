import secrets
import MySQLdb

class Config:
    SECRET_KEY = secrets.token_hex(16)
    MYSQL_HOST = 'localhost'
    MYSQL_USER = 'mathtech'
    MYSQL_PASSWORD = 'db_perpustakaan'
    MYSQL_DB = 'db_perpustakaan'

def get_db_connection():
    try:
        connection = MySQLdb.connect(
            host=Config.MYSQL_HOST,
            user=Config.MYSQL_USER,
            passwd=Config.MYSQL_PASSWORD,
            db=Config.MYSQL_DB
        )
        connection.ping(True)
        return connection
    except MySQLdb._exceptions.OperationalError as e:
        print(f"Error connecting to the database: {e}")
        return None