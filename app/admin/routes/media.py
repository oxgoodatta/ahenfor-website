"""Media library, asynchronous uploads and the homepage hero."""
from flask import abort, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user
from sqlalchemy import or_, select

from app.admin import bp
from app.admin.forms import ConfirmForm, HeroForm, MediaEditForm
from app.admin.helpers import IMAGE, VIDEO, media_slot, paginate, preload_media_slot
from app.extensions import db
from app.models import MediaAsset, MediaKind
from app.services import media_service, settings_service
from app.services.media_service import MediaInUseError, MediaValidationError, UploadBatch
from app.storage import StorageError, get_storage


def _asset_or_404(asset_id):
    asset = db.session.get(MediaAsset, asset_id)
    if asset is None:
        abort(404)
    return asset


def _library_stmt(kind=None, q=None, archived=False):
    stmt = select(MediaAsset).where(MediaAsset.is_private.is_(False), MediaAsset.is_archived.is_(archived))
    if kind in {k.value for k in MediaKind}:
        stmt = stmt.where(MediaAsset.kind == kind)
    if q:
        like = f"%{q[:100]}%"
        stmt = stmt.where(or_(MediaAsset.original_filename.ilike(like), MediaAsset.alt_text.ilike(like),
                              MediaAsset.caption.ilike(like)))
    return stmt.order_by(MediaAsset.created_at.desc(), MediaAsset.id.desc())


@bp.route("/media")
def media_library():
    kind = request.args.get("kind") or ""
    q = (request.args.get("q") or "").strip()
    archived = request.args.get("archived") == "1"
    pagination = paginate(_library_stmt(kind, q, archived), per_page=36)
    return render_template("admin/media/list.html", pagination=pagination, assets=pagination.items,
                           kind=kind, q=q, archived=archived, kinds=list(MediaKind))


@bp.route("/media/library.json")
def media_library_json():
    """Data for the 'Choose from library' picker."""
    kind = request.args.get("kind") or "image"
    pagination = paginate(_library_stmt(kind, (request.args.get("q") or "").strip()), per_page=48)
    return jsonify({
        "ok": True,
        "items": [a.to_dict() for a in pagination.items],
        "page": pagination.page,
        "pages": pagination.pages,
    })


@bp.route("/media/upload", methods=["POST"])
def media_upload():
    """Asynchronous single-file upload used by the admin JavaScript (CSRF via X-CSRFToken)."""
    profile = request.form.get("profile", "image")
    if profile not in ("image", "video", "document"):
        return jsonify({"ok": False, "error": "Unsupported upload type."}), 400
    file = request.files.get("file")
    try:
        with UploadBatch() as batch:
            asset = batch.store(
                file, profile=profile, user=current_user,
                alt_text=(request.form.get("alt_text") or "").strip(),
            )
            db.session.commit()
    except MediaValidationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "asset": asset.to_dict()}), 201


@bp.route("/media/<int:asset_id>", methods=["GET", "POST"])
def media_detail(asset_id):
    asset = _asset_or_404(asset_id)
    if asset.is_private:
        abort(404)  # private files (inquiry attachments) are managed from their inquiry
    form = MediaEditForm(obj=asset)
    if form.validate_on_submit():
        asset.alt_text = (form.alt_text.data or "").strip()
        asset.caption = (form.caption.data or "").strip()
        db.session.commit()
        flash("Media details saved.", "success")
        return redirect(url_for("admin.media_detail", asset_id=asset.id))
    return render_template("admin/media/detail.html", asset=asset, form=form,
                           references=media_service.references(asset), action_form=ConfirmForm())


@bp.route("/media/<int:asset_id>/archive", methods=["POST"])
def media_archive(asset_id):
    asset = _asset_or_404(asset_id)
    if ConfirmForm().validate_on_submit() and not asset.is_private:
        asset.is_archived = request.form.get("restore") != "1"
        db.session.commit()
        flash("Media archived. It stays visible wherever it is already used, but is hidden from the library."
              if asset.is_archived else "Media restored to the library.", "success")
    return redirect(url_for("admin.media_detail", asset_id=asset.id))


