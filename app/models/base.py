"""Shared column helpers and mixins."""
from datetime import datetime, timezone

from app.extensions import db
from app.models.enums import PublicationStatus


def utcnow():
    """Naive UTC timestamp (all datetimes are stored in UTC; Ghana is UTC+0)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def enum_type(enum_cls):
    """String-backed enum column type that validates values in Python."""
    return db.Enum(
        enum_cls,
        native_enum=False,
        length=24,
        validate_strings=True,
        values_callable=lambda e: [m.value for m in e],
        create_constraint=False,
    )


class TimestampMixin:
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class PublishableMixin:
    """Publication workflow, deliberately separate from any lifecycle status."""

    publication_status = db.Column(
        enum_type(PublicationStatus), nullable=False, default=PublicationStatus.DRAFT, index=True
    )
    published_at = db.Column(db.DateTime, nullable=True)

    @property
    def is_published(self):
        return self.publication_status == PublicationStatus.PUBLISHED

    @property
    def is_archived_content(self):
        return self.publication_status == PublicationStatus.ARCHIVED
