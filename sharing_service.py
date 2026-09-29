import hashlib, secrets
from datetime import timedelta
from models import ShareLink, utcnow

def create_share(job_id, hours=1, max_downloads=10):
    raw=secrets.token_urlsafe(30)
    row=ShareLink(id=secrets.token_urlsafe(10), job_id=job_id, token_hash=hashlib.sha256(raw.encode()).hexdigest(), expires_at=utcnow()+timedelta(hours=hours), max_downloads=max_downloads)
    return row, raw

def hash_token(token): return hashlib.sha256(token.encode()).hexdigest()
