"""Single place that decides what the public may see."""
from sqlalchemy import or_, select

from app.models import ContentPost, ProgressUpdate, PublicationStatus
from app.models.base import utcnow


def is_published(column):
    return column == PublicationStatus.PUBLISHED


def public_select(model):
    """SELECT restricted to published rows (and, for posts, a publication date not in the future)."""
    stmt = select(model).where(is_published(model.publication_status))
    if model is ContentPost:
        stmt = stmt.where(or_(ContentPost.published_at.is_(None), ContentPost.published_at <= utcnow()))
    return stmt


def set_status(obj, status):
    """Change publication status. Returns the new PublicationStatus."""
    status = PublicationStatus(status)
    obj.publication_status = status
    if status == PublicationStatus.PUBLISHED and getattr(obj, "published_at", None) is None:
        obj.published_at = utcnow()
    return status


def update_is_public(update):
    """A progress update is public only when it, its phase and its project are all public."""
    phase = update.phase
    return (
        update.publication_status == PublicationStatus.PUBLISHED
        and phase is not None
        and not phase.is_archived
        and phase.project.publication_status == PublicationStatus.PUBLISHED
    )


__all__ = ["public_select", "set_status", "update_is_public", "is_published", "ProgressUpdate"]
