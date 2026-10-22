"""WSGI entry point.

Development:  flask --app run.py run
Production:   gunicorn "run:app" --workers 3 --bind 127.0.0.1:8000
"""
from app import create_app

app = create_app()

if __name__ == "__main__":  # pragma: no cover
    app.run()
