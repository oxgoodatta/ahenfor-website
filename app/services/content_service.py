"""News, events, services, awards and testimonials queries for public pages."""
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models import Award, ContentPost, Service, Testimonial
from app.models.base import utcnow
from app.services.publishing_service import public_select

_end = func.coalesce(ContentPost.ends_at, ContentPost.starts_at)


def upcoming_events_stmt():
    return (public_select(ContentPost).options(selectinload(ContentPost.cover_image))
            .where(ContentPost.starts_at.isnot(None), _end >= utcnow())
            .order_by(ContentPost.starts_at.asc(), ContentPost.id))


def past_events_stmt():
    return (public_select(ContentPost).options(selectinload(ContentPost.cover_image))
            .where(ContentPost.starts_at.isnot(None), _end < utcnow())
            .order_by(ContentPost.starts_at.desc(), ContentPost.id.desc()))


def news_stmt():
    """Items without event dates, newest first."""
    published_order = func.coalesce(ContentPost.published_at, ContentPost.created_at)
    return (public_select(ContentPost).options(selectinload(ContentPost.cover_image))
            .where(ContentPost.starts_at.is_(None))
            .order_by(published_order.desc(), ContentPost.id.desc()))


def upcoming_events(limit=3):
    return db.session.scalars(upcoming_events_stmt().limit(limit)).all()


def latest_news(limit=3):
    return db.session.scalars(news_stmt().limit(limit)).all()


def public_post_by_slug(slug):
    return db.session.scalar(
        public_select(ContentPost).where(ContentPost.slug == slug)
        .options(selectinload(ContentPost.cover_image), selectinload(ContentPost.video))
    )


def related_posts(post, limit=3):
    return db.session.scalars(
        public_select(ContentPost).where(ContentPost.id != post.id, ContentPost.kind == post.kind)
        .options(selectinload(ContentPost.cover_image))
        .order_by(ContentPost.created_at.desc()).limit(limit)
    ).all()


def public_services(limit=None):
    stmt = public_select(Service).options(selectinload(Service.image)).order_by(Service.position, Service.name)
    if limit:
        stmt = stmt.limit(limit)
    return db.session.scalars(stmt).all()


def public_awards(limit=None):
    stmt = (public_select(Award).options(selectinload(Award.image), selectinload(Award.document))
            .order_by(Award.position, Award.year.desc().nulls_last(), Award.id.desc()))
    if limit:
        stmt = stmt.limit(limit)
    return db.session.scalars(stmt).all()


def public_testimonials(limit=None):
    stmt = (public_select(Testimonial).where(Testimonial.client_approved.is_(True))
            .options(selectinload(Testimonial.portrait), selectinload(Testimonial.project))
            .order_by(Testimonial.position, Testimonial.id.desc()))
    if limit:
        stmt = stmt.limit(limit)
    return db.session.scalars(stmt).all()


def has_published_samples():
    from app.models import Project, PublicationStatus

    for model in (Project, ContentPost, Service):
        if db.session.scalar(
            select(model.id).where(model.is_sample.is_(True),
                                   model.publication_status == PublicationStatus.PUBLISHED).limit(1)
        ):
            return True
    return False
