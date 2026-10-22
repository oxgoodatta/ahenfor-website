from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.admin import bp
from app.admin.forms import ConfirmForm, ProjectForm
from app.admin.helpers import (
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
from app.models import Project, ProjectStatus, PublicationStatus
from app.services import publishing_service
from app.services.media_service import MediaValidationError, UploadBatch


def get_project_or_404(project_id):
    project = db.session.get(Project, project_id)
    if project is None:
        abort(404)
    return project


@bp.route("/projects")
def projects():
    q = (request.args.get("q") or "").strip()
    status = request.args.get("status") or ""
    visibility = request.args.get("visibility") or ""
    stmt = select(Project).options(selectinload(Project.cover_image))
    if q:
        like = f"%{q[:100]}%"
        stmt = stmt.where(or_(Project.name.ilike(like), Project.location.ilike(like),
                              Project.reference_code.ilike(like)))
    if status in {s.value for s in ProjectStatus}:
        stmt = stmt.where(Project.status == status)
    if visibility in {s.value for s in PublicationStatus}:
        stmt = stmt.where(Project.publication_status == visibility)
    else:
        stmt = stmt.where(Project.publication_status != PublicationStatus.ARCHIVED)
    pagination = paginate(stmt.order_by(Project.updated_at.desc(), Project.id.desc()))
    return render_template(
        "admin/projects/list.html", pagination=pagination, projects=pagination.items,
        q=q, status=status, visibility=visibility, statuses=list(ProjectStatus),
        visibilities=list(PublicationStatus), action_form=ConfirmForm(),
    )


def _save_project(form, project):
    """Copy the form onto ``project`` and resolve its media inside one upload batch."""
    with UploadBatch() as batch:
        project.name = form.name.data.strip()
        project.slug = slug_for(Project, form.slug.data, project.name, exclude_id=project.id)
        project.reference_code = (form.reference_code.data or "").strip() or None
        project.location = form.location.data.strip()
        project.category = form.category.data
        project.short_description = form.short_description.data.strip()
        project.description = (form.description.data or "").strip()
        project.status = form.status.data
        project.progress_percent = form.progress_percent.data
        project.start_date = form.start_date.data
        project.estimated_completion_date = form.estimated_completion_date.data
        project.actual_completion_date = form.actual_completion_date.data
        project.client_name = (form.client_name.data or "").strip() or None
        project.show_client = bool(form.show_client.data and project.client_name)
        project.project_value = (form.project_value.data or "").strip() or None
        project.show_value = bool(form.show_value.data and project.project_value)
        project.is_featured = form.is_featured.data
        project.featured_order = form.featured_order.data or 0
        alt = (form.cover_image_alt.data or "").strip()
        project.cover_image = media_slot(batch, form, "cover_image", IMAGE, alt_text=alt or project.name)
        if project.cover_image is not None and alt:
            project.cover_image.alt_text = alt
        project.cover_video = media_slot(batch, form, "cover_video", VIDEO)
        publishing_service.set_status(project, form.publication_status.data)
        if project.id is None:
            db.session.add(project)
        db.session.commit()


def _duplicate_reference(form, project):
    code = (form.reference_code.data or "").strip()
    if not code:
        return False
    stmt = select(Project.id).where(Project.reference_code == code)
    if project.id:
        stmt = stmt.where(Project.id != project.id)
    if db.session.scalar(stmt):
        form.reference_code.errors = list(form.reference_code.errors) + ["Another project uses this reference."]
        return True
    return False


def _project_form_view(project, form, is_new):
    if form.validate_on_submit() and not _duplicate_reference(form, project):
        try:
            _save_project(form, project)
        except MediaValidationError as exc:
            flash(str(exc), "error")
        else:
            flash_saved("Project", project)
            return redirect(url_for("admin.project_progress", project_id=project.id))
    elif request.method == "POST":
        flash("Please correct the highlighted fields.", "error")
    return render_template("admin/projects/form.html", form=form, project=project, is_new=is_new)


@bp.route("/projects/new", methods=["GET", "POST"])
def project_new():
    project = Project()
    form = ProjectForm()
    return _project_form_view(project, form, is_new=True)


@bp.route("/projects/<int:project_id>")
def project_detail(project_id):
    get_project_or_404(project_id)
    return redirect(url_for("admin.project_progress", project_id=project_id))


@bp.route("/projects/<int:project_id>/edit", methods=["GET", "POST"])
def project_edit(project_id):
    project = get_project_or_404(project_id)
    form = ProjectForm(obj=project)
    if request.method == "GET":
        form.publication_status.data = (
            PublicationStatus.DRAFT.value if project.publication_status == PublicationStatus.ARCHIVED
            else project.publication_status.value
        )
        form.status.data = project.status.value
        form.cover_image_alt.data = project.cover_image.alt_text if project.cover_image else ""
        preload_media_slot(form, "cover_image", project.cover_image)
        preload_media_slot(form, "cover_video", project.cover_video)
    return _project_form_view(project, form, is_new=False)


@bp.route("/projects/<int:project_id>/preview")
def project_preview(project_id):
    from app.public.routes import render_project_page

    return render_project_page(get_project_or_404(project_id), preview=True)


@bp.route("/projects/<int:project_id>/feature", methods=["POST"])
def project_feature(project_id):
    project = get_project_or_404(project_id)
    if ConfirmForm().validate_on_submit():
        project.is_featured = not project.is_featured
        db.session.commit()
        flash(f"“{project.name}” is {'now' if project.is_featured else 'no longer'} featured.", "success")
    return redirect_back("admin.projects")
