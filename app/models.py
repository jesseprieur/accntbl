import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import event

from app.extensions import db


class Kind(enum.Enum):
    cash = "cash"
    credit = "credit"


class CadenceType(enum.Enum):
    weekly = "weekly"
    biweekly = "biweekly"
    monthly = "monthly"
    semi_monthly = "semi_monthly"
    quarterly = "quarterly"
    yearly = "yearly"
    custom = "custom"


class CustomIntervalUnit(enum.Enum):
    days = "days"
    weeks = "weeks"
    months = "months"


class OccurrenceStatus(enum.Enum):
    attached = "attached"
    detached = "detached"
    skipped = "skipped"


class NeedsWantsSavings(enum.Enum):
    need = "need"
    want = "want"
    savings = "savings"


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)


class CheckingAccount(db.Model):
    __tablename__ = "checking_accounts"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    starting_balance = db.Column(db.Numeric(12, 2), nullable=False)
    as_of_date = db.Column(db.Date, nullable=False)


class CreditCard(db.Model):
    __tablename__ = "credit_cards"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    statement_close_day = db.Column(db.Integer, nullable=False)
    payment_due_offset_days = db.Column(db.Integer, nullable=False)
    starting_balance = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    # Due date the (immutable, set-at-creation) starting_balance is seeded
    # onto — see specs.md § `credit_cards` and services/credit_card.py's
    # `compute_starting_balance_due_date`.
    starting_balance_due_date = db.Column(db.Date, nullable=True)

    @classmethod
    def set_default(cls, card):
        """Mark `card` as the one default card, unsetting every other row.

        App-level enforcement (see specs.md § `credit_cards`): SQLite's
        partial-unique-index-on-boolean support is awkward via Alembic batch
        mode, so "exactly one default" is enforced here instead of a DB
        constraint.
        """
        cls.query.filter(cls.id != card.id).update({"is_default": False})
        card.is_default = True

    def deletion_blocker(self):
        """Return a reason this card can't be deleted, or None if it can.

        See specs.md § `credit_cards` for the three block conditions. The
        "only one card" check is ordered first since a lone card is always
        the default, and the default-specific message ("promote another
        card first") would be misleading/impossible in that case.
        """
        if CreditCard.query.count() <= 1:
            return "Cannot delete the last remaining credit card."
        if Transaction.query.filter_by(credit_card_id=self.id).count() > 0 or (
            RecurringSeries.query.filter_by(credit_card_id=self.id).count() > 0
        ):
            return (
                "Cannot delete a credit card that is still referenced by "
                "transactions or recurring series. Reassign them first."
            )
        if self.is_default:
            return "Cannot delete the default credit card. Promote another card to default first."
        return None


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)

    NONE_NAME = "None"

    @classmethod
    def none_category(cls):
        return cls.query.filter_by(name=cls.NONE_NAME).first()

    @classmethod
    def default_category_id(cls):
        """Python-side default for `category_id` columns — the seeded
        `None` category's id, resolved lazily so it works regardless of
        insertion order/id in a given database."""
        none_category = cls.none_category()
        return none_category.id if none_category else None

    def deletion_blocker(self):
        """Return a reason this category can't be deleted, or None if it can.

        Mirrors CreditCard.deletion_blocker (see specs.md § `categories`):
        the seeded `None` row is the permanent fallback default and any
        category still referenced by a transaction/series must be
        reassigned first.
        """
        if self.name == self.NONE_NAME:
            return "The None category is the default fallback and cannot be deleted."
        if Transaction.query.filter_by(category_id=self.id).count() > 0 or (
            RecurringSeries.query.filter_by(category_id=self.id).count() > 0
        ):
            return (
                "Cannot delete a category that is still referenced by "
                "transactions or recurring series. Reassign them first."
            )
        return None


@event.listens_for(Category.__table__, "after_create")
def _seed_none_category(target, connection, **kwargs):
    """Seed the `None` category whenever the table is freshly created via
    `db.create_all()` (dev/test setup) — Alembic migrations seed it via
    their own explicit `bulk_insert` instead, since `op.create_table` builds
    an ad-hoc table object that doesn't carry this event listener."""
    connection.execute(target.insert().values(name=Category.NONE_NAME))


class CreditDueOverride(db.Model):
    __tablename__ = "credit_due_overrides"
    __table_args__ = (
        db.UniqueConstraint("credit_card_id", "due_date", name="uq_credit_due_override_card_date"),
    )

    id = db.Column(db.Integer, primary_key=True)
    credit_card_id = db.Column(
        db.Integer, db.ForeignKey("credit_cards.id"), nullable=False
    )
    due_date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    notes = db.Column(db.Text, nullable=True)

    credit_card = db.relationship("CreditCard")


class RecurringSeries(db.Model):
    __tablename__ = "recurring_series"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    kind = db.Column(db.Enum(Kind), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    cadence_type = db.Column(db.Enum(CadenceType), nullable=False)
    custom_interval_value = db.Column(db.Integer, nullable=True)
    custom_interval_unit = db.Column(db.Enum(CustomIntervalUnit), nullable=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    credit_card_id = db.Column(
        db.Integer, db.ForeignKey("credit_cards.id"), nullable=True
    )
    amount_logic = db.Column(db.JSON, nullable=True)
    needs_wants_savings = db.Column(
        db.Enum(NeedsWantsSavings), nullable=False, default=NeedsWantsSavings.need
    )
    category_id = db.Column(
        db.Integer,
        db.ForeignKey("categories.id"),
        nullable=False,
        default=Category.default_category_id,
    )

    transactions = db.relationship("Transaction", back_populates="recurring_series")
    credit_card = db.relationship("CreditCard")
    category = db.relationship("Category")


class Transaction(db.Model):
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    kind = db.Column(db.Enum(Kind), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    recurring_series_id = db.Column(
        db.Integer, db.ForeignKey("recurring_series.id"), nullable=True
    )
    occurrence_status = db.Column(
        db.Enum(OccurrenceStatus), nullable=True, default=None
    )
    credit_card_id = db.Column(
        db.Integer, db.ForeignKey("credit_cards.id"), nullable=True
    )
    needs_wants_savings = db.Column(
        db.Enum(NeedsWantsSavings), nullable=False, default=NeedsWantsSavings.need
    )
    category_id = db.Column(
        db.Integer,
        db.ForeignKey("categories.id"),
        nullable=False,
        default=Category.default_category_id,
    )

    recurring_series = db.relationship("RecurringSeries", back_populates="transactions")
    credit_card = db.relationship("CreditCard")
    category = db.relationship("Category")
