import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("Falta DATABASE_URL")

engine = create_engine(DATABASE_URL)

def table_exists(conn, table_name: str) -> bool:
    sql = text("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = :table_name
        )
    """)
    return bool(conn.execute(sql, {"table_name": table_name}).scalar())

def column_exists(conn, table_name: str, column_name: str) -> bool:
    sql = text("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
              AND column_name = :column_name
        )
    """)
    return bool(conn.execute(sql, {
        "table_name": table_name,
        "column_name": column_name
    }).scalar())

def constraint_exists(conn, constraint_name: str) -> bool:
    sql = text("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.table_constraints
            WHERE table_schema = 'public'
              AND constraint_name = :constraint_name
        )
    """)
    return bool(conn.execute(sql, {"constraint_name": constraint_name}).scalar())

def index_exists(conn, index_name: str) -> bool:
    sql = text("""
        SELECT EXISTS (
            SELECT 1
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND indexname = :index_name
        )
    """)
    return bool(conn.execute(sql, {"index_name": index_name}).scalar())

with engine.begin() as conn:
    print("== tournament_matches columns ==")

    tournament_match_columns = [
        ("stage_id", "ALTER TABLE tournament_matches ADD COLUMN stage_id INTEGER"),
        ("team_a_id", "ALTER TABLE tournament_matches ADD COLUMN team_a_id INTEGER"),
        ("team_b_id", "ALTER TABLE tournament_matches ADD COLUMN team_b_id INTEGER"),
        ("side_size", "ALTER TABLE tournament_matches ADD COLUMN side_size INTEGER"),
        ("match_mode", "ALTER TABLE tournament_matches ADD COLUMN match_mode TEXT"),
        ("status", "ALTER TABLE tournament_matches ADD COLUMN status TEXT DEFAULT 'draft'"),
        ("winner_side", "ALTER TABLE tournament_matches ADD COLUMN winner_side TEXT"),
        ("points_a", "ALTER TABLE tournament_matches ADD COLUMN points_a DOUBLE PRECISION"),
        ("points_b", "ALTER TABLE tournament_matches ADD COLUMN points_b DOUBLE PRECISION"),
        ("started_at", "ALTER TABLE tournament_matches ADD COLUMN started_at TIMESTAMP"),
        ("closed_at", "ALTER TABLE tournament_matches ADD COLUMN closed_at TIMESTAMP"),
    ]

    for col_name, sql in tournament_match_columns:
        if not column_exists(conn, "tournament_matches", col_name):
            print(f"Adding column tournament_matches.{col_name}")
            conn.execute(text(sql))
        else:
            print(f"OK column exists: tournament_matches.{col_name}")

    print("== create tournament_teams ==")
    if not table_exists(conn, "tournament_teams"):
        conn.execute(text("""
            CREATE TABLE tournament_teams (
                id SERIAL PRIMARY KEY,
                tournament_id INTEGER NOT NULL,
                side TEXT NOT NULL,
                name TEXT NOT NULL,
                logo_path TEXT,
                created_at TIMESTAMP
            )
        """))
        print("Created table tournament_teams")
    else:
        print("OK table exists: tournament_teams")

    print("== create tournament_team_players ==")
    if not table_exists(conn, "tournament_team_players"):
        conn.execute(text("""
            CREATE TABLE tournament_team_players (
                id SERIAL PRIMARY KEY,
                team_id INTEGER NOT NULL,
                player_id INTEGER NOT NULL,
                created_at TIMESTAMP
            )
        """))
        print("Created table tournament_team_players")
    else:
        print("OK table exists: tournament_team_players")

    print("== create tournament_stages ==")
    if not table_exists(conn, "tournament_stages"):
        conn.execute(text("""
            CREATE TABLE tournament_stages (
                id SERIAL PRIMARY KEY,
                tournament_id INTEGER NOT NULL,
                order_index INTEGER NOT NULL,
                name TEXT,
                modality TEXT NOT NULL,
                course_id INTEGER NOT NULL,
                status TEXT DEFAULT 'draft',
                created_at TIMESTAMP
            )
        """))
        print("Created table tournament_stages")
    else:
        print("OK table exists: tournament_stages")

    print("== create tournament_match_participants ==")
    if not table_exists(conn, "tournament_match_participants"):
        conn.execute(text("""
            CREATE TABLE tournament_match_participants (
                id SERIAL PRIMARY KEY,
                match_id INTEGER NOT NULL,
                player_id INTEGER NOT NULL,
                side TEXT NOT NULL,
                slot INTEGER NOT NULL
            )
        """))
        print("Created table tournament_match_participants")
    else:
        print("OK table exists: tournament_match_participants")

    print("== foreign keys ==")
    fk_statements = [
        (
            "fk_tournament_teams_tournament_id",
            """
            ALTER TABLE tournament_teams
            ADD CONSTRAINT fk_tournament_teams_tournament_id
            FOREIGN KEY (tournament_id) REFERENCES tournaments(id)
            """
        ),
        (
            "fk_tournament_team_players_team_id",
            """
            ALTER TABLE tournament_team_players
            ADD CONSTRAINT fk_tournament_team_players_team_id
            FOREIGN KEY (team_id) REFERENCES tournament_teams(id)
            """
        ),
        (
            "fk_tournament_team_players_player_id",
            """
            ALTER TABLE tournament_team_players
            ADD CONSTRAINT fk_tournament_team_players_player_id
            FOREIGN KEY (player_id) REFERENCES players(id)
            """
        ),
        (
            "fk_tournament_stages_tournament_id",
            """
            ALTER TABLE tournament_stages
            ADD CONSTRAINT fk_tournament_stages_tournament_id
            FOREIGN KEY (tournament_id) REFERENCES tournaments(id)
            """
        ),
        (
            "fk_tournament_stages_course_id",
            """
            ALTER TABLE tournament_stages
            ADD CONSTRAINT fk_tournament_stages_course_id
            FOREIGN KEY (course_id) REFERENCES courses(id)
            """
        ),
        (
            "fk_tournament_match_participants_match_id",
            """
            ALTER TABLE tournament_match_participants
            ADD CONSTRAINT fk_tournament_match_participants_match_id
            FOREIGN KEY (match_id) REFERENCES tournament_matches(id)
            """
        ),
        (
            "fk_tournament_match_participants_player_id",
            """
            ALTER TABLE tournament_match_participants
            ADD CONSTRAINT fk_tournament_match_participants_player_id
            FOREIGN KEY (player_id) REFERENCES players(id)
            """
        ),
        (
            "fk_tournament_matches_stage_id",
            """
            ALTER TABLE tournament_matches
            ADD CONSTRAINT fk_tournament_matches_stage_id
            FOREIGN KEY (stage_id) REFERENCES tournament_stages(id)
            """
        ),
        (
            "fk_tournament_matches_team_a_id",
            """
            ALTER TABLE tournament_matches
            ADD CONSTRAINT fk_tournament_matches_team_a_id
            FOREIGN KEY (team_a_id) REFERENCES tournament_teams(id)
            """
        ),
        (
            "fk_tournament_matches_team_b_id",
            """
            ALTER TABLE tournament_matches
            ADD CONSTRAINT fk_tournament_matches_team_b_id
            FOREIGN KEY (team_b_id) REFERENCES tournament_teams(id)
            """
        ),
    ]

    for fk_name, sql in fk_statements:
        if not constraint_exists(conn, fk_name):
            print(f"Adding FK {fk_name}")
            conn.execute(text(sql))
        else:
            print(f"OK FK exists: {fk_name}")

    print("== indexes ==")
    index_statements = [
        ("ix_tournament_teams_tournament_id", "CREATE INDEX ix_tournament_teams_tournament_id ON tournament_teams (tournament_id)"),
        ("ix_tournament_team_players_team_id", "CREATE INDEX ix_tournament_team_players_team_id ON tournament_team_players (team_id)"),
        ("ix_tournament_team_players_player_id", "CREATE INDEX ix_tournament_team_players_player_id ON tournament_team_players (player_id)"),
        ("ix_tournament_stages_tournament_id", "CREATE INDEX ix_tournament_stages_tournament_id ON tournament_stages (tournament_id)"),
        ("ix_tournament_match_participants_match_id", "CREATE INDEX ix_tournament_match_participants_match_id ON tournament_match_participants (match_id)"),
        ("ix_tournament_match_participants_player_id", "CREATE INDEX ix_tournament_match_participants_player_id ON tournament_match_participants (player_id)"),
    ]

    for idx_name, sql in index_statements:
        if not index_exists(conn, idx_name):
            print(f"Adding index {idx_name}")
            conn.execute(text(sql))
        else:
            print(f"OK index exists: {idx_name}")

print("Migration finished.")