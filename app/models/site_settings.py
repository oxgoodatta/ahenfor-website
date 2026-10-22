from app.extensions import db
from app.models.base import utcnow


class SiteSetting(db.Model):
    """Key/value store for editable copy. Keys come from settings_service.REGISTRY."""

    __tablename__ = "site_settings"

    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.Text, nullable=False, default="")
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class HeroConfig(db.Model):
    """Homepage hero. Exactly two rows: ``draft`` (edited) and ``published`` (live).

    Publishing copies the draft row onto the published row in one transaction.
    """

    __tablename__ = "hero_configs"

    id = db.Column(db.Integer, primary_key=True)
    state = db.Column(db.String(12), nullable=False, unique=True)
    media_type = db.Column(db.String(10), nullable=False, default="image")
    image_id = db.Column(db.Integer, db.ForeignKey("media_assets.id", ondelete="RESTRICT"))
    video_id = db.Column(db.Integer, db.ForeignKey("media_assets.id", ondelete="RESTRICT"))
    poster_id = db.Column(db.Integer, db.ForeignKey("media_assets.id", ondelete="RESTRICT"))
    alt_text = db.Column(db.String(255), nullable=False, default="")
    eyebrow = db.Column(db.String(80), nullable=False, default="")
    headline = db.Column(db.String(160), nullable=False, default="")
    subheadline = db.Column(db.String(400), nullable=False, default="")
    primary_label = db.Column(db.String(40), nullable=False, default="")
    primary_target = db.Column(db.String(30), nullable=False, default="projects")
    secondary_label = db.Column(db.String(40), nullable=False, default="")
    secondary_target = db.Column(db.String(30), nullable=False, default="quote")
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("admin_users.id", ondelete="SET NULL"))

    image = db.relationship("MediaAsset", foreign_keys=[image_id])
    video = db.relationship("MediaAsset", foreign_keys=[video_id])
    poster = db.relationship("MediaAsset", foreign_keys=[poster_id])
    updated_by = db.relationship("AdminUser")

    COPY_FIELDS = (
        "media_type", "image_id", "video_id", "poster_id", "alt_text", "eyebrow", "headline",
        "subheadline", "primary_label", "primary_target", "secondary_label", "secondary_target",
    )
