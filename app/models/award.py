from app.extensions import db
from app.models.base import PublishableMixin, TimestampMixin


class Award(TimestampMixin, PublishableMixin, db.Model):
    """Awards, certifications and professional registrations (verified records only)."""

    __tablename__ = "awards"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    issuer = db.Column(db.String(200), nullable=False)
    year = db.Column(db.Integer)
    description = db.Column(db.Text, nullable=False, default="")
    image_id = db.Column(db.Integer, db.ForeignKey("media_assets.id", ondelete="RESTRICT"))
    document_id = db.Column(db.Integer, db.ForeignKey("media_assets.id", ondelete="RESTRICT"))
    position = db.Column(db.Integer, nullable=False, default=0)

    image = db.relationship("MediaAsset", foreign_keys=[image_id])
    document = db.relationship("MediaAsset", foreign_keys=[document_id])
