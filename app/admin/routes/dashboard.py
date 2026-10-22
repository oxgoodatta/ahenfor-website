from flask import redirect, render_template, url_for

from app.admin import bp
from app.services import project_service, settings_service


@bp.route("/")
def index():
    return redirect(url_for("admin.dashboard"))


@bp.route("/dashboard")
def dashboard():
    return render_template(
        "admin/dashboard.html",
        stats=project_service.dashboard_stats(),
        hero_pending=settings_service.hero_has_unpublished_changes(),
    )
