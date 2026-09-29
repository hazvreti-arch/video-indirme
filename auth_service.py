from functools import wraps
from flask import session, jsonify
from models import db, User, Ban

def current_user():
    uid=session.get('user_id'); return db.session.get(User, uid) if uid else None

def login_user(user): session.clear(); session['user_id']=user.id

def logout_user(): session.clear()

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        u=current_user()
        if not u or u.disabled: return jsonify({'error':'Giriş yapman gerekiyor.'}),401
        return fn(*args, **kwargs)
    return wrapped

def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        u=current_user()
        if not u or u.disabled or u.role!='admin': return jsonify({'error':'Yetkisiz.'}),403
        return fn(*args, **kwargs)
    return wrapped

def is_banned(ip): return db.session.query(Ban.id).filter_by(ip=ip).first() is not None
