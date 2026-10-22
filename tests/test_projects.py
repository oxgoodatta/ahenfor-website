"""Workflows A, C and E: create/publish projects, many projects independently, status lifecycle."""
from sqlalchemy import func, select

from app.extensions import db
from app.models import Project, ProjectStatus, PublicationStatus
from tests.conftest import image_file, make_project, project_form


def _project(app, **filters):
    with app.app_context():
        return db.session.scalar(select(Project).filter_by(**filters))


def test_workflow_a_create_draft_then_publish(app, admin_client, client):
    data = project_form(cover_image_file=image_file("cover.jpg"), cover_image_alt="Front elevation")
    response = admin_client.post("/admin/projects/new", data=data, content_type="multipart/form-data")
    assert response.status_code == 302

    project = _project(app, name="Takoradi Commercial Complex")
    assert project.slug == "takoradi-commercial-complex"
    assert project.publication_status == PublicationStatus.DRAFT
    assert project.cover_image_id is not None

    # Draft is hidden from public pages
    assert client.get("/projects/takoradi-commercial-complex").status_code == 404
    assert b"Takoradi Commercial Complex" not in client.get("/projects").data
    assert b"Takoradi Commercial Complex" not in client.get("/").data

    # Admin preview works and is marked as a preview
    preview = admin_client.get(f"/admin/projects/{project.id}/preview")
    assert preview.status_code == 200 and b"Preview" in preview.data

    # Publish
    response = admin_client.post(f"/admin/status/project/{project.id}", data={"status": "published"})
    assert response.status_code == 302
    page = client.get("/projects/takoradi-commercial-complex")
    assert page.status_code == 200
    assert b"Takoradi Commercial Complex" in page.data
    listing = client.get("/projects").data
    assert b"Takoradi Commercial Complex" in listing
    assert b'alt="Front elevation"' in listing, "cover image alt text is used on project cards"


def test_edit_project_and_slug_uniqueness(app, admin_client):
    admin_client.post("/admin/projects/new", data=project_form(name="Ho Road"))
    admin_client.post("/admin/projects/new", data=project_form(name="Ho Road"))
    with app.app_context():
        slugs = sorted(db.session.scalars(select(Project.slug)))
    assert slugs == ["ho-road", "ho-road-2"]

    project = _project(app, slug="ho-road")
    response = admin_client.post(f"/admin/projects/{project.id}/edit",
                                 data=project_form(name="Ho Road Upgrade", slug="ho-road-upgrade", location="Ho"))
    assert response.status_code == 302
    updated = _project(app, id=project.id)
    assert updated.name == "Ho Road Upgrade" and updated.slug == "ho-road-upgrade" and updated.location == "Ho"


def test_invalid_slug_rejected(admin_client):
    response = admin_client.post("/admin/projects/new", data=project_form(slug="Bad Slug!"))
    assert response.status_code == 200
    assert b"lower-case letters" in response.data


def test_validation_errors_are_shown(admin_client):
    response = admin_client.post("/admin/projects/new", data=project_form(name="", progress_percent="140"))
    assert response.status_code == 200
    assert b"This field is required" in response.data
    assert b"Number must be between 0 and 100" in response.data


def test_completion_date_cannot_precede_start(admin_client):
    response = admin_client.post("/admin/projects/new", data=project_form(
        start_date="2026-05-01", estimated_completion_date="2026-01-01"))
    assert b"cannot be before the start date" in response.data


def test_workflow_c_five_projects_are_independent(app, admin_client, client):
    ids = []
    for i in range(5):
        response = admin_client.post(
            "/admin/projects/new",
            data=project_form(name=f"Project {i}", status="ongoing", publication_status="published",
                              cover_image_file=image_file(f"c{i}.jpg", color=(i * 40, 20, 20))),
            content_type="multipart/form-data",
        )
        assert response.status_code == 302
        ids.append(_project(app, name=f"Project {i}").id)

    with app.app_context():
        covers = list(db.session.scalars(select(Project.cover_image_id)))
        assert len(set(covers)) == 5, "each project has its own cover"

    # Updating one project leaves the others untouched
    admin_client.post(f"/admin/projects/{ids[0]}/edit",
                      data=project_form(name="Project 0", status="completed", publication_status="published"))
    for pid in ids[1:]:
        assert _project(app, id=pid).status == ProjectStatus.ONGOING
    assert _project(app, id=ids[0]).status == ProjectStatus.COMPLETED

    listing = client.get("/projects?status=completed").data
    assert b"Project 0" in listing and b"Project 1" not in listing


