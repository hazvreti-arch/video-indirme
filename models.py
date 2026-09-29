from datetime import datetime, timezone
import secrets
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash


db = SQLAlchemy()


def utcnow():
    return datetime.now(timezone.utc)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user')
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    disabled = db.Column(db.Boolean, default=False)

    def set_password(self, value):
        self.password_hash = generate_password_hash(value)

    def check_password(self, value):
        return check_password_hash(self.password_hash, value)


class Job(db.Model):
    id = db.Column(db.String(32), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    ip = db.Column(db.String(80), nullable=True, index=True)
    url = db.Column(db.Text, nullable=False)
    kind = db.Column(db.String(30), default='download')
    status = db.Column(db.String(30), default='queued', index=True)
    progress = db.Column(db.Integer, default=0)
    title = db.Column(db.String(600), default='Video')
    platform = db.Column(db.String(100), default='Video')
    filename = db.Column(db.Text, nullable=True)
    error = db.Column(db.Text, nullable=True)
    bytes_done = db.Column(db.Integer, default=0)
    bytes_total = db.Column(db.Integer, default=0)
    speed = db.Column(db.String(50), default='')
    eta = db.Column(db.String(50), default='')
    meta_json = db.Column(db.Text, default='{}')
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class History(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    job_id = db.Column(db.String(32), nullable=True)
    url = db.Column(db.Text, nullable=False)
    title = db.Column(db.String(600), default='Video')
    kind = db.Column(db.String(30), default='download')
    quality = db.Column(db.String(30), default='')
    format = db.Column(db.String(30), default='')
    filename = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, index=True)


class Profile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    settings_json = db.Column(db.Text, nullable=False, default='{}')
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)


class APIKey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    prefix = db.Column(db.String(20), nullable=False, index=True)
    key_hash = db.Column(db.String(255), nullable=False, unique=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    revoked = db.Column(db.Boolean, default=False)
    last_used_at = db.Column(db.DateTime(timezone=True), nullable=True)

    @staticmethod
    def create_raw():
        return 'vk_live_' + secrets.token_urlsafe(28)


class Ban(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip = db.Column(db.String(80), nullable=False, unique=True, index=True)
    reason = db.Column(db.String(255), default='')
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)


class ShareLink(db.Model):
    id = db.Column(db.String(48), primary_key=True)
    job_id = db.Column(db.String(32), nullable=False, index=True)
    token_hash = db.Column(db.String(255), nullable=False, unique=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    max_downloads = db.Column(db.Integer, default=10)
    downloads = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
