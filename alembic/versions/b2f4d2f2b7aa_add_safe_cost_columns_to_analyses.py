"""add safe cost columns to analyses

Revision ID: b2f4d2f2b7aa
Revises: a3be7b4bcb4f
Create Date: 2026-02-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2f4d2f2b7aa"
down_revision: Union[str, Sequence[str], None] = "a3be7b4bcb4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("analyses", sa.Column("input_cost_price", sa.Float(), nullable=True))
    op.add_column("analyses", sa.Column("input_margin_percent", sa.Float(), nullable=True))
    op.add_column("analyses", sa.Column("safe_cost_price", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("analyses", "safe_cost_price")
    op.drop_column("analyses", "input_margin_percent")
    op.drop_column("analyses", "input_cost_price")
