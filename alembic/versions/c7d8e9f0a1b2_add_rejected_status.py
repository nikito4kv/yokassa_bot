"""add rejected status to paymentstatus enum

Revision ID: c7d8e9f0a1b2
Revises: 913fc275a6bb
Create Date: 2025-11-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, Sequence[str], None] = '913fc275a6bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add 'rejected' to PaymentStatus enum
    # Note: This syntax is specific to PostgreSQL
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE paymentstatus ADD VALUE IF NOT EXISTS 'rejected'")


def downgrade() -> None:
    """Downgrade schema."""
    # PostgreSQL does not support removing values from ENUM types easily.
    pass
