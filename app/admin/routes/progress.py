"""Construction progress manager: phases and dated progress updates."""
from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.admin import bp
from app.admin.forms import ConfirmForm, PhaseForm, ProgressUpdateForm
from app.admin.helpers import IMAGE, VIDEO, media_slot, preload_media_slot
from app.admin.routes.projects import get_project_or_404
from app.extensions import db
from app.models import (
    PhaseStatus,
    ProgressUpdate,
    ProgressUpdateMedia,
    Project,
    ProjectPhase,
    PublicationStatus,
)
from app.models.base import utcnow
from app.services import project_service, publishing_service
from app.services.media_service import MediaValidationError, UploadBatch, get_selectable

MAX_PHOTOS_PER_UPDATE = 60


def _phase_or_404(project, phase_id):
    phase = db.session.get(ProjectPhase, phase_id)
    if phase is None or phase.project_id != project.id:
        abort(404)
    return phase


def _update_or_404(update_id):
    update = db.session.get(ProgressUpdate, update_id)
    if update is None:
        abort(404)
    return update


@bp.route("/projects/<int:project_id>/progress")
def project_progress(project_id):
    project = db.session.scalar(
        select(Project).where(Project.id == project_id).options(
            selectinload(Project.cover_image),
            selectinload(Project.phases).selectinload(ProjectPhase.updates)
            .selectinload(ProgressUpdate.media_items).selectinload(ProgressUpdateMedia.media),
        )
    )
    if project is None:
        abort(404)
    phases = project_service.ordered_phases(project)
    active = [p for p in phases if not p.is_archived]
    archived = [p for p in phases if p.is_archived]
    all_updates = [u for p in active for u in p.updates if u.publication_status != PublicationStatus.ARCHIVED]
    latest = max(all_updates, key=lambda u: (u.update_date, u.id)) if all_updates else None
    return render_template(
        "admin/projects/progress.html", project=project, phases=active, archived_phases=archived,
        latest=latest, action_form=ConfirmForm(), PublicationStatus=PublicationStatus,
    )


# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------

def _apply_phase(form, phase):
    phase.title = form.title.data.strip()
    phase.description = (form.description.data or "").strip()
    phase.status = form.status.data
    phase.start_date = form.start_date.data
    phase.completed_date = form.completed_date.data


@bp.route("/projects/<int:project_id>/phases/new", methods=["GET", "POST"])
def phase_new(project_id):
    project = get_project_or_404(project_id)
    form = PhaseForm()
    if form.validate_on_submit():
        phase = ProjectPhase(project=project, position=project_service.next_phase_position(project))
        _apply_phase(form, phase)
        db.session.add(phase)
        db.session.commit()
        flash(f"Phase “{phase.title}” added.", "success")
        return redirect(url_for("admin.project_progress", project_id=project.id, _anchor=f"phase-{phase.id}"))
    return render_template("admin/projects/phase_form.html", form=form, project=project, phase=None)


@bp.route("/projects/<int:project_id>/phases/<int:phase_id>/edit", methods=["GET", "POST"])
def phase_edit(project_id, phase_id):
    project = get_project_or_404(project_id)
    phase = _phase_or_404(project, phase_id)
    form = PhaseForm(obj=phase)
    if request.method == "GET":
        form.status.data = phase.status.value
    if form.validate_on_submit():
        _apply_phase(form, phase)
        db.session.commit()
        flash(f"Phase “{phase.title}” updated.", "success")
        return redirect(url_for("admin.project_progress", project_id=project.id, _anchor=f"phase-{phase.id}"))
    return render_template("admin/projects/phase_form.html", form=form, project=project, phase=phase)


@bp.route("/projects/<int:project_id>/phases/defaults", methods=["POST"])
def phase_defaults(project_id):
    project = get_project_or_404(project_id)
    if ConfirmForm().validate_on_submit():
        added = project_service.add_default_phases(project)
        db.session.commit()
        flash(f"{added} suggested phase{'s' if added != 1 else ''} added. Rename, reorder or archive any that "
              "don't apply." if added else "All suggested phases already exist.", "success")
    return redirect(url_for("admin.project_progress", project_id=project.id))


@bp.route("/projects/<int:project_id>/phases/<int:phase_id>/move", methods=["POST"])
def phase_move(project_id, phase_id):
    project = get_project_or_404(project_id)
    phase = _phase_or_404(project, phase_id)
    direction = -1 if request.form.get("direction") == "up" else 1
    if ConfirmForm().validate_on_submit() and not phase.is_archived:
        if project_service.move_phase(phase, direction):
            db.session.commit()
    return redirect(url_for("admin.project_progress", project_id=project.id, _anchor=f"phase-{phase.id}"))


@bp.route("/projects/<int:project_id>/phases/reorder", methods=["POST"])
def phase_reorder(project_id):
    project = get_project_or_404(project_id)
    if ConfirmForm().validate_on_submit():
        try:
            ids = [int(v) for v in request.form.get("order", "").split(",") if v.strip()]
            project_service.reorder_phases(project, ids)
        except ValueError:
            flash("The phase order could not be saved. Reload the page and try again.", "error")
        else:
            db.session.commit()
            flash("Phase order saved.", "success")
    return redirect(url_for("admin.project_progress", project_id=project.id))


