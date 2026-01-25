from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey, Text
from sqlalchemy.orm import relationship
from .db import Base
from datetime import datetime
from sqlalchemy import Boolean, DateTime
from sqlalchemy.sql import func


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    nickname = Column(String, nullable=True)
    hcp_exact = Column(Float, nullable=False, default=0.0)
    active = Column(Boolean, default=True)
    license_number = Column(String, nullable=True)

    # 📸 ruta de la foto dentro de /static (ej: "uploads/players/abcd.jpg")
    photo_url = Column(String, nullable=True)

    rounds = relationship("RoundPlayer", back_populates="player")
    achievements = relationship("PlayerAchievement", back_populates="player")


class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    city = Column(String, nullable=True)
    par_total = Column(Integer, nullable=False, default=72)

    slope_yellow = Column(Integer, nullable=False, default=113)
    rating_yellow = Column(Float, nullable=False, default=72.0)
    meters_total = Column(Integer, nullable=True)
    logo_url = Column(String, nullable=True)

    holes = relationship(
        "Hole",
        back_populates="course",
        cascade="all, delete-orphan"
    )

    rounds = relationship("Round", back_populates="course")


class Round(Base):
    __tablename__ = "rounds"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    tee = Column(String, nullable=False, default="yellow")
    type = Column(String, nullable=False, default="amistosa")

    # ✅ FK a leagues
    league_id = Column(Integer, ForeignKey("leagues.id"), nullable=True)
    league = relationship("League", back_populates="rounds")

    winner_type = Column(String, nullable=True)  # single/tie
    winner_player_ids = Column(String, nullable=True)  # "1,3"

    course = relationship("Course", back_populates="rounds")

    # ✅ nombre consistente con el resto del proyecto
    round_players = relationship("RoundPlayer", back_populates="round")



class RoundPlayer(Base):
    __tablename__ = "round_players"

    id = Column(Integer, primary_key=True, index=True)
    round_id = Column(Integer, ForeignKey("rounds.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)

    hcp_exact_day = Column(Float, nullable=False)
    course_handicap = Column(Integer, nullable=False)

    gross_total = Column(Integer, nullable=True)
    net_total = Column(Integer, nullable=True)
    stableford_hcp_total = Column(Integer, nullable=True)
    stableford_scratch_total = Column(Integer, nullable=True)

    putts_total = Column(Integer, nullable=True)

    result = Column(String, nullable=True)  # win/tie/loss

    edit_token = Column(String(128), nullable=True, index=True)
    token_created_at = Column(DateTime, nullable=True)
    player_card_locked = Column(Boolean, nullable=False, default=False)

    round = relationship("Round", back_populates="round_players")
    player = relationship("Player", back_populates="rounds")

    hole_scores = relationship(
        "HoleScore",
        back_populates="round_player",
        cascade="all, delete-orphan"
    )

class Hole(Base):
    __tablename__ = "holes"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)

    number = Column(Integer, nullable=False)          # 1..18
    par = Column(Integer, nullable=False)             # 3/4/5
    stroke_index = Column(Integer, nullable=False)    # HCP hoyo 1..18
    meters_yellow = Column(Integer, nullable=True)    # metros amarillas

    course = relationship("Course", back_populates="holes")

class HoleScore(Base):
    __tablename__ = "hole_scores"

    id = Column(Integer, primary_key=True, index=True)

    round_player_id = Column(Integer, ForeignKey("round_players.id"), nullable=False)
    hole_number = Column(Integer, nullable=False)  # 1..18

    gross_strokes = Column(Integer, nullable=False)  # golpes brutos
    putts = Column(Integer, nullable=True)          # putts

    fir = Column(Boolean, nullable=True)            # input manual (None en par3)
    gir = Column(Boolean, nullable=True)            # calculado

    net_strokes = Column(Integer, nullable=True)     # calculado
    stableford_points = Column(Integer, nullable=True)  # calculado

    round_player = relationship("RoundPlayer", back_populates="hole_scores")

class League(Base):
    __tablename__ = "leagues"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    is_closed = Column(Boolean, default=False)
    logo_url = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # relaciones
    rounds = relationship("Round", back_populates="league")

class Achievement(Base):
    __tablename__ = "achievements"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    icon = Column(String, nullable=False)        # ruta tipo "icons/campeon_liga.png"
    description = Column(String, nullable=True)
    category = Column(String, nullable=True)     # opcional, por si quieres agrupar

    players = relationship("PlayerAchievement", back_populates="achievement")

class PlayerAchievement(Base):
    __tablename__ = "player_achievements"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    achievement_id = Column(Integer, ForeignKey("achievements.id"), nullable=False)
    unlocked = Column(Boolean, default=False, nullable=False)

    player = relationship("Player", back_populates="achievements")
    achievement = relationship("Achievement", back_populates="players")


class News(Base):
    __tablename__ = "news"

    id = Column(Integer, primary_key=True, index=True)

    # Contenido
    title = Column(String(120), nullable=False)
    excerpt = Column(Text, nullable=False)  # texto corto (3-5 líneas)
    category = Column(String(32), nullable=False, default="general")  # league|achievement|record|round|general

    # Imagen 400x300 (ruta en /static/uploads/news/...)
    image_path = Column(String(255), nullable=False)

    # Opcional: link interno a algo (liga/jugador/logro)
    related_url = Column(String(255), nullable=True)

    # Publicación
    published = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

# =====================================================================================
# ================================= TOURNAMENTS =======================================
# =====================================================================================

class Tournament(Base):
    __tablename__ = "tournaments"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)
    date = Column(Date, nullable=False)

    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    
    mode = Column(String, nullable=False)  # "individual" | "team"
    status = Column(String, nullable=False, default="draft")  # draft|published|finished

    image_path = Column(String, nullable=True)  # /uploads/tournaments/xxx.jpg

    created_at = Column(DateTime, default=datetime.utcnow)

    course = relationship("Course")

    participants = relationship(
        "TournamentParticipant",
        back_populates="tournament",
        cascade="all, delete-orphan"
    )

    matches = relationship(
        "TournamentMatch",
        back_populates="tournament",
        cascade="all, delete-orphan"
    )