def test_workflow_e_upcoming_then_ongoing(app, admin_client, client):
    admin_client.post("/admin/projects/new", data=project_form(name="Cape Coast School", status="upcoming",
                                                               publication_status="published"))
    home = client.get("/").data
    assert b"Upcoming projects" in home and b"Cape Coast School" in home
    assert b"Cape Coast School" in client.get("/projects?status=upcoming").data

    project = _project(app, name="Cape Coast School")
    admin_client.post(f"/admin/projects/{project.id}/edit",
                      data=project_form(name="Cape Coast School", status="ongoing", publication_status="published"))
    assert b"Cape Coast School" not in client.get("/projects?status=upcoming").data
    assert b"Cape Coast School" in client.get("/projects?status=ongoing").data
    detail = client.get("/projects/cape-coast-school").data
    assert b"Ongoing" in detail


def test_status_change_preserves_progress_history(app, admin_client):
    pid = make_project(app, phases=1)
    with app.app_context():
        phase_id = db.session.get(Project, pid).phases[0].id
    admin_client.post(f"/admin/projects/{pid}/updates/new", data={
        "phase_id": phase_id, "title": "Slab cast", "update_date": "2026-01-10", "publication_status": "published",
        "photos": [image_file("a.jpg")],
    }, content_type="multipart/form-data")
    admin_client.post(f"/admin/projects/{pid}/edit", data=project_form(
        name="Test Project", status="completed", publication_status="published", actual_completion_date="2026-02-01"))
    with app.app_context():
        project = db.session.get(Project, pid)
        assert project.status == ProjectStatus.COMPLETED
        assert len(project.phases[0].updates) == 1
        assert len(project.phases[0].updates[0].media_items) == 1


def test_featured_projects_and_fallback(app, client):
    make_project(app, name="Plain One")
    make_project(app, name="Plain Two")
    home = client.get("/").data
    assert b"Plain One" in home, "fallback shows recent projects when none are featured"

    make_project(app, name="Star Project", is_featured=True, featured_order=0)
    with app.app_context():
        from app.services.project_service import featured_projects

        names = [p.name for p in featured_projects(limit=3)]
    assert names[0] == "Star Project"


def test_feature_toggle(app, admin_client):
    pid = make_project(app)
    admin_client.post(f"/admin/projects/{pid}/feature")
    assert _project(app, id=pid).is_featured is True
    admin_client.post(f"/admin/projects/{pid}/feature")
    assert _project(app, id=pid).is_featured is False


def test_archived_projects_hidden_everywhere_public(app, admin_client, client):
    pid = make_project(app, name="Old Warehouse")
    admin_client.post(f"/admin/status/project/{pid}", data={"status": "archived"})
    assert client.get("/projects/old-warehouse").status_code == 404
    assert b"Old Warehouse" not in client.get("/projects").data
    assert b"old-warehouse" not in client.get("/sitemap.xml").data
    assert b"Old Warehouse" not in admin_client.get("/admin/projects").data  # hidden from the default list
    assert b"Old Warehouse" in admin_client.get("/admin/projects?visibility=archived").data


def test_admin_list_search_and_filters(app, admin_client):
    make_project(app, name="Kumasi Office Block", status=ProjectStatus.COMPLETED)
    make_project(app, name="Tema Warehouse", status=ProjectStatus.ONGOING, published=False)
    assert b"Kumasi Office Block" in admin_client.get("/admin/projects?q=kumasi").data
    assert b"Tema Warehouse" not in admin_client.get("/admin/projects?q=kumasi").data
    assert b"Tema Warehouse" in admin_client.get("/admin/projects?visibility=draft").data
    assert b"Kumasi Office Block" not in admin_client.get("/admin/projects?status=ongoing").data


def test_progress_percent_is_manual_only(app, admin_client):
    admin_client.post("/admin/projects/new", data=project_form(name="Pct", progress_percent="",
                                                               publication_status="published"))
    assert _project(app, name="Pct").progress_percent is None
    with app.app_context():
        assert db.session.scalar(select(func.count(Project.id))) == 1
