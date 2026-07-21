import click
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import User


@click.command("create-user")
@click.option("--username", prompt=True)
@click.option(
    "--password", prompt=True, hide_input=True, confirmation_prompt=True
)
def create_user_command(username, password):
    """Create the single app user, or reset their password if already seeded."""
    user = User.query.filter_by(username=username).one_or_none()
    if user is None:
        user = User(username=username)
        db.session.add(user)

    user.password_hash = generate_password_hash(password)
    db.session.commit()
    click.echo(f"User {username!r} saved.")


def register_cli(app):
    app.cli.add_command(create_user_command)
