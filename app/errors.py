from flask import jsonify, render_template, request

from app.extensions import db


def register_error_handlers(app):
    @app.errorhandler(404)
    def handle_not_found(error):
        if request.path.startswith("/transactions"):
            return jsonify({"error": "Not found."}), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def handle_server_error(error):
        db.session.rollback()
        if request.path.startswith("/transactions"):
            return jsonify({"error": "An unexpected error occurred. Please try again."}), 500
        return render_template("errors/500.html"), 500
