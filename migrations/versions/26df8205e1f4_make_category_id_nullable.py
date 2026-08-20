"""make category_id nullable and drop the seeded None category

Revision ID: 26df8205e1f4
Revises: 6fa7d81a5f20
Create Date: 2026-08-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '26df8205e1f4'
down_revision = '6fa7d81a5f20'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('recurring_series', schema=None) as batch_op:
        batch_op.alter_column('category_id', nullable=True)

    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.alter_column('category_id', nullable=True)

    connection = op.get_bind()
    none_ids = [
        row[0]
        for row in connection.execute(
            sa.text("SELECT id FROM categories WHERE name = 'None'")
        ).fetchall()
    ]
    for none_id in none_ids:
        connection.execute(
            sa.text("UPDATE recurring_series SET category_id = NULL WHERE category_id = :none_id")
            .bindparams(none_id=none_id)
        )
        connection.execute(
            sa.text("UPDATE transactions SET category_id = NULL WHERE category_id = :none_id")
            .bindparams(none_id=none_id)
        )
        connection.execute(
            sa.text("DELETE FROM categories WHERE id = :none_id").bindparams(none_id=none_id)
        )


def downgrade():
    connection = op.get_bind()
    none_category = sa.table(
        'categories', sa.column('id', sa.Integer), sa.column('name', sa.String)
    )
    connection.execute(none_category.insert().values(name='None'))
    none_id = connection.execute(
        sa.text("SELECT id FROM categories WHERE name = 'None'")
    ).scalar()

    connection.execute(
        sa.text("UPDATE recurring_series SET category_id = :none_id WHERE category_id IS NULL")
        .bindparams(none_id=none_id)
    )
    connection.execute(
        sa.text("UPDATE transactions SET category_id = :none_id WHERE category_id IS NULL")
        .bindparams(none_id=none_id)
    )

    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.alter_column('category_id', nullable=False)

    with op.batch_alter_table('recurring_series', schema=None) as batch_op:
        batch_op.alter_column('category_id', nullable=False)
