"""Workflow F: CSRF, authorization, private data, draft exposure, XSS, headers."""
import io

from sqlalchemy import select

from app import create_app
from app.config import ConfigurationError, ProductionConfig
from app.extensions import db
from app.models import Inquiry, Project, PublicationStatus, Testimonial
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, image_file, make_project, project_form


def test_csrf_required_when_enabled(app, client):
    app.config["WTF_CSRF_ENABLED"] = True
    # Login without a token is rejected
    response = client.post("/admin/login", data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert response.status_code == 400
    # Public forms are protected too
    assert client.post("/contact", data={"full_name": "x"}).status_code == 400


def test_csrf_token_flow_and_ajax_header(app, client):
    app.config["WTF_CSRF_ENABLED"] = True
    page = client.get("/admin/login").data.decode()
    token = page.split('name="csrf_token" type="hidden" value="')[1].split('"')[0]
    response = client.post("/admin/login", data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "csrf_token": token})
    assert response.status_code == 302
    dash = client.get("/admin/dashboard").data.decode()
    meta = dash.split('name="csrf-token" content="')[1].split('"')[0]
    no_header = client.post("/admin/media/upload", data={"file": image_file(), "profile": "image"},
                            content_type="multipart/form-data", headers={"X-Requested-With": "fetch"})
    assert no_header.status_code == 400
    ok = client.post("/admin/media/upload", data={"file": image_file(), "profile": "image"},
                     content_type="multipart/form-data", headers={"X-Requested-With": "fetch", "X-CSRFToken": meta})
    assert ok.status_code == 201


def test_anonymous_users_cannot_modify_content(app, client):
    pid = make_project(app, published=False)
    attempts = [
        ("/admin/projects/new", project_form()),
        (f"/admin/projects/{pid}/edit", project_form(name="Hacked")),
        (f"/admin/status/project/{pid}", {"status": "published"}),
        ("/admin/media/upload", {"file": image_file(), "profile": "image"}),
        ("/admin/media/hero/publish", {}),
        ("/admin/settings?group=contact", {"contact_phone": "000"}),
    ]
    for url, data in attempts:
        response = client.post(url, data=data, content_type="multipart/form-data")
        assert response.status_code in (302, 401), url
    with app.app_context():
        project = db.session.get(Project, pid)
        assert project.name == "Test Project" and project.publication_status == PublicationStatus.DRAFT


def test_ajax_requests_get_json_401(client):
    response = client.post("/admin/media/upload", headers={"X-Requested-With": "fetch"})
    assert response.status_code == 401 and response.get_json()["ok"] is False


def test_status_change_rejects_bad_values(app, admin_client):
    pid = make_project(app)
    assert admin_client.post(f"/admin/status/project/{pid}", data={"status": "nonsense"}).status_code == 400
    assert admin_client.post(f"/admin/status/user/{pid}", data={"status": "published"}).status_code == 404
    assert admin_client.post("/admin/status/project/99999", data={"status": "published"}).status_code == 404
    assert admin_client.get(f"/admin/status/project/{pid}").status_code == 405


def test_invalid_identifiers(admin_client, client):
    assert admin_client.get("/admin/projects/abc/edit").status_code == 404
    assert admin_client.get("/admin/projects/999999/progress").status_code == 404
    assert admin_client.get("/admin/updates/999999/edit").status_code == 404
    assert client.get("/projects/%3Cscript%3E").status_code == 404
    assert client.get("/projects?status=<script>&page=-5").status_code == 200


def test_draft_content_not_exposed(app, client):
    make_project(app, name="Draft Only", published=False)
    for url in ("/", "/projects", "/projects?status=ongoing", "/sitemap.xml"):
        assert b"Draft Only" not in client.get(url).data and b"draft-only" not in client.get(url).data
    assert client.get("/projects/draft-only").status_code == 404
    # Admin preview routes need authentication
    with app.app_context():
        pid = db.session.scalar(select(Project.id))
    assert client.get(f"/admin/projects/{pid}/preview").status_code == 302


def test_unapproved_testimonials_cannot_be_published(app, admin_client, client):
    r = admin_client.post("/admin/testimonials/new", data={
        "client_name": "Kofi Boateng", "quote": "Great work", "project_id": "0", "publication_status": "published"})
    assert r.status_code == 200 and b"after the client has approved" in r.data
    admin_client.post("/admin/testimonials/new", data={
        "client_name": "Kofi Boateng", "quote": "Great work", "project_id": "0", "publication_status": "draft"})
    with app.app_context():
        tid = db.session.scalar(select(Testimonial.id))
    admin_client.post(f"/admin/status/testimonial/{tid}", data={"status": "published"})
    assert b"Kofi Boateng" not in client.get("/").data