@bp.route("/projects/<int:project_id>/phases/<int:phase_id>/archive", methods=["POST"])
def phase_archive(project_id, phase_id):
    project = get_project_or_404(project_id)
    phase = _phase_or_404(project, phase_id)
    if ConfirmForm().validate_on_submit():
        phase.is_archived = request.form.get("restore") != "1"
        if not phase.is_archived:
            phase.position = project_service.next_phase_position(project)
        db.session.commit()
        flash(f"Phase “{phase.title}” {'archived. Its updates are hidden from the website but kept' if phase.is_archived else 'restored'}.",
              "success")
    return redirect(url_for("admin.project_progress", project_id=project.id))


# ---------------------------------------------------------------------------
# Progress updates
# ---------------------------------------------------------------------------

def _phase_choices(project, include=None):
    phases = [p for p in project_service.ordered_phases(project) if not p.is_archived or p is include]
    return [(p.id, f"{i + 1}. {p.title}" + (" (archived)" if p.is_archived else "")) for i, p in enumerate(phases)]


def _submitted_gallery():
    """Read the ordered photo list posted by the update form."""
    ids = request.form.getlist("media_id")
    captions = request.form.getlist("media_caption")
    alts = request.form.getlist("media_alt")
    if len(ids) > MAX_PHOTOS_PER_UPDATE:
        raise MediaValidationError(f"An update can hold at most {MAX_PHOTOS_PER_UPDATE} photos.")
    entries = []
    for i, raw in enumerate(ids):
        asset = get_selectable(raw, IMAGE)
        entries.append((asset, captions[i] if i < len(captions) else "", alts[i] if i < len(alts) else ""))
    return entries


def _gallery_for_template(update, submitted=None):
    if submitted is not None:
        return [{"media": a, "caption": c, "alt": t} for a, c, t in submitted]
    if update is None:
        return []
    return [{"media": m.media, "caption": m.caption, "alt": m.alt_text} for m in update.media_items]


def _update_form_view(project, update, form, is_new):
    form.phase_id.choices = _phase_choices(project, include=update.phase if update else None)
    submitted = None
    if form.validate_on_submit():
        phase = _phase_or_404(project, form.phase_id.data)
        try:
            with UploadBatch() as batch:
                submitted = _submitted_gallery()
                for file in (form.photos.data or []):
                    if file and getattr(file, "filename", ""):
                        submitted.append((batch.store(file, profile="image", user=current_user), "", ""))
                if len(submitted) > MAX_PHOTOS_PER_UPDATE:
                    raise MediaValidationError(f"An update can hold at most {MAX_PHOTOS_PER_UPDATE} photos.")
                target = update or ProgressUpdate(created_by_id=current_user.id)
                target.phase = phase
                target.title = form.title.data.strip()
                target.update_date = form.update_date.data
                target.body = (form.body.data or "").strip()
                target.video = media_slot(batch, form, "video", VIDEO)
                project_service.apply_update_media(target, submitted)
                publishing_service.set_status(target, form.publication_status.data)
                project.updated_at = utcnow()  # "last updated" in lists and the sitemap
                db.session.add(target)
                db.session.commit()
        except MediaValidationError as exc:
            flash(str(exc), "error")
            try:
                submitted = _submitted_gallery()
            except MediaValidationError:
                submitted = None
        else:
            state = "published" if target.is_published else "saved as a draft"
            note = "" if project.is_published or not target.is_published else \
                " It will appear on the website once the project itself is published."
            flash(f"Progress update {state} with {len(target.media_items)} photo"
                  f"{'s' if len(target.media_items) != 1 else ''}.{note}", "success")
            return redirect(url_for("admin.project_progress", project_id=project.id, _anchor=f"update-{target.id}"))
    elif request.method == "POST":
        flash("Please correct the highlighted fields.", "error")
        try:
            submitted = _submitted_gallery()
        except MediaValidationError:
            submitted = None
    phases_by_id = {p.id: p.title for p in project.phases}
    return render_template(
        "admin/projects/update_form.html", form=form, project=project, update=update, is_new=is_new,
        gallery=_gallery_for_template(update, submitted), phases_by_id=phases_by_id,
        max_photos=MAX_PHOTOS_PER_UPDATE,
    )


@bp.route("/projects/<int:project_id>/updates/new", methods=["GET", "POST"])
def update_new(project_id):
    project = get_project_or_404(project_id)
    if not any(not p.is_archived for p in project.phases):
        flash("Add a construction phase first. Updates are filed under a phase.", "warning")
        return redirect(url_for("admin.phase_new", project_id=project.id))
    form = ProgressUpdateForm()
    if request.method == "GET":
        requested = request.args.get("phase_id", type=int)
        active = [p for p in project_service.ordered_phases(project) if not p.is_archived]
        preferred = next((p for p in active if p.id == requested), None) or next(
            (p for p in active if p.status == PhaseStatus.IN_PROGRESS), active[0])
        form.phase_id.data = preferred.id
    return _update_form_view(project, None, form, is_new=True)


@bp.route("/updates/<int:update_id>/edit", methods=["GET", "POST"])
def update_edit(update_id):
    update = _update_or_404(update_id)
    project = update.phase.project
    form = ProgressUpdateForm(obj=update)
    if request.method == "GET":
        form.publication_status.data = (
            PublicationStatus.DRAFT.value if update.publication_status == PublicationStatus.ARCHIVED
            else update.publication_status.value
        )
        preload_media_slot(form, "video", update.video)
    return _update_form_view(project, update, form, is_new=False)


@bp.route("/updates/<int:update_id>/preview")
def update_preview(update_id):
    update = _update_or_404(update_id)
    return redirect(url_for("admin.project_preview", project_id=update.phase.project_id,
                            _anchor=f"update-{update.id}"))
