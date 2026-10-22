from app.extensions import db
from app.models.base import TimestampMixin, enum_type
from app.models.enums import InquiryKind, InquiryStatus


class Inquiry(TimestampMixin, db.Model):
    """Private contact and quote requests. Never exposed through public routes."""

    __tablename__ = "inquiries"

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(enum_type(InquiryKind), nullable=False, index=True)
    status = db.Column(enum_type(InquiryStatus), nullable=False, default=InquiryStatus.NEW, index=True)
    full_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(40))
    organization = db.Column(db.String(200))
    subject = db.Column(db.String(200))
    project_location = db.Column(db.String(200))
    service = db.Column(db.String(150))
    message = db.Column(db.Text, nullable=False)
    budget_range = db.Column(db.String(60))
    timeline = db.Column(db.String(60))
    attachment_id = db.Column(db.Integer, db.ForeignKey("media_assets.id", ondelete="RESTRICT"))
    internal_notes = db.Column(db.Text, nullable=False, default="")
    notified_at = db.Column(db.DateTime)

    attachment = db.relationship("MediaAsset")
