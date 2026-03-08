from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Literal, Optional


InsightCategory = Literal[
    "evento_especial",
    "comparativa_historica",
    "casi_logro",
    "narrativa_resiliencia",
]


@dataclass
class InsightCandidate:
    id: str
    categoria: InsightCategory
    score_base: int
    data: Dict[str, Any]
    plantillas: List[str]
    score_total: int = 0  # se calcula en runtime


# -----------------------------
# Snapshots (inputs del motor)
# -----------------------------

@dataclass
class HoleSnapshot:
    hole_number: int
    par: int
    gross_strokes: Optional[int] = None
    putts: Optional[int] = None
    fir: Optional[bool] = None
    gir: Optional[bool] = None
    stableford_points: Optional[int] = None


@dataclass
class RoundSnapshot:
    round_id: int
    round_date: Optional[date]
    course_name: str

    # Totales del jugador en esta ronda
    gross_total: Optional[int]
    net_total: Optional[int]
    stableford_hcp_total: Optional[float]
    stableford_scratch_total: Optional[float]
    putts_total: Optional[int]

    fir_pct: Optional[float]
    gir_pct: Optional[float]
    putts_per_hole: Optional[float]
    play_level: Optional[float]  # nivel de juego

    # Conteos útiles
    birdies: int
    eagles: int
    pars: int
    bogeys: int
    doubles: int
    triple_plus: int

    holes: List[HoleSnapshot]


@dataclass
class HistoryBest:
    best_round_gross: Optional[int]
    best_round_gross_date: Optional[date]

    best_play_level: Optional[float]
    best_play_level_date: Optional[date]

    best_gir_pct: Optional[float]
    best_gir_pct_date: Optional[date]

    best_fir_pct: Optional[float]
    best_fir_pct_date: Optional[date]

    best_putts_per_hole: Optional[float]
    best_putts_per_hole_date: Optional[date]


@dataclass
class HistoryAverages:
    avg_gross: Optional[float]
    avg_net: Optional[float]
    avg_pts_hcp: Optional[float]
    avg_pts_scratch: Optional[float]
    avg_putts_total: Optional[float]
    avg_putts_per_hole: Optional[float]
    avg_fir_pct: Optional[float]
    avg_gir_pct: Optional[float]
    avg_play_level: Optional[float]


@dataclass
class HistoryCounts:
    rounds_played: int
    total_birdies: int
    total_eagles: int


@dataclass
class HistoryParStats:
    avg_par3: Optional[float]
    avg_par4: Optional[float]
    avg_par5: Optional[float]


@dataclass
class HistorySnapshot:
    has_min_history: bool  # >= 5 rondas válidas

    averages: HistoryAverages
    best: HistoryBest
    counts: HistoryCounts
    par_stats: HistoryParStats

    # Distribución global por hoyo
    dist_hio: int
    dist_albatros: int
    dist_eagles: int
    dist_birdies: int
    dist_pars: int
    dist_bogeys: int
    dist_doubles: int
    dist_triple_plus: int
    dist_total_holes: int


@dataclass
class AchievementsContext:
    round_type: str  # "Training", "Partido Amistoso", "Liga", etc.
    unlocked_ids: List[int]
    unlocked_names: List[str]
    near: List[Dict[str, Any]]  # [{type:"break_100", distance:2}, ...]