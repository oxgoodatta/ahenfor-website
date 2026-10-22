"""Authorization for the admin blueprint.

Every admin endpoint is protected by ``require_admin`` (registered as a
blueprint-wide before_request hook) so a newly added route cannot be left
public by forgetting a decorator. ``admin_required`` exists for use outside
the blueprint.
"""
from functools import wraps

from flask import jsonify, request
from flask_login import current_user

from app.extensions import login_manager

OPEN_ENDPOINTS = {"admin.login"}


def _wants_json():
    return request.headers.get("X-Requested-With") == "fetch" or request.accept_mimetypes.best == "application/json"


def require_admin():
    if request.endpoint in OPEN_ENDPOINTS:
        return None
    if current_user.is_authenticated and current_user.is_active:
        return None
    if _wants_json():
        return jsonify({"ok": False, "error": "Your session has expired. Please sign in again."}), 401
    return login_manager.unauthorized()


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        denied = require_admin()
        if denied is not None:
            return denied
        return view(*args, **kwargs)

    return wrapped
