"""add status and message ids to manual payments

Revision ID: 599d75f72ed3
Revises: e284015b7096
Create Date: 2025-11-24 20:10:20.615488

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '599d75f72ed3'
down_revision: Union[str, Sequence[str], None] = 'e284015b7096'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'manual_payments',
        sa.Column('status', sa.String(length=16), nullable=False, server_default='pending')
    )
    op.add_column(
        'manual_payments',
        sa.Column('admin_message_ids', sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('manual_payments', 'admin_message_ids')
    op.drop_column('manual_payments', 'status')
