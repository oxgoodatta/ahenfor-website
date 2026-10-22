from flask import current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy import func, select
from werkzeug.security import check_password_hash, generate_password_hash

from app.admin import bp
from app.admin.forms import ConfirmForm, LoginForm
from app.extensions import db, limiter
from app.models import AdminUser
from app.models.base import utcnow
from app.utils.helpers import is_safe_redirect

# Used to keep response time similar whether or not the email exists.
_DUMMY_HASH = generate_password_hash("not-a-real-password-for-timing")


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit(lambda: current_app.config["LOGIN_RATE_LIMIT"], methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = db.session.scalar(select(AdminUser).where(func.lower(AdminUser.email) == email))
        if user is None:
            check_password_hash(_DUMMY_HASH, form.password.data)
        if user is not None and user.is_active and user.check_password(form.password.data):
            next_url = request.args.get("next")
            session.clear()
            login_user(user, remember=False)
            session.permanent = True
            user.last_login_at = utcnow()
            db.session.commit()
            if is_safe_redirect(next_url) and next_url.startswith("/admin"):
                return redirect(next_url)
            return redirect(url_for("admin.dashboard"))
        current_app.logger.warning("Failed admin login for %s from %s", email[:80], request.remote_addr)
        flash("Invalid email or password.", "error")
    return render_template("admin/login.html", form=form)


@bp.route("/logout", methods=["POST"])
def logout():
    ConfirmForm().validate_on_submit()  # CSRF is enforced globally; this keeps the pattern explicit
    logout_user()
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("admin.login"))
