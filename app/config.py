import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
INSTANCE_DIR = BASE_DIR / 'instance'
INSTANCE_DIR.mkdir(exist_ok=True)


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'tcc-dev-secret-key-change-in-production')
    WTF_CSRF_SECRET_KEY = os.environ.get('WTF_CSRF_SECRET_KEY', SECRET_KEY)
    DATABASE = str(INSTANCE_DIR / 'tcc.db')
    FERNET_KEY_PATH = str(INSTANCE_DIR / 'tcc.key')
    UPLOAD_FOLDER = str(BASE_DIR / 'uploads')
    RECEIPTS_FOLDER = str(INSTANCE_DIR / 'receipts')
    BACKUPS_FOLDER = str(INSTANCE_DIR / 'backups')
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20 MB
    PORT = 5003
    ALLOWED_EXTENSIONS = {
        'pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png',
        'txt', 'xlsx', 'csv', 'xls',
    }
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 28800  # 8 hours
