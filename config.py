import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    #SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'instance', 'dsa_reminder.db')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL').replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAIL_SERVER = 'in-v3.mailjet.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.getenv('AWS_SES_SMTP_USERNAME')
    MAIL_PASSWORD = os.getenv('AWS_SES_SMTP_PASSWORD')
    MAIL_DEFAULT_SENDER = os.getenv('SENDER_EMAIL')
    TIMEZONE = 'Asia/Kolkata'  # IST timezone
    LOG_LEVEL = 'INFO'
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,  # 5 minutes
        "pool_size": 5,
        "max_overflow": 10,
        "connect_args": {
            "connect_timeout": 10,
            "sslmode": "require"  # Explicit SSL
        }
    }
