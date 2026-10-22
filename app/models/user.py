import secrets

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, login_manager
from app.models.base import utcnow

MIN_PASSWORD_LENGTH = 12


def _new_session_token():
    return secrets.token_hex(32)


class AdminUser(UserMixin, db.Model):
    __tablename__ = "admin_users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    # Rotated on password change so existing sessions are invalidated.
    session_token = db.Column(db.String(64), nullable=False, unique=True, default=_new_session_token)
    active = db.Column(db.Boolean, nullable=False, default=True)
    last_login_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    @property
    def is_active(self):
        return bool(self.active)

    def get_id(self):
        return self.session_token

    def set_password(self, password):
        if not password or len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
        self.password_hash = generate_password_hash(password)
        self.session_token = _new_session_token()

    def check_password(self, password):
        if not self.password_hash or not password:
            return False
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<AdminUser {self.email}>"


@login_manager.user_loader
def load_user(token):
    if not token or len(token) != 64:
        return None
    user = db.session.execute(
        db.select(AdminUser).where(AdminUser.session_token == token)
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    return user
