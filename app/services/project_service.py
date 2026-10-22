"""Project, phase and progress-update business logic."""
from dataclasses import dataclass, field

from sqlalchemy import case, func, select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models import (
    DEFAULT_PHASES,
    ContentPost,
    Inquiry,
    InquiryStatus,
    MediaAsset,
    PhaseStatus,
    ProgressUpdate,
    ProgressUpdateMedia,
    Project,
    ProjectPhase,
    ProjectStatus,
    PublicationStatus,
)
from app.models.base import utcnow
from app.services.publishing_service import public_select

STATUS_ORDER = case(
    (Project.status == ProjectStatus.ONGOING, 0),
    (Project.status == ProjectStatus.UPCOMING, 1),
    (Project.status == ProjectStatus.ON_HOLD, 2),
    (Project.status == ProjectStatus.COMPLETED, 3),
    else_=4,
)

_card_options = (selectinload(Project.cover_image),)


# ---------------------------------------------------------------------------
# Public queries
# ---------------------------------------------------------------------------

def public_projects_stmt(status=None, category=None):
    stmt = public_select(Project).options(*_card_options)
    if status:
        stmt = stmt.where(Project.status == ProjectStatus(status))
    if category:
        stmt = stmt.where(Project.category == category)
    return stmt.order_by(STATUS_ORDER, Project.updated_at.desc(), Project.id.desc())


def public_project_by_slug(slug):
    return db.session.scalar(
        public_select(Project).where(Project.slug == slug).options(
            selectinload(Project.cover_image), selectinload(Project.cover_video)
        )
    )


def featured_projects(limit=3):
    """Featured projects in their configured order, topped up with recent published work."""
    chosen = list(db.session.scalars(
        public_select(Project).where(Project.is_featured.is_(True)).options(*_card_options)
        .order_by(Project.featured_order, Project.updated_at.desc()).limit(limit)
    ))
    if len(chosen) < limit:
        exclude = [p.id for p in chosen] or [0]
        chosen += list(db.session.scalars(
            public_select(Project).where(Project.id.notin_(exclude)).options(*_card_options)
            .order_by(STATUS_ORDER, Project.updated_at.desc()).limit(limit - len(chosen))
        ))
    return chosen


def projects_by_status(status, limit=3):
    return list(db.session.scalars(
        public_select(Project).where(Project.status == status).options(*_card_options)
        .order_by(Project.start_date.asc().nulls_last(), Project.updated_at.desc()).limit(limit)
    ))


def related_projects(project, limit=3):
    return list(db.session.scalars(
        public_select(Project).where(Project.id != project.id, Project.category == project.category)
        .options(*_card_options).order_by(Project.updated_at.desc()).limit(limit)
    ))


@dataclass
class PhaseView:
    phase: ProjectPhase
    updates: list = field(default_factory=list)

    @property
    def photo_count(self):
        return sum(len(u.media_items) for u in self.updates)


def timeline(project, include_drafts=False):
    """Ordered phases with their visible updates (oldest first within each phase).

    Public pages pass include_drafts=False. Admin previews pass True to also see
    drafts; archived updates and phases are never shown.
    """
    phases = db.session.scalars(
        select(ProjectPhase)
        .where(ProjectPhase.project_id == project.id, ProjectPhase.is_archived.is_(False))
        .order_by(ProjectPhase.position, ProjectPhase.id)
        .options(
            selectinload(ProjectPhase.updates)
            .selectinload(ProgressUpdate.media_items)
            .selectinload(ProgressUpdateMedia.media),
            selectinload(ProjectPhase.updates).selectinload(ProgressUpdate.video),
        )
    ).all()
    allowed = {PublicationStatus.PUBLISHED}
    if include_drafts:
        allowed.add(PublicationStatus.DRAFT)
    views = []
    for phase in phases:
        updates = [u for u in phase.updates if u.publication_status in allowed]
        updates.sort(key=lambda u: (u.update_date, u.id))
        views.append(PhaseView(phase, updates))
    return views


def latest_update(views):
    updates = [u for v in views for u in v.updates]
    return max(updates, key=lambda u: (u.update_date, u.id)) if updates else None


def gallery(views, limit=None):
    items = [m for v in views for u in sorted(v.updates, key=lambda u: (u.update_date, u.id), reverse=True)
             for m in u.media_items]
    return items[:limit] if limit else items


