"""Template globals used only by admin templates."""
from flask import current_app
from sqlalchemy import func, select

from app.admin import bp
from app.extensions import db
from app.models import Inquiry, InquiryStatus, MediaAsset
from app.services.media_service import PROFILE_HINTS, accept_attr


@bp.app_template_global()
def media_asset(asset_id):
    """Look up a MediaAsset for a media form slot (hidden id value)."""
    try:
        asset_id = int(asset_id)
    except (TypeError, ValueError):
        return None
    asset = db.session.get(MediaAsset, asset_id)
    return asset if asset is not None and not asset.is_private else None


@bp.app_template_global()
def accept_for(profile):
    return accept_attr(profile)


@bp.app_template_global()
def limits_for(profile):
    cfg = current_app.config
    limit = {"image": cfg["MAX_IMAGE_BYTES"], "video": cfg["MAX_VIDEO_BYTES"]}.get(profile, cfg["MAX_DOCUMENT_BYTES"])
    return f"{PROFILE_HINTS[profile]}, up to {limit // (1024 * 1024)} MB."


@bp.app_template_global()
def new_inquiry_count():
    return db.session.scalar(select(func.count(Inquiry.id)).where(Inquiry.status == InquiryStatus.NEW)) or 0
