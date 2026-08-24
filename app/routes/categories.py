"""Category CRUD, rendered as part of the Settings page. See specs.md's
`categories` data model section and "Category icons".
"""
from flask import Blueprint, flash, redirect, request, url_for

from app.extensions import db
from app.models import CATEGORY_ICON_CHOICES, Category
from app.routes.auth import login_required

categories_bp = Blueprint("categories", __name__, url_prefix="/settings/categories")


def _parse_icon(value):
    icon = (value or "").strip()
    if not icon:
        return None
    if icon not in CATEGORY_ICON_CHOICES:
        raise ValueError("Invalid icon selection.")
    return icon


@categories_bp.route("", methods=["POST"])
@login_required
def create():
    try:
        name = request.form.get("name", "").strip()
        if not name:
            raise ValueError("Name is required.")
        if Category.query.filter_by(name=name).first() is not None:
            raise ValueError("A category with that name already exists.")
        icon = _parse_icon(request.form.get("icon"))

        db.session.add(Category(name=name, icon=icon))
        db.session.commit()
    except ValueError as exc:
        flash(str(exc))

    return redirect(url_for("settings.index"))


@categories_bp.route("/<int:category_id>", methods=["POST"])
@login_required
def update(category_id):
    category = Category.query.get_or_404(category_id)

    try:
        name = request.form.get("name", "").strip()
        if not name:
            raise ValueError("Name is required.")
        existing = Category.query.filter(
            Category.name == name, Category.id != category_id
        ).first()
        if existing is not None:
            raise ValueError("A category with that name already exists.")
        icon = _parse_icon(request.form.get("icon"))

        category.name = name
        category.icon = icon
        db.session.commit()
    except ValueError as exc:
        flash(str(exc))

    return redirect(url_for("settings.index"))


@categories_bp.route("/<int:category_id>/delete", methods=["POST"])
@login_required
def delete(category_id):
    category = Category.query.get_or_404(category_id)

    blocker = category.deletion_blocker()
    if blocker:
        flash(blocker)
    else:
        db.session.delete(category)
        db.session.commit()

    return redirect(url_for("settings.index"))
