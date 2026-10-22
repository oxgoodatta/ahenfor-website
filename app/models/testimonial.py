from app.extensions import db
from app.models.base import PublishableMixin, TimestampMixin


class Testimonial(TimestampMixin, PublishableMixin, db.Model):
    __tablename__ = "testimonials"

    id = db.Column(db.Integer, primary_key=True)
    client_name = db.Column(db.String(150), nullable=False)
    client_role = db.Column(db.String(150))
    organization = db.Column(db.String(200))
    quote = db.Column(db.Text, nullable=False)
    portrait_id = db.Column(db.Integer, db.ForeignKey("media_assets.id", ondelete="RESTRICT"))
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="SET NULL"))
    # Recorded confirmation that the client approved the statement for publication.
    client_approved = db.Column(db.Boolean, nullable=False, default=False)
    position = db.Column(db.Integer, nullable=False, default=0)

    portrait = db.relationship("MediaAsset")
    project = db.relationship("Project")
