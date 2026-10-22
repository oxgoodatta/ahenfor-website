from app.extensions import db
from app.models.base import PublishableMixin, TimestampMixin, enum_type
from app.models.enums import ProjectStatus

# Developer-defined categories (the admin chooses, but cannot invent new ones).
PROJECT_CATEGORIES = [
    "Commercial Buildings",
    "Residential",
    "Institutional",
    "Civil and Structural",
    "Roads and Infrastructure",
    "Industrial",
    "Renovation and Rehabilitation",
    "Other",
]


class Project(TimestampMixin, PublishableMixin, db.Model):
    __tablename__ = "projects"
    __table_args__ = (
        db.CheckConstraint(
            "progress_percent IS NULL OR (progress_percent >= 0 AND progress_percent <= 100)",
            name="progress_range",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), nullable=False, unique=True, index=True)
    reference_code = db.Column(db.String(50), unique=True)
    location = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100), nullable=False, index=True)
    short_description = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")

    cover_image_id = db.Column(db.Integer, db.ForeignKey("media_assets.id", ondelete="RESTRICT"))
    cover_video_id = db.Column(db.Integer, db.ForeignKey("media_assets.id", ondelete="RESTRICT"))

    status = db.Column(enum_type(ProjectStatus), nullable=False, default=ProjectStatus.UPCOMING, index=True)
    start_date = db.Column(db.Date)
    estimated_completion_date = db.Column(db.Date)
    actual_completion_date = db.Column(db.Date)

    client_name = db.Column(db.String(200))
    show_client = db.Column(db.Boolean, nullable=False, default=False)
    project_value = db.Column(db.String(100))
    show_value = db.Column(db.Boolean, nullable=False, default=False)

    # Entered manually by the company. Never derived from uploads.
    progress_percent = db.Column(db.Integer)

    is_featured = db.Column(db.Boolean, nullable=False, default=False, index=True)
    featured_order = db.Column(db.Integer, nullable=False, default=0)
    is_sample = db.Column(db.Boolean, nullable=False, default=False)

    cover_image = db.relationship("MediaAsset", foreign_keys=[cover_image_id])
    cover_video = db.relationship("MediaAsset", foreign_keys=[cover_video_id])
    phases = db.relationship(
        "ProjectPhase",
        back_populates="project",
        order_by="ProjectPhase.position",
        cascade="all, delete-orphan",
    )

    @property
    def active_phases(self):
        return [p for p in self.phases if not p.is_archived]

    def __repr__(self):
        return f"<Project {self.slug}>"
