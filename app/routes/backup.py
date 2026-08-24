"""Backup export/import, rendered as part of the Settings page. See
specs.md's "Backup / import-export" section.
"""
import json
from datetime import date

from flask import Blueprint, Response, flash, redirect, request, url_for

from app.routes.auth import login_required
from app.services.backup import build_snapshot, restore_snapshot, validate_snapshot

backup_bp = Blueprint("backup", __name__, url_prefix="/settings/backup")


@backup_bp.route("", methods=["GET"])
@login_required
def download():
    snapshot = build_snapshot()
    filename = f"accntbl-backup-{date.today().isoformat()}.json"
    return Response(
        json.dumps(snapshot, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@backup_bp.route("/validate", methods=["POST"])
@login_required
def validate():
    file = request.files.get("backup_file")
    if file is None or not file.filename:
        return {"valid": False, "errors": ["Please choose a backup file."]}

    try:
        data = json.load(file.stream)
    except ValueError:
        return {"valid": False, "errors": ["Backup file is not valid JSON."]}

    errors = validate_snapshot(data)
    return {"valid": not errors, "errors": errors}


@backup_bp.route("/restore", methods=["POST"])
@login_required
def restore():
    file = request.files.get("backup_file")
    if file is None or not file.filename:
        flash("Please choose a backup file to restore.")
        return redirect(url_for("settings.index"))

    try:
        data = json.load(file.stream)
    except ValueError:
        flash("Backup file is not valid JSON.")
        return redirect(url_for("settings.index"))

    try:
        restore_snapshot(data)
    except ValueError as exc:
        flash(str(exc))
        return redirect(url_for("settings.index"))

    flash("Backup restored successfully.")
    return redirect(url_for("settings.index"))
