"""add closed_at to rounds

Revision ID: 2ac301b16f8b
Revises: da9b91113d03
Create Date: 2026-02-22 19:23:13.626522

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2ac301b16f8b'
down_revision: Union[str, None] = 'da9b91113d03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column("rounds", sa.Column("closed_at", sa.DateTime(), nullable=True))

def downgrade():
    op.drop_column("rounds", "closed_at")