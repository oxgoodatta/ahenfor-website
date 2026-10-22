from flask import Blueprint

from app.admin.decorators import require_admin

bp = Blueprint("admin", __name__)
bp.before_request(require_admin)

from app.admin import template_helpers  # noqa: E402,F401
from app.admin.routes import (  # noqa: E402,F401
    auth,
    content,
    dashboard,
    inquiries,
    media,
    progress,
    projects,
    settings,
)
