"""seed Uncategorized category and enforce category_id not null

Revision ID: 8b1c4f9a2e3d
Revises: 70ba669a5b01
Create Date: 2026-08-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8b1c4f9a2e3d'
down_revision = '70ba669a5b01'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('categories', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('is_system', sa.Boolean(), nullable=False, server_default=sa.false())
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

    connection = op.get_bind()
    uncategorized_id = connection.execute(
        sa.text("SELECT id FROM categories WHERE name = 'Uncategorized'")
    ).scalar()
    connection.execute(
        sa.text(
            "UPDATE recurring_series SET category_id = :id WHERE category_id IS NULL"
        ).bindparams(id=uncategorized_id)
    )
    connection.execute(
        sa.text(
            "UPDATE transactions SET category_id = :id WHERE category_id IS NULL"
        ).bindparams(id=uncategorized_id)
    )

    with op.batch_alter_table('recurring_series', schema=None) as batch_op:
        batch_op.alter_column('category_id', nullable=False)

    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.alter_column('category_id', nullable=False)


def downgrade():
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.alter_column('category_id', nullable=True)

    with op.batch_alter_table('recurring_series', schema=None) as batch_op:
        batch_op.alter_column('category_id', nullable=True)

    connection = op.get_bind()
    uncategorized_id = connection.execute(
        sa.text("SELECT id FROM categories WHERE name = 'Uncategorized' AND is_system = 1")
    ).scalar()
    if uncategorized_id is not None:
        connection.execute(
            sa.text(
                "UPDATE transactions SET category_id = NULL WHERE category_id = :id"
            ).bindparams(id=uncategorized_id)
        )
        connection.execute(
            sa.text(
                "UPDATE recurring_series SET category_id = NULL WHERE category_id = :id"
            ).bindparams(id=uncategorized_id)
        )
        connection.execute(
            sa.text("DELETE FROM categories WHERE id = :id").bindparams(id=uncategorized_id)
        )

    with op.batch_alter_table('categories', schema=None) as batch_op:
        batch_op.drop_column('is_system')
