from flask import current_app, flash, redirect, request, url_for
from flask_login import current_user

from app.extensions import db
from app.models import MediaKind
from app.services.media_service import resolve_media_field
from app.utils.helpers import is_safe_redirect, unique_slug


def redirect_back(default_endpoint, **values):
    target = request.form.get("next") or request.args.get("next")
    if is_safe_redirect(target):
        return redirect(target)
    return redirect(url_for(default_endpoint, **values))


def paginate(stmt, per_page=None):
    return db.paginate(
        stmt,
        page=request.args.get("page", 1, type=int) or 1,
        per_page=per_page or current_app.config["ADMIN_PER_PAGE"],
        error_out=False,
    )


def media_slot(batch, form, base, kind, profile=None, alt_text=""):
    """Resolve ``<base>_file`` / ``<base>_id`` form fields to a MediaAsset or None."""
    return resolve_media_field(
        batch,
        getattr(form, f"{base}_file").data,
        getattr(form, f"{base}_id").data,
        kind,
        profile=profile,
        user=current_user,
        alt_text=alt_text,
    )


def preload_media_slot(form, base, asset):
    """Fill the hidden id field on GET so the current media shows in the form."""
    field = getattr(form, f"{base}_id")
    if not field.data and asset is not None:
        field.data = str(asset.id)


def slug_for(model, form_slug, fallback, exclude_id=None):
    value = (form_slug or "").strip() or fallback
    return unique_slug(model, value, exclude_id=exclude_id)


def flash_saved(noun, obj):
    state = "published" if getattr(obj, "is_published", False) else "saved as a draft"
    flash(f"{noun} {state}.", "success")


IMAGE, VIDEO, DOCUMENT = MediaKind.IMAGE, MediaKind.VIDEO, MediaKind.DOCUMENT
