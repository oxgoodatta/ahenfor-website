import io
from datetime import date

import pytest
from sqlalchemy import select

from app.extensions import db
from app.models import Award, Inquiry, InquiryKind, Project, PublicationStatus, Service, Testimonial
from app.services import settings_service
from app.services.email_service import backend
from tests.conftest import make_project


@pytest.mark.parametrize("url", ["/", "/about", "/services", "/projects", "/awards", "/news-events",
                                 "/news-events?view=news", "/news-events?view=past", "/contact",
                                 "/request-quote", "/privacy", "/robots.txt", "/sitemap.xml"])
def test_public_pages_render_on_empty_site(client, url):
    response = client.get(url)
    assert response.status_code == 200


def test_homepage_has_no_invented_statistics_or_credentials(client):
    html = client.get("/").data.decode()
    assert "Company in numbers" not in html
    assert "Awards and certifications" not in html.split("<footer")[0] or "award-year" not in html
    assert "What our clients say" not in html


def test_statistics_only_show_entered_values(app, admin_client, client):
    admin_client.post("/admin/settings?group=stats", data={"stat_years": "12", "stat_projects": "",
                                                           "stat_projects_source": "manual", "stat_clients": "",
                                                           "stat_awards": ""})
    html = client.get("/").data.decode()
    assert "Years of experience" in html and ">12<" in html
    assert "Clients served" not in html


def test_derived_project_count_counts_each_completed_project_once(app, admin_client, client):
    from app.models import ProjectStatus

    make_project(app, name="Done A", status=ProjectStatus.COMPLETED)
    make_project(app, name="Done B", status=ProjectStatus.COMPLETED)
    make_project(app, name="Draft Done", status=ProjectStatus.COMPLETED, published=False)
    make_project(app, name="Still going", status=ProjectStatus.ONGOING)
    admin_client.post("/admin/settings?group=stats", data={"stat_projects_source": "derived"})
    with app.app_context():
        stats = settings_service.public_stats()
    assert {"value": 2, "label": "Projects completed"} in stats


def test_project_listing_detail_and_timeline(app, admin_client, client):
    pid = make_project(app, name="Timeline Project", phases=2, progress_percent=45,
                       client_name="Secret Client", show_client=False)
    with app.app_context():
        phase_ids = [p.id for p in db.session.get(Project, pid).phases]
    from tests.conftest import image_file

    admin_client.post(f"/admin/projects/{pid}/updates/new", data={
        "phase_id": phase_ids[0], "title": "Excavation done", "update_date": "2026-02-01",
        "publication_status": "published", "photos": [image_file("p.jpg")]}, content_type="multipart/form-data")
    html = client.get("/projects/timeline-project").data.decode()
    assert "Phase by phase" in html and "Excavation done" in html and "Phase 1" in html
    assert "45%" in html and "As reported by the project team" in html
    assert "Secret Client" not in html, "client name hidden unless approved"
    assert 'property="og:title"' in html and "<link rel=\"canonical\"" in html
    assert "Latest update" in html


def test_services_awards_testimonials_published_only(app, client):
    with app.app_context():
        db.session.add_all([
            Service(name="Building Construction", slug="building-construction", short_description="Buildings.",
                    publication_status=PublicationStatus.PUBLISHED),
            Service(name="Hidden Service", slug="hidden", short_description="x"),
            Award(title="Real Certificate", issuer="Ghana Institution of Engineering", year=2024,
                  publication_status=PublicationStatus.PUBLISHED),
            Testimonial(client_name="Approved Client", quote="Excellent.", client_approved=True,
                        publication_status=PublicationStatus.PUBLISHED),
        ])
        db.session.commit()
    home = client.get("/").data
    assert b"Building Construction" in home and b"Hidden Service" not in home
    assert b"Real Certificate" in client.get("/awards").data
    assert b"Approved Client" in home
    quote = client.get("/request-quote").data
    assert b"Building Construction" in quote and b"Hidden Service" not in quote


