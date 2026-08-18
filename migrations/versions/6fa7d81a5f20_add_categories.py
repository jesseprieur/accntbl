"""add categories table and needs_wants_savings/category_id fields

Revision ID: 6fa7d81a5f20
Revises: 3167e16d7097
Create Date: 2026-08-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6fa7d81a5f20'
down_revision = '3167e16d7097'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    none_category = sa.table(
        'categories', sa.column('id', sa.Integer), sa.column('name', sa.String)
    )
    op.bulk_insert(none_category, [{'name': 'None'}])

    with op.batch_alter_table('recurring_series', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'needs_wants_savings',
                sa.Enum('need', 'want', 'savings', name='needswantssavings'),
                nullable=False,
                server_default='need',
            )
        )
        batch_op.add_column(sa.Column('category_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_recurring_series_category_id', 'categories', ['category_id'], ['id']
        )

    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'needs_wants_savings',
                sa.Enum('need', 'want', 'savings', name='needswantssavings'),
                nullable=False,
                server_default='need',
            )
        )
        batch_op.add_column(sa.Column('category_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_transactions_category_id', 'categories', ['category_id'], ['id']
        )

    connection = op.get_bind()
    none_id = connection.execute(
        sa.text("SELECT id FROM categories WHERE name = 'None'")
    ).scalar()
    connection.execute(
        sa.text("UPDATE recurring_series SET category_id = :none_id")
        .bindparams(none_id=none_id)
    )
    connection.execute(
        sa.text("UPDATE transactions SET category_id = :none_id")
        .bindparams(none_id=none_id)
    )

    with op.batch_alter_table('recurring_series', schema=None) as batch_op:
        batch_op.alter_column('category_id', nullable=False)

    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.alter_column('category_id', nullable=False)


def downgrade():
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_transactions_category_id', type_='foreignkey')
        batch_op.drop_column('category_id')
        batch_op.drop_column('needs_wants_savings')

    with op.batch_alter_table('recurring_series', schema=None) as batch_op:
        batch_op.drop_constraint('fk_recurring_series_category_id', type_='foreignkey')
        batch_op.drop_column('category_id')
        batch_op.drop_column('needs_wants_savings')

    op.drop_table('categories')