# ---------------------------------------------------------------------------
# Phase management
# ---------------------------------------------------------------------------

def _renumber(phases):
    for index, phase in enumerate(phases):
        phase.position = index


def ordered_phases(project):
    return sorted(project.phases, key=lambda p: (p.position, p.id))


def next_phase_position(project):
    return max((p.position for p in project.phases), default=-1) + 1


def add_default_phases(project):
    existing = {p.title.strip().lower() for p in project.phases}
    position = next_phase_position(project)
    added = 0
    for title in DEFAULT_PHASES:
        if title.lower() in existing:
            continue
        project.phases.append(ProjectPhase(title=title, position=position, status=PhaseStatus.UPCOMING))
        position += 1
        added += 1
    return added


def move_phase(phase, direction):
    """Move a phase up (-1) or down (+1) among the project's active phases."""
    project = phase.project
    phases = ordered_phases(project)
    _renumber(phases)
    active = [p for p in phases if not p.is_archived]
    index = active.index(phase)
    target = index + direction
    if target < 0 or target >= len(active):
        return False
    other = active[target]
    phase.position, other.position = other.position, phase.position
    return True


def reorder_phases(project, ordered_ids):
    """Apply an explicit order. ordered_ids must be exactly the project's active phase ids."""
    active = {p.id: p for p in project.phases if not p.is_archived}
    if sorted(ordered_ids) != sorted(active):
        raise ValueError("The phase list does not match this project.")
    archived = [p for p in ordered_phases(project) if p.is_archived]
    _renumber([active[i] for i in ordered_ids] + archived)


# ---------------------------------------------------------------------------
# Progress update media
# ---------------------------------------------------------------------------

def apply_update_media(update, entries):
    """Replace the update's gallery with ``entries`` = [(asset, caption, alt_text), ...].

    Existing links are reused (so their ids stay stable); links not present are
    removed. Removing a link never deletes the underlying file.
    """
    existing = {item.media_id: item for item in update.media_items}
    seen = set()
    new_items = []
    for position, (asset, caption, alt_text) in enumerate(entries):
        if asset.id in seen:
            continue
        seen.add(asset.id)
        item = existing.get(asset.id) or ProgressUpdateMedia(media=asset)
        item.position = position
        item.caption = (caption or "").strip()[:300]
        item.alt_text = (alt_text or "").strip()[:255]
        new_items.append(item)
    update.media_items = new_items


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def dashboard_stats():
    counts = dict(db.session.execute(
        select(Project.status, func.count(Project.id))
        .where(Project.publication_status != PublicationStatus.ARCHIVED)
        .group_by(Project.status)
    ).all())
    now = utcnow()
    upcoming_events = db.session.scalar(
        select(func.count(ContentPost.id)).where(
            ContentPost.publication_status == PublicationStatus.PUBLISHED,
            ContentPost.starts_at.isnot(None),
            func.coalesce(ContentPost.ends_at, ContentPost.starts_at) >= now,
        )
    )
    return {
        "ongoing": counts.get(ProjectStatus.ONGOING, 0),
        "upcoming": counts.get(ProjectStatus.UPCOMING, 0),
        "completed": counts.get(ProjectStatus.COMPLETED, 0),
        "on_hold": counts.get(ProjectStatus.ON_HOLD, 0),
        "draft_projects": db.session.scalar(
            select(func.count(Project.id)).where(Project.publication_status == PublicationStatus.DRAFT)
        ),
        "upcoming_events": upcoming_events,
        "new_inquiries": db.session.scalar(
            select(func.count(Inquiry.id)).where(Inquiry.status == InquiryStatus.NEW)
        ),
        "recent_updates": db.session.scalars(
            select(ProgressUpdate).options(
                selectinload(ProgressUpdate.phase).selectinload(ProjectPhase.project),
                selectinload(ProgressUpdate.media_items),
            ).order_by(ProgressUpdate.created_at.desc()).limit(6)
        ).all(),
        "recent_uploads": db.session.scalars(
            select(MediaAsset).where(MediaAsset.is_private.is_(False))
            .order_by(MediaAsset.created_at.desc()).limit(8)
        ).all(),
        "recent_inquiries": db.session.scalars(
            select(Inquiry).order_by(Inquiry.created_at.desc()).limit(5)
        ).all(),
    }
