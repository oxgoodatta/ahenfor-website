from app.extensions import db
from app.models.base import PublishableMixin, TimestampMixin


class ProgressUpdate(TimestampMixin, PublishableMixin, db.Model):
    __tablename__ = "progress_updates"

    id = db.Column(db.Integer, primary_key=True)
    phase_id = db.Column(
        db.Integer, db.ForeignKey("project_phases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = db.Column(db.String(200), nullable=False)
    update_date = db.Column(db.Date, nullable=False, index=True)
    body = db.Column(db.Text, nullable=False, default="")
    video_id = db.Column(db.Integer, db.ForeignKey("media_assets.id", ondelete="RESTRICT"))
    created_by_id = db.Column(db.Integer, db.ForeignKey("admin_users.id", ondelete="SET NULL"))

    phase = db.relationship("ProjectPhase", back_populates="updates")
    video = db.relationship("MediaAsset", foreign_keys=[video_id])
    created_by = db.relationship("AdminUser")
    media_items = db.relationship(
        "ProgressUpdateMedia",
        back_populates="update",
        order_by="ProgressUpdateMedia.position",
        cascade="all, delete-orphan",
    )

    @property
    def project(self):
        return self.phase.project if self.phase else None


class ProgressUpdateMedia(db.Model):
    """Ordered photo gallery for a progress update.

    Caption and alt text live on the link so one photo can be reused with
    different context. Deleting the link never deletes the stored file.
    """

    __tablename__ = "progress_update_media"
    __table_args__ = (db.UniqueConstraint("update_id", "media_id", name="uq_update_media"),)

    id = db.Column(db.Integer, primary_key=True)
    update_id = db.Column(
        db.Integer, db.ForeignKey("progress_updates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    media_id = db.Column(
        db.Integer, db.ForeignKey("media_assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    position = db.Column(db.Integer, nullable=False, default=0)
    caption = db.Column(db.String(300), nullable=False, default="")
    alt_text = db.Column(db.String(255), nullable=False, default="")

    update = db.relationship("ProgressUpdate", back_populates="media_items")
    media = db.relationship("MediaAsset")

    @property
    def effective_alt(self):
        return self.alt_text or self.media.alt_text or self.caption or ""