def test_contact_form_validation_and_storage(app, client):
    bad = client.post("/contact", data={"full_name": "", "email": "not-an-email", "subject": "", "message": "short"})
    assert bad.status_code == 200
    assert b"This field is required" in bad.data and b"Invalid email" in bad.data

    ok = client.post("/contact", data={"full_name": "Yaw Mensah", "email": "yaw@example.com", "phone": "024 000 0000",
                                       "subject": "Partnership", "message": "We would like to discuss a project."})
    assert ok.status_code == 302
    with app.app_context():
        inquiry = db.session.scalar(select(Inquiry))
        assert inquiry.kind == InquiryKind.CONTACT and inquiry.full_name == "Yaw Mensah"


def test_honeypot_spam_is_discarded(app, client):
    response = client.post("/contact", data={"full_name": "Bot", "email": "bot@example.com", "subject": "Buy",
                                             "message": "Spam spam spam spam", "company_website": "http://spam"})
    assert response.status_code == 302
    with app.app_context():
        assert db.session.scalar(select(Inquiry)) is None


def test_quote_form_notifies_configured_address(app, admin_client, client):
    admin_client.post("/admin/settings?group=contact", data={"inquiry_notify_email": "projects@ahenfor.example"})
    response = client.post("/request-quote", data={
        "full_name": "Efua Asante", "email": "efua@example.com", "phone": "+233 20 000 0000",
        "project_location": "Cape Coast", "service": "Other / not sure", "timeline": "3 – 6 months",
        "message": "Three-bedroom house with boundary wall."})
    assert response.status_code == 302
    with app.app_context():
        outbox = backend().outbox
        assert len(outbox) == 1 and outbox[0].to == ["projects@ahenfor.example"]
        assert "Efua Asante" in outbox[0].subject and outbox[0].reply_to == "efua@example.com"
        assert db.session.scalar(select(Inquiry)).notified_at is not None


def test_quote_form_rejects_unsafe_attachment(app, client):
    response = client.post("/request-quote", data={
        "full_name": "A", "email": "a@example.com", "phone": "0240000000", "project_location": "Accra",
        "service": "Other / not sure", "timeline": "Not decided", "message": "Need a warehouse built please.",
        "attachment": (io.BytesIO(b"#!/bin/sh\nrm -rf /"), "brief.sh")}, content_type="multipart/form-data")
    assert response.status_code == 200 and b"File type not allowed" in response.data
    with app.app_context():
        assert db.session.scalar(select(Inquiry)) is None


def test_missing_page_handling(client):
    response = client.get("/no-such-page")
    assert response.status_code == 404 and b"Page not found" in response.data
    assert client.get("/projects/no-such-project").status_code == 404
    assert client.get("/news-events/no-such-post").status_code == 404


def test_sitemap_lists_published_content(app, client):
    make_project(app, name="Mapped Project")
    xml = client.get("/sitemap.xml").data.decode()
    assert "http://localhost/projects/mapped-project" in xml and "<lastmod>" in xml


def test_contact_details_from_settings(app, admin_client, client):
    admin_client.post("/admin/settings?group=contact", data={
        "contact_phone": "+233 30 000 0000", "contact_email": "info@ahenfor.example",
        "contact_whatsapp": "233240000000", "contact_map_url": "https://maps.example/x"})
    html = client.get("/contact").data.decode()
    assert "+233 30 000 0000" in html and "info@ahenfor.example" in html and "https://wa.me/233240000000" in html
    footer = client.get("/").data.decode().split("<footer")[1]
    assert "info@ahenfor.example" in footer


def test_settings_reject_javascript_urls(admin_client):
    response = admin_client.post("/admin/settings?group=social", data={"social_linkedin": "javascript:alert(1)"})
    assert response.status_code == 200 and b"https://" in response.data


def test_seed_demo_flags_and_clears_sample_content(app, client):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["seed-demo"])
    assert result.exit_code == 0, result.output
    assert b"Sample content:" in client.get("/").data
    with app.app_context():
        assert db.session.scalar(select(Project).where(Project.is_sample.is_(False))) is None
        assert db.session.scalar(select(Award)) is None and db.session.scalar(select(Testimonial)) is None
    result = runner.invoke(args=["seed-demo", "--clear"])
    assert result.exit_code == 0, result.output
    assert b"Sample content:" not in client.get("/").data
    with app.app_context():
        assert db.session.scalar(select(Project)) is None
    assert date.today()