class TournamentParticipant(Base):
    __tablename__ = "tournament_participants"

    id = Column(Integer, primary_key=True, index=True)

    tournament_id = Column(Integer, ForeignKey("tournaments.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)

    seed = Column(Integer, nullable=True)  # opcional (1..16)

    tournament = relationship("Tournament", back_populates="participants")
    player = relationship("Player")


class TournamentMatch(Base):
    __tablename__ = "tournament_matches"

    id = Column(Integer, primary_key=True, index=True)

    tournament_id = Column(Integer, ForeignKey("tournaments.id"), nullable=False)

    round = Column(String, nullable=False)   # "R16", "QF", "SF", "F"
    position = Column(Integer, nullable=False)

    player_a_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    player_b_id = Column(Integer, ForeignKey("players.id"), nullable=True)

    winner_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    result_text = Column(String, nullable=True)  # "3&2"

    # ✅ NUEVO: link secreto para editar desde móvil
    edit_token = Column(String, nullable=True, index=True)

    # ✅ Opcional: auditoría
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    tournament = relationship("Tournament", back_populates="matches")

    player_a = relationship("Player", foreign_keys=[player_a_id])
    player_b = relationship("Player", foreign_keys=[player_b_id])
    winner = relationship("Player", foreign_keys=[winner_id])

    hole_results = relationship(
        "TournamentMatchHole",
        back_populates="match",
        cascade="all, delete-orphan"
    )

class TournamentMatchHole(Base):
    __tablename__ = "tournament_match_holes"

    id = Column(Integer, primary_key=True, index=True)

    match_id = Column(Integer, ForeignKey("tournament_matches.id"), nullable=False)
    hole_number = Column(Integer, nullable=False)  # 1..18
    outcome = Column(String, nullable=False)       # "A" | "B" | "AS"

    match = relationship("TournamentMatch", back_populates="hole_results")

