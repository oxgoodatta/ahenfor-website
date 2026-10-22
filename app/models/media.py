from app.extensions import db
from app.models.base import enum_type, utcnow
from app.models.enums import MediaKind


class MediaAsset(db.Model):
    """Metadata for a file held in the configured storage backend.

    Binary content never lives in the database. Records referenced elsewhere are
    protected by RESTRICT/SET NULL foreign keys and by media_service.references().
    """

    __tablename__ = "media_assets"

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(enum_type(MediaKind), nullable=False, index=True)
    storage_provider = db.Column(db.String(20), nullable=False)
    storage_key = db.Column(db.String(255), nullable=False, unique=True)
    thumb_key = db.Column(db.String(255), unique=True)
    mime_type = db.Column(db.String(120), nullable=False)
    size_bytes = db.Column(db.BigInteger, nullable=False)
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    duration_seconds = db.Column(db.Float)
    original_filename = db.Column(db.String(255))
    alt_text = db.Column(db.String(255), nullable=False, default="")
    caption = db.Column(db.String(300), nullable=False, default="")
    is_private = db.Column(db.Boolean, nullable=False, default=False)
    is_archived = db.Column(db.Boolean, nullable=False, default=False, index=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("admin_users.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    uploaded_by = db.relationship("AdminUser")

    @property
    def is_image(self):
        return self.kind == MediaKind.IMAGE

    @property
    def is_video(self):
        return self.kind == MediaKind.VIDEO

    @property
    def is_document(self):
        return self.kind == MediaKind.DOCUMENT

    @property
    def url(self):
        """Public URL. Private assets are only reachable through admin routes."""
        if self.is_private:
            return None
        from app.storage import get_storage

        return get_storage().url(self.storage_key)

    @property
    def thumb_url(self):
        if self.is_private:
            return None
        from app.storage import get_storage

        return get_storage().url(self.thumb_key or self.storage_key)

    @property
    def display_name(self):
        return self.original_filename or f"{self.kind.label} #{self.id}"

    @property
    def size_label(self):
        size = float(self.size_bytes or 0)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return ""

    def to_dict(self):
        return {
            "id": self.id,
            "kind": self.kind.value,
            "url": self.url,
            "thumb_url": self.thumb_url,
            "mime_type": self.mime_type,
            "width": self.width,
            "height": self.height,
            "alt_text": self.alt_text,
            "caption": self.caption,
            "name": self.display_name,
            "size": self.size_label,
        }
