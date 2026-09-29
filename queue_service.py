from concurrent.futures import ThreadPoolExecutor
import threading
from models import db, Job, History

_executor = ThreadPoolExecutor(max_workers=3)
_pause_flags = set()
_pause_lock = threading.Lock()

def pause(job_id):
    with _pause_lock: _pause_flags.add(job_id)

def resume(job_id):
    with _pause_lock: _pause_flags.discard(job_id)

def is_paused(job_id):
    with _pause_lock: return job_id in _pause_flags

def submit(app, job_id, fn, options):
    _executor.submit(_run, app, job_id, fn, options)

def _run(app, job_id, fn, options):
    with app.app_context():
        job = db.session.get(Job, job_id)
        if not job: return
        job.status = 'downloading'; db.session.commit()
    try:
        with app.app_context():
            def update(**kwargs):
                j = db.session.get(Job, job_id)
                if not j: return
                for k,v in kwargs.items():
                    if hasattr(j,k): setattr(j,k,v)
                db.session.commit()
            result = fn(db.session.get(Job, job_id), options, update)
            job = db.session.get(Job, job_id)
            job.status = 'ready'; job.progress = 100
            if result: job.filename = str(result)
            db.session.add(History(user_id=job.user_id, job_id=job.id, url=job.url, title=job.title, kind=job.kind, quality=options.get('quality',''), format=options.get('container',''), filename=job.filename))
            db.session.commit()
    except Exception as exc:
        with app.app_context():
            job = db.session.get(Job, job_id)
            if job:
                job.status='error'; job.error=str(exc)[:800]; db.session.commit()
