from datetime import date, timedelta
from decimal import Decimal

import click
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import (
    CadenceType,
    CheckingAccount,
    CreditCard,
    Kind,
    OccurrenceStatus,
    RecurringSeries,
    Transaction,
    User,
)
from app.services.credit_card import compute_starting_balance_due_date
from app.services.recurring import generate_occurrences


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


@click.command("seed-demo-data")
def seed_demo_data_command():
    """Populate a fresh dev database with sample accounts/transactions.

    Refuses to run if any checking account already exists, so it can't be
    run twice against real data by accident.
    """
    if CheckingAccount.query.first() is not None:
        click.echo("Checking accounts already exist; skipping seed.")
        return

    today = date.today()

    db.session.add(
        CheckingAccount(
            name="Primary Checking",
            starting_balance=Decimal("2500.00"),
            as_of_date=today,
        )
    )
    default_card = CreditCard(
        id=1,
        name="Default Credit Card",
        is_default=True,
        statement_close_day=20,
        payment_due_offset_days=15,
        starting_balance=Decimal("-340.00"),
        starting_balance_due_date=compute_starting_balance_due_date(20, 15, today=today),
    )
    db.session.add(default_card)
    rewards_card = CreditCard(
        id=2,
        name="Rewards Visa",
        is_default=False,
        statement_close_day=5,
        payment_due_offset_days=21,
        starting_balance=Decimal("-125.50"),
        starting_balance_due_date=compute_starting_balance_due_date(5, 21, today=today),
    )
    db.session.add(rewards_card)

    horizon = today + timedelta(days=365)
    series_specs = [
        dict(
            name="Paycheck",
            kind=Kind.cash,
            amount=Decimal("2100.00"),
            cadence_type=CadenceType.biweekly,
            start_date=today - timedelta(days=60),
        ),
        dict(
            name="Rent",
            kind=Kind.cash,
            amount=Decimal("-1500.00"),
            cadence_type=CadenceType.monthly,
            start_date=today.replace(day=1),
        ),
        dict(
            name="Streaming subscription",
            kind=Kind.credit,
            amount=Decimal("-15.99"),
            cadence_type=CadenceType.monthly,
            start_date=today.replace(day=1),
            credit_card=default_card,
        ),
        dict(
            name="Gym membership",
            kind=Kind.credit,
            amount=Decimal("-45.00"),
            cadence_type=CadenceType.monthly,
            start_date=today.replace(day=1),
            credit_card=rewards_card,
        ),
    ]

    for spec in series_specs:
        series = RecurringSeries(
            cadence_type=spec["cadence_type"],
            custom_interval_value=None,
            custom_interval_unit=None,
            name=spec["name"],
            kind=spec["kind"],
            amount=spec["amount"],
            start_date=spec["start_date"],
            end_date=None,
            notes=None,
            credit_card_id=spec.get("credit_card").id if spec.get("credit_card") else None,
        )
        db.session.add(series)
        db.session.flush()

        for occurrence_date in generate_occurrences(series, spec["start_date"], horizon):
            db.session.add(
                Transaction(
                    name=series.name,
                    kind=series.kind,
                    amount=series.amount,
                    date=occurrence_date,
                    recurring_series_id=series.id,
                    occurrence_status=OccurrenceStatus.attached,
                    credit_card_id=series.credit_card_id,
                )
            )

    db.session.add(
        Transaction(
            name="Grocery run",
            kind=Kind.cash,
            amount=Decimal("-120.35"),
            date=today - timedelta(days=2),
        )
    )
    db.session.add(
        Transaction(
            name="Concert tickets",
            kind=Kind.credit,
            amount=Decimal("-89.00"),
            date=today + timedelta(days=5),
            credit_card_id=default_card.id,
        )
    )
    db.session.add(
        Transaction(
            name="New headphones",
            kind=Kind.credit,
            amount=Decimal("-199.00"),
            date=today - timedelta(days=3),
            credit_card_id=rewards_card.id,
        )
    )

    db.session.commit()
    click.echo("Seeded demo data.")


def register_cli(app):
    app.cli.add_command(create_user_command)
    app.cli.add_command(seed_demo_data_command)
