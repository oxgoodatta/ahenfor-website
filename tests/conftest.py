"""Shared fixtures.

Tests run against a throwaway database: SQLite in a temp folder by default, or
PostgreSQL when TEST_DATABASE_URL is set. Never point TEST_DATABASE_URL at a
database that holds real data - every test drops and recreates all tables.
"""
import io
import os
from datetime import date

import pytest
from PIL import Image

from app import create_app
from app.config import normalise_db_url
from app.extensions import db
from app.models import AdminUser, Project, ProjectPhase, ProjectStatus, PublicationStatus

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def app(tmp_path):
    db_url = normalise_db_url(os.environ.get("TEST_DATABASE_URL")) or f"sqlite:///{tmp_path / 'test.db'}"
    application = create_app("testing", {
        "SQLALCHEMY_DATABASE_URI": db_url,
        "LOCAL_MEDIA_ROOT": str(tmp_path / "media"),
    })
    with application.app_context():
        db.drop_all()
        db.create_all()
        admin = AdminUser(email=ADMIN_EMAIL, name="Test Admin")
        admin.set_password(ADMIN_PASSWORD)
        db.session.add(admin)
        db.session.commit()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_client(client):
    response = client.post("/admin/login", data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert response.status_code == 302, "admin login failed in fixture"
    return client


def image_bytes(fmt="JPEG", size=(640, 480), color=(30, 60, 90)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, fmt)
    buf.seek(0)
    return buf


def image_file(name="photo.jpg", fmt="JPEG", **kw):
    return (image_bytes(fmt, **kw), name)


def make_project(app, name="Test Project", published=True, status=ProjectStatus.ONGOING, phases=0, **kw):
    from app.utils.helpers import unique_slug

    with app.app_context():
        project = Project(
            name=name, slug=unique_slug(Project, name), location="Accra, Greater Accra",
            category="Commercial Buildings", short_description=f"{name} short description",
            status=status,
            publication_status=PublicationStatus.PUBLISHED if published else PublicationStatus.DRAFT,
            **kw,
        )
        db.session.add(project)
        for i in range(phases):
            project.phases.append(ProjectPhase(title=f"Phase {i + 1}", position=i))
        db.session.commit()
        return project.id


def project_form(**overrides):
    data = {
        "name": "Takoradi Commercial Complex",
        "location": "Takoradi, Western Region",
        "category": "Commercial Buildings",
        "short_description": "A four-storey commercial building.",
        "description": "Full description.",
        "status": "upcoming",
        "publication_status": "draft",
        "start_date": "",
        "estimated_completion_date": "",
        "actual_completion_date": "",
        "featured_order": "0",
    }
    data.update(overrides)
    return data


@pytest.fixture
def today():
    return date.today()
