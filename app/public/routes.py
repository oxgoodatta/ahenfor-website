import os
from datetime import datetime

from flask import (
    Response,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from sqlalchemy import select

from app.extensions import db, limiter
from app.models import (
    PROJECT_CATEGORIES,
    ContentPost,
    Inquiry,
    InquiryKind,
    Project,
    ProjectStatus,
)
from app.models.base import utcnow
from app.public import bp
from app.public.forms import ContactForm, QuoteForm
from app.services import content_service, email_service, project_service, settings_service
from app.services.media_service import MediaValidationError, UploadBatch
from app.services.publishing_service import public_select
from app.storage import StorageError, get_storage


def _form_rate_limit():
    return current_app.config["FORM_RATE_LIMIT"]


def _page():
    return request.args.get("page", 1, type=int) or 1


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@bp.route("/")
def home():
    hero = settings_service.get_hero("published")
    return render_template("public/home.html", hero=hero, **home_context())


def home_context():
    return {
        "stats": settings_service.public_stats(),
        "services": content_service.public_services(limit=6),
        "featured": project_service.featured_projects(limit=3),
        "upcoming_projects": project_service.projects_by_status(ProjectStatus.UPCOMING, limit=3),
        "awards": content_service.public_awards(limit=4),
        "testimonials": content_service.public_testimonials(limit=3),
        "events": content_service.upcoming_events(limit=3),
        "news": content_service.latest_news(limit=3),
    }


@bp.route("/about")
def about():
    return render_template(
        "public/about.html",
        services=content_service.public_services(limit=6),
        stats=settings_service.public_stats(),
        awards=content_service.public_awards(limit=4),
    )


@bp.route("/services")
def services():
    return render_template("public/services.html", services=content_service.public_services())


@bp.route("/projects")
def projects():
    status = request.args.get("status") or None
    if status and status not in {s.value for s in ProjectStatus}:
        status = None
    category = request.args.get("category") or None
    if category and category not in PROJECT_CATEGORIES:
        category = None
    pagination = db.paginate(
        project_service.public_projects_stmt(status=status, category=category),
        page=_page(), per_page=current_app.config["PUBLIC_PER_PAGE"], error_out=False,
    )
    return render_template(
        "public/projects.html", pagination=pagination, projects=pagination.items,
        status=status, category=category, statuses=list(ProjectStatus), categories=PROJECT_CATEGORIES,
    )


def render_project_page(project, preview=False):
    views = project_service.timeline(project, include_drafts=preview)
    return render_template(
        "public/project_detail.html",
        project=project,
        phases=views,
        latest=project_service.latest_update(views),
        gallery=project_service.gallery(views, limit=24),
        related=project_service.related_projects(project),
        preview=preview,
    )


@bp.route("/projects/<slug>")
def project_detail(slug):
    project = project_service.public_project_by_slug(slug)
    if project is None:
        abort(404)
    return render_project_page(project)


@bp.route("/awards")
def awards():
    return render_template("public/awards.html", awards=content_service.public_awards())


@bp.route("/news-events")
def news_events():
    view = request.args.get("view")
    if view not in ("upcoming", "news", "past"):
        view = "upcoming" if content_service.upcoming_events(limit=1) else "news"
    stmt = {
        "upcoming": content_service.upcoming_events_stmt,
        "news": content_service.news_stmt,
        "past": content_service.past_events_stmt,
    }[view]()
    pagination = db.paginate(stmt, page=_page(), per_page=current_app.config["PUBLIC_PER_PAGE"], error_out=False)
    return render_template("public/events.html", view=view, pagination=pagination, posts=pagination.items)


def render_post_page(post, preview=False):
    return render_template(
        "public/event_detail.html", post=post, related=content_service.related_posts(post), preview=preview
    )


@bp.route("/news-events/<slug>")
def post_detail(slug):
    post = content_service.public_post_by_slug(slug)
    if post is None:
        abort(404)
    return render_post_page(post)


@bp.route("/privacy")
def privacy():
    return render_template("public/privacy.html")


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------

def _notify(inquiry):
    recipient = settings_service.site().inquiry_notify_email or current_app.config.get("INQUIRY_NOTIFY_EMAIL")
    delivered = email_service.send_inquiry_notification(inquiry, recipient)
    if delivered:
        inquiry.notified_at = utcnow()
        db.session.commit()


@bp.route("/contact", methods=["GET", "POST"])
@limiter.limit(_form_rate_limit, methods=["POST"])
def contact():
    form = ContactForm()
    if form.validate_on_submit():
        if not form.is_spam:
            inquiry = Inquiry(
                kind=InquiryKind.CONTACT,
                full_name=form.full_name.data.strip(),
                email=form.email.data.strip().lower(),
                phone=(form.phone.data or "").strip() or None,
                subject=form.subject.data.strip(),
                message=form.message.data.strip(),
            )
            db.session.add(inquiry)
            db.session.commit()
            _notify(inquiry)
        flash("Thank you. Your message has been received and our team will respond shortly.", "success")
        return redirect(url_for("public.contact", sent=1))
    return render_template("public/contact.html", form=form, sent=request.args.get("sent"))


def _service_choices():
    names = [s.name for s in content_service.public_services()]
    return [("", "Select a service")] + [(n, n) for n in names] + [("Other / not sure", "Other / not sure")]


@bp.route("/request-quote", methods=["GET", "POST"])
@limiter.limit(_form_rate_limit, methods=["POST"])
def request_quote():
    form = QuoteForm()
    form.service.choices = _service_choices()
    if request.method == "GET" and request.args.get("service"):
        form.service.data = request.args.get("service")
    if form.validate_on_submit():
        if form.is_spam:
            flash("Thank you. Your request has been received.", "success")
            return redirect(url_for("public.request_quote", sent=1))
        try:
            with UploadBatch() as batch:
                attachment = None
                if form.attachment.data and getattr(form.attachment.data, "filename", ""):
                    attachment = batch.store(form.attachment.data, profile="attachment", private=True)
                inquiry = Inquiry(
                    kind=InquiryKind.QUOTE,
                    full_name=form.full_name.data.strip(),
                    email=form.email.data.strip().lower(),
                    phone=form.phone.data.strip(),
                    organization=(form.organization.data or "").strip() or None,
                    project_location=form.project_location.data.strip(),
                    service=form.service.data,
                    message=form.message.data.strip(),
                    budget_range=form.budget_range.data or None,
                    timeline=form.timeline.data or None,
                    attachment=attachment,
                )
                db.session.add(inquiry)
                db.session.commit()
        except MediaValidationError as exc:
            form.attachment.errors = [str(exc)]
        else:
            _notify(inquiry)
            flash("Thank you. Your project request has been received. Our team will contact you shortly.", "success")
            return redirect(url_for("public.request_quote", sent=1))
    return render_template("public/request_quote.html", form=form, sent=request.args.get("sent"))


# ---------------------------------------------------------------------------
# Media (local storage only) and SEO files
# ---------------------------------------------------------------------------

@bp.route("/media/<path:key>")
def media_file(key):
    storage = get_storage()
    if not storage.is_local or not key.startswith("public/"):
        abort(404)
    try:
        path = storage.path_for(key)
    except StorageError:
        abort(404)
    if not path.is_file():
        abort(404)
    return send_from_directory(storage.root, key, max_age=60 * 60 * 24 * 365)


@bp.route("/brand/logo.png")
def brand_logo():
    """The site logo with its white margin cropped and background made transparent."""
    from app.utils.logo import prepare_logo

    prepared = prepare_logo(current_app.static_folder, current_app.instance_path)
    if prepared is None:
        abort(404)
    path, _ = prepared
    return send_from_directory(os.path.dirname(path), os.path.basename(path), max_age=60 * 60 * 24 * 365)


@bp.route("/sitemap.xml")
def sitemap():
    base = current_app.config["SITE_URL"]
    pages = [(url_for(e), None) for e in (
        "public.home", "public.about", "public.services", "public.projects",
        "public.awards", "public.news_events", "public.contact", "public.request_quote",
    )]
    for slug, updated in db.session.execute(
        public_select(Project).with_only_columns(Project.slug, Project.updated_at)
    ):
        pages.append((url_for("public.project_detail", slug=slug), updated))
    for slug, updated in db.session.execute(
        public_select(ContentPost).with_only_columns(ContentPost.slug, ContentPost.updated_at)
    ):
        pages.append((url_for("public.post_detail", slug=slug), updated))
    xml = render_template("public/sitemap.xml", base=base, pages=pages)
    return Response(xml, mimetype="application/xml")


@bp.route("/robots.txt")
def robots():
    base = current_app.config["SITE_URL"]
    body = f"User-agent: *\nDisallow: /admin/\nAllow: /\n\nSitemap: {base}{url_for('public.sitemap')}\n"
    return Response(body, mimetype="text/plain")


@bp.app_template_global()
def now_utc():
    return utcnow()


@bp.app_template_global()
def year_now():
    return datetime.now().year


__all__ = ["render_project_page", "render_post_page", "home_context", "select"]
