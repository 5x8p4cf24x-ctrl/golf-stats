"""add round context

Revision ID: da9b91113d03
Revises: 9bd64267f669
Create Date: 2026-02-20 18:21:31.950583

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'da9b91113d03'
down_revision: Union[str, None] = '9bd64267f669'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "rounds",
        sa.Column("context", sa.String(length=16), nullable=False, server_default="friendly")
    )


def downgrade() -> None:
    op.drop_column("rounds", "context")
    
