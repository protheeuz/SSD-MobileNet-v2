from flask import Flask
from flask_mysqldb import MySQL
import MySQLdb

app = Flask(__name__)
app.config.from_object('config.Config')

mysql = MySQL(app)