def test_inquiries_are_private(app, client, admin_client):
    client.post("/request-quote", data={
        "full_name": "Ama Owusu", "email": "ama@example.com", "phone": "+233 24 123 4567",
        "project_location": "Kasoa", "service": "Other / not sure", "timeline": "Within 3 months",
        "message": "We need a two-storey office block on a 70x100 plot.",
        "attachment": (io.BytesIO(b"%PDF-1.5 confidential drawings"), "drawings.pdf"),
    }, content_type="multipart/form-data")
    with app.app_context():
        inquiry = db.session.scalar(select(Inquiry))
        attachment = inquiry.attachment
        assert attachment.is_private and attachment.storage_key.startswith("private/")
        key, aid, iid = attachment.storage_key, attachment.id, inquiry.id

    anon = app.test_client()
    assert anon.get(f"/media/{key}").status_code == 404
    assert anon.get(f"/admin/media/{aid}/file").status_code == 302
    assert anon.get(f"/admin/inquiries/{iid}").status_code == 302
    for url in ("/", "/sitemap.xml", "/projects"):
        assert b"Ama Owusu" not in anon.get(url).data
    # Private assets are not offered in the media library or picker
    assert b"drawings.pdf" not in admin_client.get("/admin/media").data
    assert admin_client.get(f"/admin/media/{aid}").status_code == 404
    download = admin_client.get(f"/admin/media/{aid}/file")
    assert download.status_code == 200 and download.data.startswith(b"%PDF")
    assert "no-store" in download.headers["Cache-Control"]


def test_user_content_is_escaped(app, admin_client, client):
    payload = '<script>alert("x")</script>'
    admin_client.post("/admin/projects/new", data=project_form(
        name="XSS Test", description=payload, short_description=payload, publication_status="published"))
    html = client.get("/projects/xss-test").data.decode()
    assert payload not in html and "&lt;script&gt;" in html


def test_security_headers(client, admin_client):
    public = client.get("/")
    assert public.headers["X-Content-Type-Options"] == "nosniff"
    assert public.headers["X-Frame-Options"] == "DENY"
    assert "script-src 'self'" in public.headers["Content-Security-Policy"]
    admin = admin_client.get("/admin/dashboard")
    assert "no-store" in admin.headers["Cache-Control"]
    assert "noindex" in admin.headers["X-Robots-Tag"]


def test_robots_blocks_admin(client):
    assert b"Disallow: /admin/" in client.get("/robots.txt").data


def test_production_config_refuses_unsafe_settings():
    class Unsafe(ProductionConfig):
        SECRET_KEY = "short"
        SQLALCHEMY_DATABASE_URI = "sqlite:///x.db"
        MEDIA_STORAGE_PROVIDER = "local"
        ALLOW_LOCAL_MEDIA_IN_PRODUCTION = False

    from flask import Flask

    probe = Flask("probe")
    probe.config.from_object(Unsafe)
    try:
        Unsafe.validate(probe)
    except ConfigurationError as exc:
        message = str(exc)
        assert "SECRET_KEY" in message and "PostgreSQL" in message and "MEDIA_STORAGE_PROVIDER" in message
    else:
        raise AssertionError("unsafe production configuration accepted")


def test_production_config_accepts_complete_settings():
    from flask import Flask

    class Complete(ProductionConfig):
        SECRET_KEY = "x" * 48
        SQLALCHEMY_DATABASE_URI = "postgresql+psycopg://u:p@db/ahenfor"
        MEDIA_STORAGE_PROVIDER = "s3"
        AWS_S3_BUCKET = "ahenfor-media"
        MAIL_BACKEND = "smtp"
        MAIL_SERVER = "smtp.example.com"

    probe = Flask("probe")
    probe.config.from_object(Complete)
    Complete.validate(probe)  # does not raise
    assert probe.config["SESSION_COOKIE_SECURE"] is True


def test_unknown_config_name_is_rejected():
    try:
        create_app("staging-typo")
    except RuntimeError as exc:
        assert "Unknown FLASK_CONFIG" in str(exc)
    else:
        raise AssertionError("unknown config accepted")
