"""add categories.icon column

Revision ID: 70ba669a5b01
Revises: 26df8205e1f4
Create Date: 2026-08-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '70ba669a5b01'
down_revision = '26df8205e1f4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('categories', schema=None) as batch_op:
        batch_op.add_column(sa.Column('icon', sa.String(length=64), nullable=True))


def downgrade():
    with op.batch_alter_table('categories', schema=None) as batch_op:
        batch_op.drop_column('icon')
