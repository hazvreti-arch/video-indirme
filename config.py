import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / 'instance'
INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR = Path(os.getenv('VIDORA_DOWNLOAD_DIR', '/tmp/vidora'))
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv('DATABASE_URL', f'sqlite:///{INSTANCE_DIR / "vidora.db"}')
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql+psycopg2://', 1)
elif DATABASE_URL.startswith('postgresql://'):
    DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+psycopg2://', 1)

SECRET_KEY = os.getenv('VIDORA_SECRET_KEY', 'change-this-secret-in-production')
ADMIN_EMAIL = os.getenv('VIDORA_ADMIN_EMAIL', 'admin@vidora.local').strip().lower()
ADMIN_PASSWORD = os.getenv('VIDORA_ADMIN_PASSWORD', 'change-me-now')
REDIS_URL = os.getenv('REDIS_URL', '').strip()
PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', '').rstrip('/')
JOB_RETENTION_HOURS = int(os.getenv('JOB_RETENTION_HOURS', '2'))
MAX_BATCH_ITEMS = int(os.getenv('MAX_BATCH_ITEMS', '50'))
RATE_LIMIT_PER_MINUTE = int(os.getenv('RATE_LIMIT_PER_MINUTE', '20'))
