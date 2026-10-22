"""Media validation, storage failure handling, shared-media protection and the hero (workflow D)."""
import io

import pytest
from sqlalchemy import func, select

from app.extensions import db
from app.models import HeroConfig, MediaAsset, Project
from app.services import media_service
from app.storage import StorageError, get_storage
from tests.conftest import image_bytes, image_file, make_project, project_form

FETCH = {"X-Requested-With": "fetch"}


def _upload(client, data, profile="image"):
    file, name = data if isinstance(data, tuple) else (data, "file.bin")
    return client.post("/admin/media/upload", data={"file": (file, name), "profile": profile},
                       content_type="multipart/form-data", headers=FETCH)


def _count(app):
    with app.app_context():
        return db.session.scalar(select(func.count(MediaAsset.id)))


@pytest.mark.parametrize("fmt,name", [("JPEG", "a.jpg"), ("PNG", "b.png"), ("WEBP", "c.webp")])
def test_allowed_image_types(app, admin_client, fmt, name):
    response = _upload(admin_client, (image_bytes(fmt), name))
    assert response.status_code == 201, response.get_json()
    asset = response.get_json()["asset"]
    assert asset["kind"] == "image" and asset["thumb_url"]


def test_images_are_reencoded_resized_and_stripped(app, admin_client):
    response = _upload(admin_client, (image_bytes(size=(4000, 3000)), "big.jpg"))
    asset_id = response.get_json()["asset"]["id"]
    with app.app_context():
        asset = db.session.get(MediaAsset, asset_id)
        assert max(asset.width, asset.height) == media_service.MAIN_MAX_EDGE
        assert asset.storage_key.startswith("public/image/") and asset.storage_key.endswith(".jpg")
        assert "big" not in asset.storage_key, "browser filename never used in storage key"
        assert get_storage().exists(asset.thumb_key)


@pytest.mark.parametrize("payload,name,profile", [
    (b"<?php system($_GET['c']); ?>", "shell.php", "image"),
    (b"<svg onload=alert(1)>", "x.svg", "image"),
    (b"not really a jpeg", "fake.jpg", "image"),
    (b"MZ\x90\x00 exe", "doc.pdf", "document"),
    (b"\x00\x00\x00\x00junk", "clip.mp4", "video"),
    (b"GIF89a....", "anim.gif", "image"),
])
def test_unsafe_or_mismatched_uploads_rejected(app, admin_client, payload, name, profile):
    before = _count(app)
    response = _upload(admin_client, (io.BytesIO(payload), name), profile=profile)
    assert response.status_code == 400
    assert response.get_json()["ok"] is False
    assert _count(app) == before


def test_path_traversal_filename_is_ignored(app, admin_client):
    response = _upload(admin_client, (image_bytes(), "../../../etc/passwd.jpg"))
    assert response.status_code == 201
    with app.app_context():
        asset = db.session.get(MediaAsset, response.get_json()["asset"]["id"])
        assert ".." not in asset.storage_key and asset.original_filename == "passwd.jpg"


def test_valid_video_and_pdf_accepted(admin_client):
    mp4 = io.BytesIO(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)
    assert _upload(admin_client, (mp4, "site.mp4"), profile="video").status_code == 201
    pdf = io.BytesIO(b"%PDF-1.7\n%test\n")
    assert _upload(admin_client, (pdf, "cert.pdf"), profile="document").status_code == 201


def test_file_size_limit(app, admin_client):
    app.config["MAX_IMAGE_BYTES"] = 1024
    response = _upload(admin_client, (image_bytes(size=(1200, 1200)), "large.jpg"))
    assert response.status_code == 400
    assert "too large" in response.get_json()["error"]


def test_request_size_limit_returns_413(app, admin_client):
    app.config["MAX_CONTENT_LENGTH"] = 2048
    response = _upload(admin_client, (io.BytesIO(b"x" * 10_000), "big.jpg"))
    assert response.status_code == 413