@bp.route("/media/<int:asset_id>/delete", methods=["POST"])
def media_delete(asset_id):
    asset = _asset_or_404(asset_id)
    if asset.is_private or not ConfirmForm().validate_on_submit():
        abort(400)
    try:
        media_service.purge(asset)
    except MediaInUseError as exc:
        flash("This file cannot be deleted because it is still used by: " + "; ".join(exc.references), "error")
        return redirect(url_for("admin.media_detail", asset_id=asset_id))
    flash("File permanently deleted.", "success")
    return redirect(url_for("admin.media_library"))


@bp.route("/media/<int:asset_id>/file")
def media_private_file(asset_id):
    """Authenticated access to any asset, including private inquiry attachments."""
    asset = _asset_or_404(asset_id)
    storage = get_storage()
    download_name = asset.original_filename or f"file-{asset.id}"
    if storage.is_local:
        try:
            path = storage.path_for(asset.storage_key)
        except StorageError:
            abort(404)
        if not path.is_file():
            abort(404)
        response = send_file(path, mimetype=asset.mime_type, as_attachment=True, download_name=download_name)
    else:
        response = redirect(storage.url(asset.storage_key, private=asset.is_private, expires=300))
    response.headers["Cache-Control"] = "no-store, private"
    return response


# ---------------------------------------------------------------------------
# Homepage hero
# ---------------------------------------------------------------------------

@bp.route("/media/hero", methods=["GET", "POST"])
def hero():
    draft = settings_service.get_hero("draft")
    published = settings_service.get_hero("published")
    db.session.commit()  # persist lazily-created rows
    form = HeroForm(obj=draft)
    if request.method == "GET":
        preload_media_slot(form, "image", draft.image)
        preload_media_slot(form, "video", draft.video)
        preload_media_slot(form, "poster", draft.poster)
    if form.validate_on_submit():
        try:
            with UploadBatch() as batch:
                image = media_slot(batch, form, "image", IMAGE, alt_text=form.alt_text.data or "")
                video = media_slot(batch, form, "video", VIDEO)
                poster = media_slot(batch, form, "poster", IMAGE)
                if form.media_type.data == "video" and video is None:
                    raise MediaValidationError("Upload or choose a video, or switch the background type to Image.")
                draft.media_type = form.media_type.data
                draft.image, draft.video, draft.poster = image, video, poster
                for field in ("alt_text", "eyebrow", "headline", "subheadline", "primary_label",
                              "primary_target", "secondary_label", "secondary_target"):
                    setattr(draft, field, (getattr(form, field).data or "").strip())
                draft.updated_by_id = current_user.id
                db.session.commit()
        except MediaValidationError as exc:
            flash(str(exc), "error")
        else:
            if request.form.get("action") == "publish":
                settings_service.publish_hero(current_user)
                flash("Homepage hero published. The live homepage now shows these changes.", "success")
            else:
                flash("Draft saved. Preview it, then publish when ready.", "success")
            return redirect(url_for("admin.hero"))
    return render_template("admin/media/hero.html", form=form, draft=draft, published=published,
                           pending=settings_service.hero_has_unpublished_changes(), action_form=ConfirmForm())


@bp.route("/media/hero/publish", methods=["POST"])
def hero_publish():
    if ConfirmForm().validate_on_submit():
        settings_service.publish_hero(current_user)
        flash("Homepage hero published. The live homepage now shows these changes.", "success")
    return redirect(url_for("admin.hero"))


@bp.route("/media/hero/discard", methods=["POST"])
def hero_discard():
    if ConfirmForm().validate_on_submit():
        draft = settings_service.get_hero("draft")
        published = settings_service.get_hero("published")
        for field in draft.COPY_FIELDS:
            setattr(draft, field, getattr(published, field))
        db.session.commit()
        flash("Draft changes discarded.", "success")
    return redirect(url_for("admin.hero"))


@bp.route("/media/hero/preview")
def hero_preview():
    from app.public.routes import home_context

    draft = settings_service.get_hero("draft")
    return render_template("public/home.html", hero=draft, preview=True, **home_context())


__all__ = ["MediaKind"]
