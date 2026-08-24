"""create full schema

Revision ID: 8b1c4f9a2e3d
Revises:
Create Date: 2026-08-24 00:00:00.000000

Consolidates what used to be six incremental migrations (initial tables,
amount_logic, categories, nullable category_id, category icon, seeded
Uncategorized + not-null category_id) into the single schema a fresh
install actually needs. Deliberately keeps the same revision id as the
last of those six migrations: any database that already ran them is
already stamped at this id in its `alembic_version` table, so `flask db
upgrade` is a no-op for it, and any backup exported before this
consolidation still has a matching `schema_version` — see specs.md §
"Backup / import-export".
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8b1c4f9a2e3d'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'checking_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('starting_balance', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('as_of_date', sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'credit_cards',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False),
        sa.Column('statement_close_day', sa.Integer(), nullable=False),
        sa.Column('payment_due_offset_days', sa.Integer(), nullable=False),
        sa.Column('starting_balance', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0'),
        sa.Column('starting_balance_due_date', sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('icon', sa.String(length=64), nullable=True),
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_table(
        'recurring_series',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('kind', sa.Enum('cash', 'credit', name='kind'), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            'cadence_type',
            sa.Enum('weekly', 'biweekly', 'monthly', 'semi_monthly', 'quarterly', 'yearly', 'custom', name='cadencetype'),
            nullable=False,
        ),
        sa.Column('custom_interval_value', sa.Integer(), nullable=True),
        sa.Column('custom_interval_unit', sa.Enum('days', 'weeks', 'months', name='customintervalunit'), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('credit_card_id', sa.Integer(), nullable=True),
        sa.Column('amount_logic', sa.JSON(), nullable=True),
        sa.Column(
            'needs_wants_savings',
            sa.Enum('need', 'want', 'savings', name='needswantssavings'),
            nullable=False,
            server_default='need',
        ),
        sa.Column('category_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['credit_card_id'], ['credit_cards.id']),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'credit_due_overrides',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('credit_card_id', sa.Integer(), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['credit_card_id'], ['credit_cards.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('credit_card_id', 'due_date', name='uq_credit_due_override_card_date'),
    )
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=80), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
    )
    op.create_table(
        'transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('kind', sa.Enum('cash', 'credit', name='kind'), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('recurring_series_id', sa.Integer(), nullable=True),
        sa.Column('occurrence_status', sa.Enum('attached', 'detached', 'skipped', name='occurrencestatus'), nullable=True),
        sa.Column('credit_card_id', sa.Integer(), nullable=True),
        sa.Column(
            'needs_wants_savings',
            sa.Enum('need', 'want', 'savings', name='needswantssavings'),
            nullable=False,
            server_default='need',
        ),
        sa.Column('category_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['recurring_series_id'], ['recurring_series.id']),
        sa.ForeignKeyConstraint(['credit_card_id'], ['credit_cards.id']),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    categories = sa.table(
        'categories',
        sa.column('id', sa.Integer),
        sa.column('name', sa.String),
        sa.column('icon', sa.String),
        sa.column('is_system', sa.Boolean),
    )
    op.bulk_insert(
        categories, [{'name': 'Uncategorized', 'icon': 'bi-tag', 'is_system': True}]
    )


def downgrade():
    op.drop_table('transactions')
    op.drop_table('users')
    op.drop_table('credit_due_overrides')
    op.drop_table('recurring_series')
    op.drop_table('categories')
    op.drop_table('credit_cards')
    op.drop_table('checking_accounts')
