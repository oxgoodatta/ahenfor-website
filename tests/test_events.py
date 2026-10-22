from datetime import timedelta

from sqlalchemy import select

from app.extensions import db
from app.models import ContentPost, PostKind, PublicationStatus
from app.models.base import utcnow


def _fmt(dt):
    return dt.strftime("%Y-%m-%dT%H:%M")


def _post(admin_client, **overrides):
    data = {"title": "Site safety open day", "kind": "event", "summary": "Join us on site.",
            "body": "", "publication_status": "draft", "starts_at": _fmt(utcnow() + timedelta(days=10)),
            "ends_at": "", "venue": "Head office", "registration_url": "", "published_at": "", "slug": ""}
    data.update(overrides)
    return admin_client.post("/admin/events/new", data=data)


def _get(app, title):
    with app.app_context():
        return db.session.scalar(select(ContentPost).where(ContentPost.title == title))


def test_create_edit_and_publish_event(app, admin_client, client):
    assert _post(admin_client).status_code == 302
    post = _get(app, "Site safety open day")
    assert post.slug == "site-safety-open-day" and post.publication_status == PublicationStatus.DRAFT
    assert client.get("/news-events/site-safety-open-day").status_code == 404
    assert b"Site safety open day" not in client.get("/news-events?view=upcoming").data
    assert b"Site safety open day" in admin_client.get(f"/admin/events/{post.id}/preview").data

    admin_client.post(f"/admin/events/{post.id}/edit", data={
        "title": "Site safety open day", "kind": "event", "summary": "Updated summary", "publication_status": "published",
        "starts_at": _fmt(utcnow() + timedelta(days=10)), "venue": "Tema yard", "slug": "site-safety-open-day"})
    assert _get(app, "Site safety open day").venue == "Tema yard"
    assert b"Site safety open day" in client.get("/news-events?view=upcoming").data
    assert b"Site safety open day" in client.get("/").data
    assert client.get("/news-events/site-safety-open-day").status_code == 200


def test_event_requires_start_and_valid_range(admin_client):
    r = _post(admin_client, starts_at="")
    assert b"Events need a start date" in r.data
    start = utcnow() + timedelta(days=5)
    r = _post(admin_client, title="Bad range", starts_at=_fmt(start), ends_at=_fmt(start - timedelta(hours=2)))
    assert b"cannot end before it starts" in r.data


def test_registration_url_must_be_http(admin_client):
    r = _post(admin_client, registration_url="javascript:alert(1)")
    assert r.status_code == 200 and b"https://" in r.data


def test_upcoming_and_past_classification(app, admin_client, client):
    now = utcnow()
    _post(admin_client, title="Future event", publication_status="published", starts_at=_fmt(now + timedelta(days=3)))
    _post(admin_client, title="Finished event", publication_status="published",
          starts_at=_fmt(now - timedelta(days=10)), ends_at=_fmt(now - timedelta(days=9)))
    # Started yesterday but ends tomorrow: still upcoming/ongoing
    _post(admin_client, title="Multi day event", publication_status="published",
          starts_at=_fmt(now - timedelta(days=1)), ends_at=_fmt(now + timedelta(days=1)))
    upcoming = client.get("/news-events?view=upcoming").data
    past = client.get("/news-events?view=past").data
    assert b"Future event" in upcoming and b"Multi day event" in upcoming and b"Finished event" not in upcoming
    assert b"Finished event" in past and b"Future event" not in past
    # Chronological order for upcoming events
    assert upcoming.index(b"Multi day event") < upcoming.index(b"Future event")
    # Past events are preserved, not deleted
    assert _get(app, "Finished event") is not None
    assert _get(app, "Finished event").is_past


def test_news_items_and_scheduled_publication(app, admin_client, client):
    _post(admin_client, title="Website launch", kind="news", starts_at="", publication_status="published")
    _post(admin_client, title="Scheduled news", kind="news", starts_at="", publication_status="published",
          published_at=_fmt(utcnow() + timedelta(days=2)))
    news = client.get("/news-events?view=news").data
    assert b"Website launch" in news
    assert b"Scheduled news" not in news, "future publication date is not public yet"
    assert client.get("/news-events/scheduled-news").status_code == 404


def test_archive_post(app, admin_client, client):
    _post(admin_client, title="To archive", kind="news", starts_at="", publication_status="published")
    post = _get(app, "To archive")
    admin_client.post(f"/admin/status/post/{post.id}", data={"status": "archived"})
    assert client.get("/news-events/to-archive").status_code == 404
    assert _get(app, "To archive").publication_status == PublicationStatus.ARCHIVED


def test_admin_event_filters(app, admin_client):
    now = utcnow()
    _post(admin_client, title="Old one", starts_at=_fmt(now - timedelta(days=30)))
    _post(admin_client, title="New one", starts_at=_fmt(now + timedelta(days=30)))
    assert b"Old one" in admin_client.get("/admin/events?when=past").data
    assert b"New one" not in admin_client.get("/admin/events?when=past").data
    assert b"New one" in admin_client.get(f"/admin/events?kind={PostKind.EVENT.value}&when=upcoming").data
