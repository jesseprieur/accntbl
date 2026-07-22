from datetime import date

from flask import Blueprint, render_template

from app.auth import login_required

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
@login_required
def index():
    return render_template("index.html", today=date.today().isoformat())
