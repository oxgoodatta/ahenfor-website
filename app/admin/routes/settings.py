from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user

from app.admin import bp
from app.admin.forms import PasswordChangeForm, build_settings_form
from app.admin.helpers import IMAGE, media_slot
from app.extensions import db
from app.services import settings_service
from app.services.media_service import MediaValidationError, UploadBatch


@bp.route("/settings", methods=["GET", "POST"])
def settings():
    group = request.args.get("group", "company")
    if group not in settings_service.GROUPS:
        abort(404)
    definitions = [d for d in settings_service.REGISTRY if d.group == group]
    values = settings_service.load_values()
    form = build_settings_form(definitions, values)()
    if form.validate_on_submit():
        updates = {}
        try:
            with UploadBatch() as batch:
                for d in definitions:
                    if d.kind == "media":
                        asset = media_slot(batch, form, d.key, IMAGE)
                        updates[d.key] = str(asset.id) if asset else ""
                    else:
                        data = getattr(form, d.key).data
                        updates[d.key] = "" if data is None else str(data)
                settings_service.save(updates)
                db.session.commit()
        except MediaValidationError as exc:
            flash(str(exc), "error")
        else:
            flash(f"{settings_service.GROUPS[group]} saved. The website now uses the new values.", "success")
            return redirect(url_for("admin.settings", group=group))
    elif request.method == "POST":
        flash("Please correct the highlighted fields.", "error")
    media_values = {d.key: settings_service.site().media(d.key) for d in definitions if d.kind == "media"}
    return render_template("admin/settings/index.html", form=form, group=group, groups=settings_service.GROUPS,
                           definitions=definitions, media_values=media_values, values=values)


@bp.route("/content/company")
def company():
    return redirect(url_for("admin.settings", group="company"))


@bp.route("/account", methods=["GET", "POST"])
def account():
    form = PasswordChangeForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            form.current_password.errors = ["Current password is incorrect."]
        else:
            current_user.set_password(form.new_password.data)
            db.session.commit()
            login_user(current_user)  # new session token; other sessions are signed out
            flash("Password changed. Other signed-in sessions have been signed out.", "success")
            return redirect(url_for("admin.account"))
    return render_template("admin/settings/account.html", form=form)
