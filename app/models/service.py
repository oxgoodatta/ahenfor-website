from app.extensions import db
from app.models.base import PublishableMixin, TimestampMixin


class Service(TimestampMixin, PublishableMixin, db.Model):
    __tablename__ = "services"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    slug = db.Column(db.String(170), nullable=False, unique=True, index=True)
    short_description = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    image_id = db.Column(db.Integer, db.ForeignKey("media_assets.id", ondelete="RESTRICT"))
    position = db.Column(db.Integer, nullable=False, default=0)
    is_sample = db.Column(db.Boolean, nullable=False, default=False)

    image = db.relationship("MediaAsset")