def test_storage_failure_leaves_no_records_or_files(app, admin_client, monkeypatch):
    storage = app.extensions["media_storage"]
    original_save = storage.save
    calls = {"n": 0}

    def flaky_save(data, key, content_type, private=False):
        calls["n"] += 1
        if calls["n"] == 2:  # main file stored, thumbnail fails
            raise StorageError("simulated outage")
        return original_save(data, key, content_type, private)

    monkeypatch.setattr(storage, "save", flaky_save)
    before = _count(app)
    response = _upload(admin_client, (image_bytes(), "x.jpg"))
    assert response.status_code == 400
    assert "could not be saved" in response.get_json()["error"]
    assert _count(app) == before
    leftovers = [p for p in storage.root.rglob("*") if p.is_file()]
    assert leftovers == [], "the stored main file was cleaned up"


def test_database_failure_cleans_up_stored_files(app, admin_client, monkeypatch):
    storage = app.extensions["media_storage"]

    def broken_commit():
        raise RuntimeError("simulated database failure")

    with app.app_context():
        pass
    monkeypatch.setattr(db.session, "commit", broken_commit)
    with pytest.raises(RuntimeError):
        admin_client.post("/admin/projects/new",
                          data=project_form(cover_image_file=image_file("c.jpg")),
                          content_type="multipart/form-data")
    monkeypatch.undo()
    assert [p for p in storage.root.rglob("*") if p.is_file()] == []
    assert _count(app) == 0


def test_shared_media_cannot_be_deleted_while_referenced(app, admin_client):
    asset_id = _upload(admin_client, (image_bytes(), "shared.jpg")).get_json()["asset"]["id"]
    for name in ("Alpha", "Beta"):
        admin_client.post("/admin/projects/new", data=project_form(name=name, cover_image_id=str(asset_id)))
    response = admin_client.post(f"/admin/media/{asset_id}/delete", follow_redirects=True)
    assert b"still used by" in response.data
    assert _count(app) == 1

    # Alpha stops using it; Beta still does -> still protected
    with app.app_context():
        alpha = db.session.scalar(select(Project).where(Project.name == "Alpha"))
        alpha_id = alpha.id
    admin_client.post(f"/admin/projects/{alpha_id}/edit", data=project_form(name="Alpha", cover_image_id=""))
    admin_client.post(f"/admin/media/{asset_id}/delete")
    assert _count(app) == 1

    with app.app_context():
        beta_id = db.session.scalar(select(Project.id).where(Project.name == "Beta"))
    admin_client.post(f"/admin/projects/{beta_id}/edit", data=project_form(name="Beta", cover_image_id=""))
    admin_client.post(f"/admin/media/{asset_id}/delete")
    assert _count(app) == 0


def test_archiving_media_keeps_existing_usage(app, admin_client, client):
    asset_id = _upload(admin_client, (image_bytes(), "keep.jpg")).get_json()["asset"]["id"]
    admin_client.post("/admin/projects/new", data=project_form(name="Uses Archived", cover_image_id=str(asset_id),
                                                               publication_status="published"))
    admin_client.post(f"/admin/media/{asset_id}/archive")
    library = admin_client.get("/admin/media/library.json?kind=image").get_json()
    assert asset_id not in [i["id"] for i in library["items"]]
    with app.app_context():
        assert db.session.scalar(select(Project.cover_image_id).where(Project.name == "Uses Archived")) == asset_id
    # Re-saving the project with the archived asset still selected keeps it
    with app.app_context():
        pid = db.session.scalar(select(Project.id).where(Project.name == "Uses Archived"))
    admin_client.post(f"/admin/projects/{pid}/edit", data=project_form(name="Uses Archived", cover_image_id=str(asset_id),
                                                                       publication_status="published"))
    with app.app_context():
        assert db.session.get(Project, pid).cover_image_id == asset_id


