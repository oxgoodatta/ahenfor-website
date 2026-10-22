from app.extensions import db
from app.models.base import PublishableMixin, TimestampMixin, enum_type, utcnow
from app.models.enums import PostKind


class ContentPost(TimestampMixin, PublishableMixin, db.Model):
    """News items and events share one table; ``kind`` distinguishes them.

    An item is an *event* when it has ``starts_at``. Whether an event is past
    or upcoming is computed from ``coalesce(ends_at, starts_at)`` at query time,
    so it can never go stale and past events are never deleted.
    """

    __tablename__ = "content_posts"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), nullable=False, unique=True, index=True)
    kind = db.Column(enum_type(PostKind), nullable=False, default=PostKind.NEWS, index=True)
    summary = db.Column(db.String(400), nullable=False)
    body = db.Column(db.Text, nullable=False, default="")
    cover_image_id = db.Column(db.Integer, db.ForeignKey("media_assets.id", ondelete="RESTRICT"))
    video_id = db.Column(db.Integer, db.ForeignKey("media_assets.id", ondelete="RESTRICT"))
    starts_at = db.Column(db.DateTime, index=True)
    ends_at = db.Column(db.DateTime)
    venue = db.Column(db.String(200))
    registration_url = db.Column(db.String(500))
    is_sample = db.Column(db.Boolean, nullable=False, default=False)

    cover_image = db.relationship("MediaAsset", foreign_keys=[cover_image_id])
    video = db.relationship("MediaAsset", foreign_keys=[video_id])

    @property
    def is_event(self):
        return self.starts_at is not None

    @property
    def effective_end(self):
        return self.ends_at or self.starts_at

    @property
    def is_past(self):
        end = self.effective_end
        return end is not None and end < utcnow()

    @property
    def is_upcoming(self):
        return self.is_event and not self.is_past
