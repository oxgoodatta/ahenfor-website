"""News/events, services, awards, testimonials and the shared publish/archive action."""
from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.admin import bp
from app.admin.forms import AwardForm, ConfirmForm, PostForm, ServiceForm, TestimonialForm
from app.admin.helpers import (
    DOCUMENT,
    IMAGE,
    VIDEO,
    flash_saved,
    media_slot,
    paginate,
    preload_media_slot,
    redirect_back,
    slug_for,
)
from app.extensions import db
from app.models import (
    Award,
    ContentPost,
    PostKind,
    ProgressUpdate,
    Project,
    PublicationStatus,
    Service,
    Testimonial,
)
from app.models.base import utcnow
from app.services import publishing_service
from app.services.media_service import MediaValidationError, UploadBatch

PUBLISHABLE = {
    "project": (Project, "Project", "admin.projects"),
    "update": (ProgressUpdate, "Progress update", "admin.projects"),
    "post": (ContentPost, "News/event item", "admin.posts"),
    "service": (Service, "Service", "admin.services"),
    "award": (Award, "Award", "admin.awards"),
    "testimonial": (Testimonial, "Testimonial", "admin.testimonials"),
}

STATUS_MESSAGES = {
    PublicationStatus.PUBLISHED: "{noun} published.",
    PublicationStatus.DRAFT: "{noun} unpublished and returned to draft.",
    PublicationStatus.ARCHIVED: "{noun} archived. It is hidden from the website but kept in the system.",
}


@bp.route("/status/<entity>/<int:obj_id>", methods=["POST"])
def change_status(entity, obj_id):
    """Publish, unpublish (draft) or archive any publishable record."""
    if entity not in PUBLISHABLE:
        abort(404)
    model, noun, default_endpoint = PUBLISHABLE[entity]
    obj = db.session.get(model, obj_id)
    if obj is None:
        abort(404)
    if not ConfirmForm().validate_on_submit():
        abort(400)
    try:
        status = PublicationStatus(request.form.get("status", ""))
    except ValueError:
        abort(400)
    if entity == "testimonial" and status == PublicationStatus.PUBLISHED and not obj.client_approved:
        flash("This testimonial cannot be published until the client's approval is recorded.", "error")
        return redirect_back(default_endpoint)
    publishing_service.set_status(obj, status)
    if entity == "update":
        obj.phase.project.updated_at = utcnow()
    db.session.commit()
    flash(STATUS_MESSAGES[status].format(noun=noun), "success")
    if entity == "update" and status == PublicationStatus.PUBLISHED and not obj.phase.project.is_published:
        flash("Note: the project itself is still a draft, so this update is not yet visible publicly.", "warning")
    return redirect_back(default_endpoint)


def _list_filters(model, search_columns):
    q = (request.args.get("q") or "").strip()
    visibility = request.args.get("visibility") or ""
    stmt = select(model)
    if q:
        like = f"%{q[:100]}%"
        stmt = stmt.where(or_(*[c.ilike(like) for c in search_columns]))
    if visibility in {s.value for s in PublicationStatus}:
        stmt = stmt.where(model.publication_status == visibility)
    else:
        stmt = stmt.where(model.publication_status != PublicationStatus.ARCHIVED)
    return stmt, q, visibility


def _form_page(template, **context):
    context.setdefault("action_form", ConfirmForm())
    return render_template(template, **context)


# ---------------------------------------------------------------------------
# News and events
# ---------------------------------------------------------------------------

@bp.route("/events")
def posts():
    stmt, q, visibility = _list_filters(ContentPost, [ContentPost.title, ContentPost.summary, ContentPost.venue])
    kind = request.args.get("kind") or ""
    if kind in {k.value for k in PostKind}:
        stmt = stmt.where(ContentPost.kind == kind)
    when = request.args.get("when") or ""
    end = db.func.coalesce(ContentPost.ends_at, ContentPost.starts_at)
    if when == "upcoming":
        stmt = stmt.where(ContentPost.starts_at.isnot(None), end >= utcnow())
    elif when == "past":
        stmt = stmt.where(ContentPost.starts_at.isnot(None), end < utcnow())
    pagination = paginate(stmt.options(selectinload(ContentPost.cover_image))
                          .order_by(ContentPost.created_at.desc(), ContentPost.id.desc()))
    return render_template("admin/events/list.html", pagination=pagination, posts=pagination.items, q=q,
                           visibility=visibility, kind=kind, when=when, kinds=list(PostKind),
                           visibilities=list(PublicationStatus), action_form=ConfirmForm())


