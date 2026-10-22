from sqlalchemy import select

from app import create_app
from app.extensions import db
from app.models import AdminUser
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD


def test_login_page_renders(client):
    response = client.get("/admin/login")
    assert response.status_code == 200
    assert b"Sign in" in response.data


def test_valid_login_redirects_to_dashboard(client):
    response = client.post("/admin/login", data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/dashboard")
    assert client.get("/admin/dashboard").status_code == 200


def test_login_is_case_insensitive_on_email(client):
    response = client.post("/admin/login", data={"email": ADMIN_EMAIL.upper(), "password": ADMIN_PASSWORD})
    assert response.status_code == 302


def test_invalid_password_is_rejected(client):
    response = client.post("/admin/login", data={"email": ADMIN_EMAIL, "password": "wrong-password-123"})
    assert response.status_code == 200
    assert b"Invalid email or password" in response.data
    assert client.get("/admin/dashboard").status_code == 302


def test_unknown_email_gets_same_message(client):
    response = client.post("/admin/login", data={"email": "nobody@example.com", "password": "whatever-123456"})
    assert b"Invalid email or password" in response.data


def test_inactive_admin_cannot_sign_in(app, client):
    with app.app_context():
        user = db.session.scalar(select(AdminUser))
        user.active = False
        db.session.commit()
    response = client.post("/admin/login", data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert response.status_code == 200
    assert client.get("/admin/dashboard").status_code == 302


def test_logout_requires_post_and_ends_session(admin_client):
    assert admin_client.get("/admin/logout").status_code == 405
    response = admin_client.post("/admin/logout")
    assert response.status_code == 302
    assert admin_client.get("/admin/dashboard").status_code == 302


def test_protected_pages_redirect_to_login(client):
    for url in ("/admin/", "/admin/dashboard", "/admin/projects", "/admin/inquiries", "/admin/media/hero",
                "/admin/settings", "/admin/projects/1/progress", "/admin/media/1/file"):
        response = client.get(url)
        assert response.status_code == 302, url
        assert "/admin/login" in response.headers["Location"]


def test_login_next_parameter_cannot_redirect_offsite(client):
    response = client.post("/admin/login?next=https://evil.example/phish",
                           data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert response.headers["Location"].endswith("/admin/dashboard")
    response = client.post("/admin/logout")
    response = client.post("/admin/login?next=//evil.example",
                           data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert "evil" not in response.headers["Location"]


def test_password_is_hashed(app):
    with app.app_context():
        user = db.session.scalar(select(AdminUser))
        assert user.password_hash != ADMIN_PASSWORD
        assert user.password_hash.startswith(("scrypt:", "pbkdf2:"))
        assert user.check_password(ADMIN_PASSWORD)
        assert not user.check_password("wrong")


def test_short_passwords_are_refused(app):
    with app.app_context():
        user = AdminUser(email="x@example.com", name="X")
        try:
            user.set_password("short")
        except ValueError:
            pass
        else:
            raise AssertionError("short password accepted")


def test_password_change_invalidates_existing_sessions(app, admin_client):
    other = app.test_client()
    other.post("/admin/login", data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert other.get("/admin/dashboard").status_code == 200
    response = admin_client.post("/admin/account", data={
        "current_password": ADMIN_PASSWORD, "new_password": "a-brand-new-password", "confirm_password": "a-brand-new-password",
    })
    assert response.status_code == 302
    assert admin_client.get("/admin/dashboard").status_code == 200  # current session kept
    assert other.get("/admin/dashboard").status_code == 302          # other session signed out


def test_login_rate_limiting(tmp_path):
    app = create_app("testing", {
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'rl.db'}",
        "LOCAL_MEDIA_ROOT": str(tmp_path / "m"),
        "RATELIMIT_ENABLED": True,
        "LOGIN_RATE_LIMIT": "3 per minute",
    })
    with app.app_context():
        db.create_all()
    client = app.test_client()
    codes = [client.post("/admin/login", data={"email": "a@b.com", "password": "nope-nope-nope"}).status_code
             for _ in range(5)]
    assert codes[:3] == [200, 200, 200]
    assert codes[-1] == 429


def test_create_admin_cli(app):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["create-admin", "--email", "new@example.com", "--name", "New Admin",
                                 "--password", "long-enough-password"])
    assert result.exit_code == 0, result.output
    with app.app_context():
        assert db.session.scalar(select(AdminUser).where(AdminUser.email == "new@example.com"))
    duplicate = runner.invoke(args=["create-admin", "--email", "new@example.com", "--name", "Again",
                                    "--password", "long-enough-password"])
    assert duplicate.exit_code != 0
