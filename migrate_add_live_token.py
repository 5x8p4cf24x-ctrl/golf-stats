from sqlalchemy import create_engine, text

# ajusta la ruta si tu db está en otra carpeta
engine = create_engine("sqlite:///golf_stats.db", future=True)

statements = [
    "ALTER TABLE round_players ADD COLUMN edit_token VARCHAR(128)",
    "ALTER TABLE round_players ADD COLUMN token_created_at DATETIME",
    "ALTER TABLE round_players ADD COLUMN player_card_locked BOOLEAN NOT NULL DEFAULT 0",
    "CREATE INDEX IF NOT EXISTS ix_round_players_edit_token ON round_players (edit_token)",
]

with engine.begin() as conn:
    for stmt in statements:
        try:
            conn.execute(text(stmt))
            print("OK:", stmt)
        except Exception as e:
            print("SKIP / ERROR:", stmt, "->", e)

print("Migración terminada")
