"""Validated status values. Stored as short strings (VARCHAR) in the database."""
from enum import StrEnum

_LABELS = {
    "on_hold": "On Hold",
    "in_progress": "In Progress",
    "in_review": "In Review",
    "csr": "Corporate Social Responsibility",
    "project_announcement": "Project Announcement",
}


class _Labelled(StrEnum):
    @property
    def label(self):
        return _LABELS.get(self.value) or self.value.replace("_", " ").title()

    @classmethod
    def choices(cls, exclude=()):
        return [(m.value, m.label) for m in cls if m not in exclude]


class PublicationStatus(_Labelled):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ProjectStatus(_Labelled):
    UPCOMING = "upcoming"
    ONGOING = "ongoing"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"


class PhaseStatus(_Labelled):
    UPCOMING = "upcoming"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class MediaKind(_Labelled):
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"


class PostKind(_Labelled):
    NEWS = "news"
    EVENT = "event"
    PROJECT_ANNOUNCEMENT = "project_announcement"
    MILESTONE = "milestone"
    CSR = "csr"
    ANNOUNCEMENT = "announcement"


class InquiryKind(_Labelled):
    CONTACT = "contact"
    QUOTE = "quote"


class InquiryStatus(_Labelled):
    NEW = "new"
    IN_REVIEW = "in_review"
    CONTACTED = "contacted"
    CLOSED = "closed"
