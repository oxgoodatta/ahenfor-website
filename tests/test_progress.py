"""Workflow B: phases and continuous progress updates with photos."""
from sqlalchemy import select

from app.extensions import db
from app.models import (
    DEFAULT_PHASES,
    MediaAsset,
    ProgressUpdate,
    ProgressUpdateMedia,
    Project,
    ProjectPhase,
    PublicationStatus,
)
from tests.conftest import image_file, make_project


def _phases(app, pid):
    with app.app_context():
        return [(p.id, p.title, p.position, p.is_archived)
                for p in sorted(db.session.get(Project, pid).phases, key=lambda p: p.position)]


def _post_update(client, pid, phase_id, title, date="2026-03-01", status="published", photos=(), extra=None):
    data = {"phase_id": phase_id, "title": title, "update_date": date, "body": f"{title} details",
            "publication_status": status, "photos": list(photos)}
    data.update(extra or {})
    return client.post(f"/admin/projects/{pid}/updates/new", data=data, content_type="multipart/form-data")


def test_create_custom_phase_and_defaults(app, admin_client):
    pid = make_project(app)
    response = admin_client.post(f"/admin/projects/{pid}/phases/new",
                                 data={"title": "Site Clearing", "status": "in_progress", "description": ""})
    assert response.status_code == 302
    admin_client.post(f"/admin/projects/{pid}/phases/defaults")
    titles = [t for _, t, _, _ in _phases(app, pid)]
    assert titles[0] == "Site Clearing"
    assert titles[1:] == DEFAULT_PHASES
    # Adding defaults twice does not duplicate them
    admin_client.post(f"/admin/projects/{pid}/phases/defaults")
    assert len(_phases(app, pid)) == 1 + len(DEFAULT_PHASES)


def test_edit_phase(app, admin_client):
    pid = make_project(app, phases=1)
    phase_id = _phases(app, pid)[0][0]
    admin_client.post(f"/admin/projects/{pid}/phases/{phase_id}/edit",
                      data={"title": "Foundation Works", "status": "completed", "start_date": "2026-01-01",
                            "completed_date": "2026-02-01"})
    with app.app_context():
        phase = db.session.get(ProjectPhase, phase_id)
        assert phase.title == "Foundation Works" and phase.status.value == "completed"


def test_reorder_phases_with_buttons_and_explicit_order(app, admin_client):
    pid = make_project(app, phases=3)
    ids = [p[0] for p in _phases(app, pid)]
    admin_client.post(f"/admin/projects/{pid}/phases/{ids[2]}/move", data={"direction": "up"})
    assert [p[0] for p in _phases(app, pid)] == [ids[0], ids[2], ids[1]]

    admin_client.post(f"/admin/projects/{pid}/phases/reorder", data={"order": f"{ids[1]},{ids[0]},{ids[2]}"})
    assert [p[0] for p in _phases(app, pid)] == [ids[1], ids[0], ids[2]]

    # An order that doesn't match the project's phases is rejected
    other = make_project(app, name="Other", phases=1)
    foreign = _phases(app, other)[0][0]
    admin_client.post(f"/admin/projects/{pid}/phases/reorder", data={"order": f"{ids[1]},{foreign},{ids[2]}"})
    assert [p[0] for p in _phases(app, pid)] == [ids[1], ids[0], ids[2]]


def test_phase_from_another_project_is_404(app, admin_client):
    pid = make_project(app, phases=1)
    other = make_project(app, name="Other", phases=1)
    other_phase = _phases(app, other)[0][0]
    assert admin_client.get(f"/admin/projects/{pid}/phases/{other_phase}/edit").status_code == 404
    response = _post_update(admin_client, pid, other_phase, "Sneaky")
    assert response.status_code in (200, 404)  # rejected by choice validation
    with app.app_context():
        assert db.session.scalar(select(ProgressUpdate).where(ProgressUpdate.title == "Sneaky")) is None


def test_workflow_b_updates_with_photos_accumulate(app, admin_client, client):
    pid = make_project(app, name="Takoradi Complex", phases=2)
    phase_a, phase_b = [p[0] for p in _phases(app, pid)]

    r1 = _post_update(admin_client, pid, phase_a, "Site excavation", "2026-01-05",
                      photos=[image_file("1.jpg"), image_file("2.png", fmt="PNG"), image_file("3.jpg")])
    assert r1.status_code == 302
    r2 = _post_update(admin_client, pid, phase_a, "Reinforcement installation", "2026-01-20",
                      photos=[image_file("4.jpg")])
    r3 = _post_update(admin_client, pid, phase_b, "Ground-floor columns", "2026-02-10",
                      photos=[image_file("5.jpg"), image_file("6.jpg")])
    assert r2.status_code == r3.status_code == 302

    with app.app_context():
        updates = {u.title: u for u in db.session.scalars(select(ProgressUpdate))}
        assert len(updates["Site excavation"].media_items) == 3
        assert updates["Site excavation"].phase_id == phase_a
        assert updates["Ground-floor columns"].phase_id == phase_b
        assert [m.position for m in updates["Site excavation"].media_items] == [0, 1, 2]
        first_photo_ids = {m.media_id for m in updates["Site excavation"].media_items}

    full = client.get("/projects/takoradi-complex").data.decode()
    assert "Latest update" in full and full.index("Latest update") < full.index('id="progress"')
    page = full[full.index('id="progress"'):]  # the construction timeline section
    # Photos appear under the right phase, oldest update first, older updates intact
    assert page.index("Site excavation") < page.index("Reinforcement installation") < page.index("Ground-floor columns")
    assert "LATEST" in page and page.index("LATEST") > page.index("Ground-floor columns")
    assert page.count('data-lightbox') >= 6

    # Weeks later: add more photos to the same phase without touching earlier ones
    _post_update(admin_client, pid, phase_a, "Concrete foundation completed", "2026-03-01",
                 photos=[image_file("7.jpg")])
    with app.app_context():
        excavation = db.session.scalar(select(ProgressUpdate).where(ProgressUpdate.title == "Site excavation"))
        assert {m.media_id for m in excavation.media_items} == first_photo_ids
        assert db.session.scalar(select(db.func.count(ProgressUpdate.id))) == 4


