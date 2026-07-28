from werkzeug.security import check_password_hash

import pytest

from app import create_app
from app.extensions import db
from app.models import CheckingAccount, CreditCard, Kind, RecurringSeries, Transaction, User


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def runner(app):
    return app.test_cli_runner()


def test_create_user_seeds_a_new_user(app, runner):
    result = runner.invoke(
        args=["create-user"],
        input="anita\nsecret123\nsecret123\n",
    )

    assert result.exit_code == 0
    with app.app_context():
        user = User.query.filter_by(username="anita").one()
        assert check_password_hash(user.password_hash, "secret123")


def test_create_user_resets_password_for_existing_username(app, runner):
    with app.app_context():
        db.session.add(User(username="anita", password_hash="stale-hash"))
        db.session.commit()

    result = runner.invoke(
        args=["create-user"],
        input="anita\nnewpassword\nnewpassword\n",
    )

    assert result.exit_code == 0
    with app.app_context():
        users = User.query.filter_by(username="anita").all()
        assert len(users) == 1
        assert check_password_hash(users[0].password_hash, "newpassword")


def test_create_user_requires_matching_password_confirmation(app, runner):
    result = runner.invoke(
        args=["create-user"],
        input="anita\nsecret123\nmismatch\n",
    )

    assert result.exit_code != 0
    with app.app_context():
        assert User.query.filter_by(username="anita").one_or_none() is None


def test_seed_demo_data_populates_accounts_series_and_transactions(app, runner):
    result = runner.invoke(args=["seed-demo-data"])

    assert result.exit_code == 0
    with app.app_context():
        assert CheckingAccount.query.count() == 1
        assert CreditCard.query.count() == 2
        assert CreditCard.query.filter_by(is_default=True).count() == 1
        assert RecurringSeries.query.count() == 4
        assert Transaction.query.count() > 4
        assert Transaction.query.filter_by(recurring_series_id=None).count() == 3

        default_card = CreditCard.query.filter_by(is_default=True).one()
        other_card = CreditCard.query.filter(CreditCard.id != default_card.id).one()

        credit_transactions = Transaction.query.filter_by(kind=Kind.credit).all()
        assert credit_transactions
        assert all(t.credit_card_id is not None for t in credit_transactions)
        assert {t.credit_card_id for t in credit_transactions} == {
            default_card.id,
            other_card.id,
        }

        credit_series = RecurringSeries.query.filter_by(kind=Kind.credit).all()
        assert credit_series
        assert all(s.credit_card_id is not None for s in credit_series)


def test_seed_demo_data_is_a_noop_when_checking_accounts_already_exist(app, runner):
    from datetime import date
    from decimal import Decimal

    with app.app_context():
        db.session.add(
            CheckingAccount(
                name="Existing", starting_balance=Decimal("1.00"), as_of_date=date.today()
            )
        )
        db.session.commit()

    result = runner.invoke(args=["seed-demo-data"])

    assert result.exit_code == 0
    with app.app_context():
        assert CheckingAccount.query.count() == 1
        assert RecurringSeries.query.count() == 0
        assert Transaction.query.count() == 0
