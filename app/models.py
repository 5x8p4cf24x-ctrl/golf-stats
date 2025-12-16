from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from .db import Base
from datetime import datetime
from sqlalchemy import Boolean, DateTime


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
