"""add reset password token fields to users

Revision ID: f330a595280a
Revises: 2ac301b16f8b
Create Date: 2026-02-24 22:11:18.622094

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f330a595280a'
down_revision: Union[str, None] = '2ac301b16f8b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column("users", sa.Column("reset_token", sa.String(length=128), nullable=True))
    op.add_column("users", sa.Column("reset_token_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_users_reset_token"), "users", ["reset_token"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_users_reset_token"), table_name="users")
    op.drop_column("users", "reset_token_expires_at")
    op.drop_column("users", "reset_token")