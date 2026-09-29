# Optional worker entrypoint. Web requests currently use the same thread-pool queue,
# while this file exists so Redis/RQ/Celery can be introduced without changing the repo layout.
from app import app

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
