import enum
from datetime import datetime

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


class CreditCardSettings(db.Model):
    __tablename__ = "credit_card_settings"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    statement_close_day = db.Column(db.Integer, nullable=False)
    payment_due_offset_days = db.Column(db.Integer, nullable=False)
    starting_balance = db.Column(db.Numeric(12, 2), nullable=True)


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

    transactions = db.relationship("Transaction", back_populates="recurring_series")


class Transaction(db.Model):
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    cash_amount = db.Column(db.Numeric(12, 2), nullable=True)
    credit_amount = db.Column(db.Numeric(12, 2), nullable=True)
    date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    recurring_series_id = db.Column(
        db.Integer, db.ForeignKey("recurring_series.id"), nullable=True
    )
    occurrence_status = db.Column(
        db.Enum(OccurrenceStatus), nullable=True, default=None
    )

    recurring_series = db.relationship("RecurringSeries", back_populates="transactions")