def _post_view(post, form, is_new):
    if form.validate_on_submit():
        try:
            with UploadBatch() as batch:
                post.title = form.title.data.strip()
                post.slug = slug_for(ContentPost, form.slug.data, post.title, exclude_id=post.id)
                post.kind = form.kind.data
                post.summary = form.summary.data.strip()
                post.body = (form.body.data or "").strip()
                post.cover_image = media_slot(batch, form, "cover_image", IMAGE, alt_text=post.title)
                post.video = media_slot(batch, form, "video", VIDEO)
                post.starts_at = form.starts_at.data
                post.ends_at = form.ends_at.data
                post.venue = (form.venue.data or "").strip() or None
                post.registration_url = (form.registration_url.data or "").strip() or None
                post.published_at = form.published_at.data
                publishing_service.set_status(post, form.publication_status.data)
                db.session.add(post)
                db.session.commit()
        except MediaValidationError as exc:
            flash(str(exc), "error")
        else:
            flash_saved("News/event item", post)
            return redirect(url_for("admin.posts"))
    elif request.method == "POST":
        flash("Please correct the highlighted fields.", "error")
    return _form_page("admin/events/form.html", form=form, post=post, is_new=is_new)


@bp.route("/events/new", methods=["GET", "POST"])
def post_new():
    form = PostForm()
    if request.method == "GET" and request.args.get("kind") in {k.value for k in PostKind}:
        form.kind.data = request.args["kind"]
    return _post_view(ContentPost(), form, True)


@bp.route("/events/<int:post_id>/edit", methods=["GET", "POST"])
def post_edit(post_id):
    post = db.session.get(ContentPost, post_id) or abort(404)
    form = PostForm(obj=post)
    if request.method == "GET":
        form.kind.data = post.kind.value
        form.publication_status.data = (PublicationStatus.DRAFT.value if post.is_archived_content
                                        else post.publication_status.value)
        preload_media_slot(form, "cover_image", post.cover_image)
        preload_media_slot(form, "video", post.video)
    return _post_view(post, form, False)


@bp.route("/events/<int:post_id>/preview")
def post_preview(post_id):
    from app.public.routes import render_post_page

    post = db.session.get(ContentPost, post_id) or abort(404)
    return render_post_page(post, preview=True)


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

@bp.route("/services")
def services():
    stmt, q, visibility = _list_filters(Service, [Service.name, Service.short_description])
    items = db.session.scalars(stmt.options(selectinload(Service.image)).order_by(Service.position, Service.name)).all()
    return render_template("admin/content/services.html", items=items, q=q, visibility=visibility,
                           visibilities=list(PublicationStatus), action_form=ConfirmForm())


def _service_view(service, form, is_new):
    if form.validate_on_submit():
        try:
            with UploadBatch() as batch:
                service.name = form.name.data.strip()
                service.slug = slug_for(Service, None, service.name, exclude_id=service.id)
                service.short_description = form.short_description.data.strip()
                service.description = (form.description.data or "").strip()
                service.image = media_slot(batch, form, "image", IMAGE, alt_text=service.name)
                service.position = form.position.data or 0
                service.is_sample = False if not is_new else service.is_sample
                publishing_service.set_status(service, form.publication_status.data)
                db.session.add(service)
                db.session.commit()
        except MediaValidationError as exc:
            flash(str(exc), "error")
        else:
            flash_saved("Service", service)
            return redirect(url_for("admin.services"))
    return _form_page("admin/content/form.html", form=form, obj=service, is_new=is_new, noun="service",
                      list_endpoint="admin.services", sections=[
                          ("Service", ["name", "short_description", "description"]),
                          ("Image", ["image"]),
                          ("Display", ["position", "publication_status"]),
                      ])


@bp.route("/services/new", methods=["GET", "POST"])
def service_new():
    return _service_view(Service(), ServiceForm(), True)


@bp.route("/services/<int:item_id>/edit", methods=["GET", "POST"])
def service_edit(item_id):
    service = db.session.get(Service, item_id) or abort(404)
    form = ServiceForm(obj=service)
    if request.method == "GET":
        form.publication_status.data = (PublicationStatus.DRAFT.value if service.is_archived_content
                                        else service.publication_status.value)
        preload_media_slot(form, "image", service.image)
    return _service_view(service, form, False)


# ---------------------------------------------------------------------------
# Awards and certifications
# ---------------------------------------------------------------------------

@bp.route("/awards")
def awards():
    stmt, q, visibility = _list_filters(Award, [Award.title, Award.issuer])
    items = db.session.scalars(stmt.options(selectinload(Award.image))
                               .order_by(Award.position, Award.year.desc(), Award.id.desc())).all()
    return render_template("admin/content/awards.html", items=items, q=q, visibility=visibility,
                           visibilities=list(PublicationStatus), action_form=ConfirmForm())


