from flask import abort, flash, redirect, render_template, request, url_for
from sqlalchemy import or_, select

from app.admin import bp
from app.admin.forms import InquiryForm
from app.admin.helpers import paginate
from app.extensions import db
from app.models import Inquiry, InquiryKind, InquiryStatus


@bp.route("/inquiries")
def inquiries():
    q = (request.args.get("q") or "").strip()
    status = request.args.get("status") or ""
    kind = request.args.get("kind") or ""
    stmt = select(Inquiry)
    if q:
        like = f"%{q[:100]}%"
        stmt = stmt.where(or_(Inquiry.full_name.ilike(like), Inquiry.email.ilike(like),
                              Inquiry.organization.ilike(like), Inquiry.project_location.ilike(like)))
    if status in {s.value for s in InquiryStatus}:
        stmt = stmt.where(Inquiry.status == status)
    if kind in {k.value for k in InquiryKind}:
        stmt = stmt.where(Inquiry.kind == kind)
    pagination = paginate(stmt.order_by(Inquiry.created_at.desc(), Inquiry.id.desc()))
    return render_template("admin/inquiries/list.html", pagination=pagination, inquiries=pagination.items,
                           q=q, status=status, kind=kind, statuses=list(InquiryStatus), kinds=list(InquiryKind))


@bp.route("/inquiries/<int:inquiry_id>", methods=["GET", "POST"])
def inquiry_detail(inquiry_id):
    inquiry = db.session.get(Inquiry, inquiry_id) or abort(404)
    form = InquiryForm(obj=inquiry)
    if request.method == "GET":
        form.status.data = inquiry.status.value
    if form.validate_on_submit():
        inquiry.status = form.status.data
        inquiry.internal_notes = (form.internal_notes.data or "").strip()
        db.session.commit()
        flash("Inquiry updated.", "success")
        return redirect(url_for("admin.inquiry_detail", inquiry_id=inquiry.id))
    return render_template("admin/inquiries/detail.html", inquiry=inquiry, form=form)
