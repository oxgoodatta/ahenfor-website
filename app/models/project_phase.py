from app.extensions import db
from app.models.base import TimestampMixin, enum_type
from app.models.enums import PhaseStatus

DEFAULT_PHASES = [
    "Planning and Site Preparation",
    "Excavation and Foundation",
    "Structural Works",
    "Roofing and Enclosure",
    "Electrical and Plumbing",
    "Finishing",
    "Inspection and Handover",
]


class ProjectPhase(TimestampMixin, db.Model):
    __tablename__ = "project_phases"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    status = db.Column(enum_type(PhaseStatus), nullable=False, default=PhaseStatus.UPCOMING)
    position = db.Column(db.Integer, nullable=False, default=0)
    start_date = db.Column(db.Date)
    completed_date = db.Column(db.Date)
    is_archived = db.Column(db.Boolean, nullable=False, default=False)

    project = db.relationship("Project", back_populates="phases")
    updates = db.relationship(
        "ProgressUpdate",
        back_populates="phase",
        order_by="(ProgressUpdate.update_date, ProgressUpdate.id)",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<ProjectPhase {self.project_id}:{self.position} {self.title}>"
