import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise SystemExit("ERROR: DATABASE_URL no está definido (Render lo define en producción).")

engine = create_engine(DATABASE_URL)

def try_run(label: str, sql: str):
    try:
        with engine.begin() as conn:
            conn.execute(text(sql))
        print(f"OK: {label}")
    except Exception as e:
        print(f"SKIP/ERR: {label} -> {e}")

# Postgres-safe
try_run("ADD edit_token",
        "ALTER TABLE round_players ADD COLUMN IF NOT EXISTS edit_token VARCHAR(128)")
try_run("ADD token_created_at",
        "ALTER TABLE round_players ADD COLUMN IF NOT EXISTS token_created_at TIMESTAMP NULL")
try_run("ADD player_card_locked",
        "ALTER TABLE round_players ADD COLUMN IF NOT EXISTS player_card_locked BOOLEAN NOT NULL DEFAULT FALSE")
try_run("INDEX edit_token",
        "CREATE INDEX IF NOT EXISTS ix_round_players_edit_token ON round_players (edit_token)")

print("Migración terminada")