def _award_view(award, form, is_new):
    if form.validate_on_submit():
        try:
            with UploadBatch() as batch:
                award.title = form.title.data.strip()
                award.issuer = form.issuer.data.strip()
                award.year = form.year.data
                award.description = (form.description.data or "").strip()
                award.image = media_slot(batch, form, "image", IMAGE, alt_text=award.title)
                award.document = media_slot(batch, form, "document", DOCUMENT)
                award.position = form.position.data or 0
                publishing_service.set_status(award, form.publication_status.data)
                db.session.add(award)
                db.session.commit()
        except MediaValidationError as exc:
            flash(str(exc), "error")
        else:
            flash_saved("Award", award)
            return redirect(url_for("admin.awards"))
    return _form_page("admin/content/form.html", form=form, obj=award, is_new=is_new, noun="award or certification",
                      list_endpoint="admin.awards",
                      notice="Only add awards, certifications and registrations the company actually holds. "
                             "Upload the certificate where possible.",
                      sections=[
                          ("Details", ["title", "issuer", "year", "description"]),
                          ("Image and document", ["image", "document"]),
                          ("Display", ["position", "publication_status"]),
                      ])


@bp.route("/awards/new", methods=["GET", "POST"])
def award_new():
    return _award_view(Award(), AwardForm(), True)


@bp.route("/awards/<int:item_id>/edit", methods=["GET", "POST"])
def award_edit(item_id):
    award = db.session.get(Award, item_id) or abort(404)
    form = AwardForm(obj=award)
    if request.method == "GET":
        form.publication_status.data = (PublicationStatus.DRAFT.value if award.is_archived_content
                                        else award.publication_status.value)
        preload_media_slot(form, "image", award.image)
        preload_media_slot(form, "document", award.document)
    return _award_view(award, form, False)


# ---------------------------------------------------------------------------
# Testimonials
# ---------------------------------------------------------------------------

@bp.route("/testimonials")
def testimonials():
    stmt, q, visibility = _list_filters(Testimonial, [Testimonial.client_name, Testimonial.organization,
                                                      Testimonial.quote])
    items = db.session.scalars(stmt.options(selectinload(Testimonial.portrait))
                               .order_by(Testimonial.position, Testimonial.id.desc())).all()
    return render_template("admin/content/testimonials.html", items=items, q=q, visibility=visibility,
                           visibilities=list(PublicationStatus), action_form=ConfirmForm())


def _project_choices():
    rows = db.session.execute(select(Project.id, Project.name)
                              .where(Project.publication_status != PublicationStatus.ARCHIVED)
                              .order_by(Project.name)).all()
    return [(0, "— None —")] + [(r.id, r.name) for r in rows]


def _testimonial_view(item, form, is_new):
    form.project_id.choices = _project_choices()
    if form.validate_on_submit():
        try:
            with UploadBatch() as batch:
                item.client_name = form.client_name.data.strip()
                item.client_role = (form.client_role.data or "").strip() or None
                item.organization = (form.organization.data or "").strip() or None
                item.quote = form.quote.data.strip()
                item.portrait = media_slot(batch, form, "portrait", IMAGE, alt_text=item.client_name)
                item.project_id = form.project_id.data or None
                item.client_approved = form.client_approved.data
                item.position = form.position.data or 0
                publishing_service.set_status(item, form.publication_status.data)
                db.session.add(item)
                db.session.commit()
        except MediaValidationError as exc:
            flash(str(exc), "error")
        else:
            flash_saved("Testimonial", item)
            return redirect(url_for("admin.testimonials"))
    return _form_page("admin/content/form.html", form=form, obj=item, is_new=is_new, noun="testimonial",
                      list_endpoint="admin.testimonials",
                      notice="Only publish statements the client actually gave and approved for use.",
                      sections=[
                          ("Client", ["client_name", "client_role", "organization", "portrait"]),
                          ("Testimonial", ["quote", "project_id", "client_approved"]),
                          ("Display", ["position", "publication_status"]),
                      ])


@bp.route("/testimonials/new", methods=["GET", "POST"])
def testimonial_new():
    return _testimonial_view(Testimonial(), TestimonialForm(), True)


@bp.route("/testimonials/<int:item_id>/edit", methods=["GET", "POST"])
def testimonial_edit(item_id):
    item = db.session.get(Testimonial, item_id) or abort(404)
    form = TestimonialForm(obj=item)
    if request.method == "GET":
        form.project_id.data = item.project_id or 0
        form.publication_status.data = (PublicationStatus.DRAFT.value if item.is_archived_content
                                        else item.publication_status.value)
        preload_media_slot(form, "portrait", item.portrait)
    return _testimonial_view(item, form, False)


__all__ = ["current_user"]
