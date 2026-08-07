"""add amount_logic to recurring_series

Revision ID: 3167e16d7097
Revises: 4502d977e445
Create Date: 2026-08-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3167e16d7097'
down_revision = '4502d977e445'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('recurring_series', schema=None) as batch_op:
        batch_op.add_column(sa.Column('amount_logic', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('recurring_series', schema=None) as batch_op:
        batch_op.drop_column('amount_logic')