def test_edit_update_reorder_caption_and_remove_photo_keeps_file(app, admin_client):
    pid = make_project(app, phases=1)
    phase = _phases(app, pid)[0][0]
    _post_update(admin_client, pid, phase, "Slab", photos=[image_file("a.jpg"), image_file("b.jpg"), image_file("c.jpg")])
    with app.app_context():
        update = db.session.scalar(select(ProgressUpdate))
        ids = [m.media_id for m in update.media_items]
        uid = update.id

    response = admin_client.post(f"/admin/updates/{uid}/edit", data={
        "phase_id": phase, "title": "Slab cast", "update_date": "2026-03-01", "publication_status": "published",
        "media_id": [ids[2], ids[0]], "media_caption": ["Pour in progress", "Formwork"], "media_alt": ["", "Formwork alt"],
    }, content_type="multipart/form-data")
    assert response.status_code == 302
    with app.app_context():
        update = db.session.get(ProgressUpdate, uid)
        assert update.title == "Slab cast"
        assert [(m.media_id, m.caption) for m in update.media_items] == [(ids[2], "Pour in progress"), (ids[0], "Formwork")]
        assert db.session.get(MediaAsset, ids[1]) is not None, "removing a photo from an update keeps the file"


def test_associating_existing_library_photo(app, admin_client):
    pid = make_project(app, phases=1)
    phase = _phases(app, pid)[0][0]
    upload = admin_client.post("/admin/media/upload", data={"file": image_file("lib.jpg"), "profile": "image"},
                               content_type="multipart/form-data", headers={"X-Requested-With": "fetch"})
    assert upload.status_code == 201
    asset_id = upload.get_json()["asset"]["id"]
    _post_update(admin_client, pid, phase, "From library", extra={"media_id": [asset_id], "media_caption": ["c"],
                                                                     "media_alt": [""]})
    with app.app_context():
        update = db.session.scalar(select(ProgressUpdate))
        assert [m.media_id for m in update.media_items] == [asset_id]


def test_publish_and_unpublish_update(app, admin_client, client):
    pid = make_project(app, name="Visible Project", phases=1)
    phase = _phases(app, pid)[0][0]
    _post_update(admin_client, pid, phase, "Draft update", status="draft")
    assert b"Draft update" not in client.get("/projects/visible-project").data
    # ...but the admin preview shows it, labelled as a draft
    preview = admin_client.get(f"/admin/projects/{pid}/preview").data
    assert b"Draft update" in preview and b"DRAFT" in preview

    with app.app_context():
        uid = db.session.scalar(select(ProgressUpdate.id))
    admin_client.post(f"/admin/status/update/{uid}", data={"status": "published"})
    assert b"Draft update" in client.get("/projects/visible-project").data
    admin_client.post(f"/admin/status/update/{uid}", data={"status": "draft"})
    assert b"Draft update" not in client.get("/projects/visible-project").data
    admin_client.post(f"/admin/status/update/{uid}", data={"status": "archived"})
    with app.app_context():
        assert db.session.get(ProgressUpdate, uid).publication_status == PublicationStatus.ARCHIVED


def test_published_update_hidden_while_project_is_draft(app, admin_client, client):
    pid = make_project(app, name="Secret Project", published=False, phases=1)
    phase = _phases(app, pid)[0][0]
    _post_update(admin_client, pid, phase, "Published update")
    assert client.get("/projects/secret-project").status_code == 404


def test_archived_phase_hides_its_updates_but_keeps_them(app, admin_client, client):
    pid = make_project(app, name="Phase Test", phases=2)
    phase_a = _phases(app, pid)[0][0]
    _post_update(admin_client, pid, phase_a, "Hidden with phase")
    admin_client.post(f"/admin/projects/{pid}/phases/{phase_a}/archive")
    assert b"Hidden with phase" not in client.get("/projects/phase-test").data
    with app.app_context():
        assert db.session.scalar(select(ProgressUpdate).where(ProgressUpdate.title == "Hidden with phase"))
    admin_client.post(f"/admin/projects/{pid}/phases/{phase_a}/archive", data={"restore": "1"})
    assert b"Hidden with phase" in client.get("/projects/phase-test").data


def test_update_requires_a_phase(app, admin_client):
    pid = make_project(app)
    response = admin_client.get(f"/admin/projects/{pid}/updates/new")
    assert response.status_code == 302
    assert f"/admin/projects/{pid}/phases/new" in response.headers["Location"]


def test_future_dated_update_rejected(app, admin_client):
    pid = make_project(app, phases=1)
    phase = _phases(app, pid)[0][0]
    response = _post_update(admin_client, pid, phase, "Future", date="2999-01-01")
    assert response.status_code == 200
    assert b"cannot be in the future" in response.data


def test_progress_manager_page_shows_context(app, admin_client):
    pid = make_project(app, name="Context Project", phases=1)
    phase = _phases(app, pid)[0][0]
    page = admin_client.get(f"/admin/projects/{pid}/updates/new?phase_id={phase}").data
    assert b"You are adding an update for" in page and b"Context Project" in page and b"Phase 1" in page
    assert ProgressUpdateMedia  # imported for clarity
