import shutil, time
from pathlib import Path
from config import DOWNLOAD_DIR, JOB_RETENTION_HOURS

def job_dir(job_id):
    p = DOWNLOAD_DIR / job_id
    p.mkdir(parents=True, exist_ok=True)
    return p

def cleanup_files():
    cutoff = time.time() - JOB_RETENTION_HOURS * 3600
    if not DOWNLOAD_DIR.exists():
        return
    for item in DOWNLOAD_DIR.iterdir():
        try:
            if item.stat().st_mtime < cutoff:
                shutil.rmtree(item, ignore_errors=True)
        except OSError:
            pass