def test_selecting_wrong_kind_or_private_media_is_rejected(app, admin_client):
    pdf = admin_client.post("/admin/media/upload", data={"file": (io.BytesIO(b"%PDF-1.4"), "a.pdf"), "profile": "document"},
                            content_type="multipart/form-data", headers=FETCH).get_json()["asset"]["id"]
    response = admin_client.post("/admin/projects/new", data=project_form(cover_image_id=str(pdf)))
    assert response.status_code == 200 and b"not available" in response.data


def test_workflow_d_hero_draft_preview_publish(app, admin_client, client):
    old = _upload(admin_client, (image_bytes(color=(10, 10, 10)), "old.jpg")).get_json()["asset"]["id"]
    admin_client.post("/admin/media/hero", data={
        "media_type": "image", "image_id": str(old), "headline": "Old headline", "primary_label": "Projects",
        "primary_target": "projects", "secondary_label": "", "secondary_target": "quote", "action": "publish",
    })
    # The old hero image is also used by a project
    admin_client.post("/admin/projects/new", data=project_form(name="Reuses Hero", cover_image_id=str(old)))
    assert b"Old headline" in client.get("/").data

    response = admin_client.post("/admin/media/hero", data={
        "media_type": "image", "image_file": image_file("new-hero.jpg"), "headline": "Building the future",
        "subheadline": "New subheadline", "primary_label": "See projects", "primary_target": "projects",
        "secondary_label": "Talk to us", "secondary_target": "contact", "action": "draft",
    }, content_type="multipart/form-data")
    assert response.status_code == 302
    assert b"Old headline" in client.get("/").data, "draft is not live"
    preview = admin_client.get("/admin/media/hero/preview")
    assert b"Building the future" in preview.data and b"Preview" in preview.data

    admin_client.post("/admin/media/hero/publish")
    home = client.get("/").data
    assert b"Building the future" in home and b"Talk to us" in home and b"/contact" in home

    # The old image is not deleted while the project still references it
    with app.app_context():
        assert db.session.get(MediaAsset, old) is not None
        published = db.session.scalar(select(HeroConfig).where(HeroConfig.state == "published"))
        assert published.image_id != old
    assert b"still used by" in admin_client.post(f"/admin/media/{old}/delete", follow_redirects=True).data


def test_hero_video_requires_a_video(admin_client):
    response = admin_client.post("/admin/media/hero", data={
        "media_type": "video", "headline": "H", "primary_label": "P", "primary_target": "projects",
        "secondary_target": "quote",
    })
    assert response.status_code == 200
    assert b"choose a video" in response.data


def test_hero_video_renders_without_autoplay_sound(app, admin_client, client):
    mp4 = io.BytesIO(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)
    vid = _upload(admin_client, (mp4, "hero.mp4"), profile="video").get_json()["asset"]["id"]
    admin_client.post("/admin/media/hero", data={
        "media_type": "video", "video_id": str(vid), "headline": "Video hero", "primary_label": "Go",
        "primary_target": "projects", "secondary_target": "quote", "action": "publish",
    })
    html = client.get("/").data.decode()
    assert "data-hero-video" in html and "muted" in html and "preload=\"none\"" in html
    assert "autoplay" not in html


def test_local_media_route_only_serves_public_keys(app, client):
    assert client.get("/media/private/document/2026/01/x.pdf").status_code == 404
    assert client.get("/media/public/../../instance/dev.db").status_code == 404


@pytest.mark.parametrize("url_suffix,field", [("/edit", "cover_image_id")])
def test_media_slot_hidden_field_rendered_once(app, admin_client, url_suffix, field):
    """Regression: a duplicated hidden id input would make the server ignore JS selections."""
    pid = make_project(app)
    html = admin_client.get(f"/admin/projects/{pid}{url_suffix}").data.decode()
    assert html.count(f'name="{field}"') == 1
    hero = admin_client.get("/admin/media/hero").data.decode()
    for name in ("image_id", "video_id", "poster_id"):
        assert hero.count(f'name="{name}"') == 1, name
    settings = admin_client.get("/admin/settings").data.decode()
    assert settings.count('name="about_image_id"') == 1
