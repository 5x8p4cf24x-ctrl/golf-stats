"""link player to user

Revision ID: aa4d1e41b87f
Revises: 578f1b573c29
Create Date: 2026-02-18 19:23:44.013692

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "aa4d1e41b87f"
down_revision: Union[str, None] = "578f1b573c29"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Añadir columna (esto funciona en SQLite y Postgres)
    op.add_column("players", sa.Column("user_id", sa.Integer(), nullable=True))

    # 2) Constraints:
    # - En Postgres: FK + UNIQUE (ideal)
    # - En SQLite: a veces falla crear FK/constraints tras ALTER TABLE.
    #   Así que en SQLite creamos un índice unique, que sí suele funcionar.
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.create_unique_constraint("uq_players_user_id", "players", ["user_id"])
        op.create_foreign_key(
            "fk_players_user_id_users",
            "players",
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )
    else:
        # SQLite (y otros): índice unique para mantener 1:1 sin pelear con FK
        # Nota: UNIQUE en SQLite permite múltiples NULL, así que no rompe nada.
        op.create_index("ix_players_user_id_unique", "players", ["user_id"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.drop_constraint("fk_players_user_id_users", "players", type_="foreignkey")
        op.drop_constraint("uq_players_user_id", "players", type_="unique")
    else:
        op.drop_index("ix_players_user_id_unique", table_name="players")

    op.drop_column("players", "user_id")
