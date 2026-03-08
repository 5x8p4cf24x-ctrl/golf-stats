from __future__ import annotations

import random
from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from app import models
from app.insights import rules_v1
from app.insights.types import (
    AchievementsContext,
    HistoryAverages,
    HistoryBest,
    HistoryCounts,
    HistoryParStats,
    HistorySnapshot,
    HoleSnapshot,
    InsightCandidate,
    RoundSnapshot,
)


# =========================================================
# Snapshots
# =========================================================

def build_history_snapshot(db: Session, player_id: int) -> HistorySnapshot:
    rps: list[models.RoundPlayer] = (
        db.query(models.RoundPlayer)
        .options(
            joinedload(models.RoundPlayer.round)
            .joinedload(models.Round.course)
            .joinedload(models.Course.holes),
            joinedload(models.RoundPlayer.hole_scores),
        )
        .filter(models.RoundPlayer.player_id == player_id)
        .all()
    )

    valid_rps = [rp for rp in rps if rp.gross_total is not None]
    rounds_played = len(valid_rps)
    has_min_history = rounds_played >= 5

    gross_list = [rp.gross_total for rp in valid_rps if rp.gross_total is not None]
    net_list = [rp.net_total for rp in valid_rps if rp.net_total is not None]
    pts_hcp_list = [rp.stableford_hcp_total for rp in valid_rps if rp.stableford_hcp_total is not None]
    pts_scratch_list = [rp.stableford_scratch_total for rp in valid_rps if rp.stableford_scratch_total is not None]
    putts_list = [rp.putts_total for rp in valid_rps if rp.putts_total is not None]

    avg_gross = (sum(gross_list) / len(gross_list)) if gross_list else None
    avg_net = (sum(net_list) / len(net_list)) if net_list else None
    avg_pts_hcp = (sum(pts_hcp_list) / len(pts_hcp_list)) if pts_hcp_list else None
    avg_pts_scratch = (sum(pts_scratch_list) / len(pts_scratch_list)) if pts_scratch_list else None
    avg_putts_total = (sum(putts_list) / len(putts_list)) if putts_list else None

    best_round_gross = min(gross_list) if gross_list else None

    hole_scores: list[models.HoleScore] = []
    for rp in valid_rps:
        hole_scores.extend(list(rp.hole_scores or []))

    fir_total = sum(1 for s in hole_scores if s.fir is True)
    fir_possible = sum(1 for s in hole_scores if s.fir is not None)
    fir_pct = (fir_total / fir_possible * 100) if fir_possible else None

    gir_total = sum(1 for s in hole_scores if s.gir is True)
    gir_possible = sum(1 for s in hole_scores if s.gir is not None)
    gir_pct = (gir_total / gir_possible * 100) if gir_possible else None

    putts_holes = [s.putts for s in hole_scores if s.putts is not None]
    avg_putts_per_hole = (sum(putts_holes) / len(putts_holes)) if putts_holes else None

    play_levels: list[float] = []
    for rp in valid_rps:
        r = rp.round
        c = r.course if r else None
        if rp.gross_total is not None and c and c.slope_yellow and c.rating_yellow is not None:
            lvl = ((rp.gross_total - c.rating_yellow) * 113) / c.slope_yellow
            play_levels.append(lvl)
    avg_play_level = (sum(play_levels) / len(play_levels)) if play_levels else None

    dist_hio = dist_albatros = dist_eagles = dist_birdies = 0
    dist_pars = dist_bogeys = dist_doubles = dist_triple_plus = 0
    dist_total_holes = 0

    par3_sum = par3_count = 0
    par4_sum = par4_count = 0
    par5_sum = par5_count = 0

    for rp in valid_rps:
        course = rp.round.course if rp.round else None
        if not course:
            continue

        par_map = {h.number: h.par for h in (course.holes or [])}

        for s in rp.hole_scores or []:
            if s.gross_strokes is None:
                continue

            par = par_map.get(s.hole_number)
            if par is None:
                continue

            dist_total_holes += 1

            if par == 3:
                par3_sum += s.gross_strokes
                par3_count += 1
            elif par == 4:
                par4_sum += s.gross_strokes
                par4_count += 1
            elif par == 5:
                par5_sum += s.gross_strokes
                par5_count += 1

            if s.gross_strokes == 1:
                dist_hio += 1
                continue

            diff = s.gross_strokes - par
            if diff <= -3:
                dist_albatros += 1
            elif diff == -2:
                dist_eagles += 1
            elif diff == -1:
                dist_birdies += 1
            elif diff == 0:
                dist_pars += 1
            elif diff == 1:
                dist_bogeys += 1
            elif diff == 2:
                dist_doubles += 1
            else:
                dist_triple_plus += 1

    best = HistoryBest(
        best_round_gross=best_round_gross,
        best_round_gross_date=None,
        best_play_level=None,
        best_play_level_date=None,
        best_gir_pct=None,
        best_gir_pct_date=None,
        best_fir_pct=None,
        best_fir_pct_date=None,
        best_putts_per_hole=None,
        best_putts_per_hole_date=None,
    )

    averages = HistoryAverages(
        avg_gross=avg_gross,
        avg_net=avg_net,
        avg_pts_hcp=avg_pts_hcp,
        avg_pts_scratch=avg_pts_scratch,
        avg_putts_total=avg_putts_total,
        avg_putts_per_hole=avg_putts_per_hole,
        avg_fir_pct=fir_pct,
        avg_gir_pct=gir_pct,
        avg_play_level=avg_play_level,
    )

    counts = HistoryCounts(
        rounds_played=rounds_played,
        total_birdies=dist_birdies,
        total_eagles=dist_eagles,
    )

    par_stats = HistoryParStats(
        avg_par3=(par3_sum / par3_count) if par3_count else None,
        avg_par4=(par4_sum / par4_count) if par4_count else None,
        avg_par5=(par5_sum / par5_count) if par5_count else None,
    )

    return HistorySnapshot(
        has_min_history=has_min_history,
        averages=averages,
        best=best,
        counts=counts,
        par_stats=par_stats,
        dist_hio=dist_hio,
        dist_albatros=dist_albatros,
        dist_eagles=dist_eagles,
        dist_birdies=dist_birdies,
        dist_pars=dist_pars,
        dist_bogeys=dist_bogeys,
        dist_doubles=dist_doubles,
        dist_triple_plus=dist_triple_plus,
        dist_total_holes=dist_total_holes,
    )


def build_round_snapshot(db: Session, round_id: int, player_id: int) -> RoundSnapshot:
    rp: models.RoundPlayer | None = (
        db.query(models.RoundPlayer)
        .options(
            joinedload(models.RoundPlayer.round)
            .joinedload(models.Round.course)
            .joinedload(models.Course.holes),
            joinedload(models.RoundPlayer.hole_scores),
        )
        .filter(
            models.RoundPlayer.round_id == round_id,
            models.RoundPlayer.player_id == player_id,
        )
        .first()
    )

    if rp is None or rp.round is None or rp.round.course is None:
        return RoundSnapshot(
            round_id=round_id,
            round_date=None,
            course_name="",
            gross_total=rp.gross_total if rp else None,
            net_total=rp.net_total if rp else None,
            stableford_hcp_total=rp.stableford_hcp_total if rp else None,
            stableford_scratch_total=rp.stableford_scratch_total if rp else None,
            putts_total=rp.putts_total if rp else None,
            fir_pct=None,
            gir_pct=None,
            putts_per_hole=None,
            play_level=None,
            birdies=0,
            eagles=0,
            pars=0,
            bogeys=0,
            doubles=0,
            triple_plus=0,
            holes=[],
        )

    r = rp.round
    c = r.course
    par_map = {h.number: h.par for h in (c.holes or [])}

    holes: list[HoleSnapshot] = []
    for s in (rp.hole_scores or []):
        holes.append(
            HoleSnapshot(
                hole_number=s.hole_number,
                par=par_map.get(s.hole_number, 0),
                gross_strokes=s.gross_strokes,
                putts=s.putts,
                fir=s.fir,
                gir=s.gir,
                stableford_points=s.stableford_points,
            )
        )
    holes.sort(key=lambda x: x.hole_number)

    fir_total = sum(1 for h in holes if h.fir is True)
    fir_possible = sum(1 for h in holes if h.fir is not None)
    fir_pct = (fir_total / fir_possible * 100) if fir_possible else None

    gir_total = sum(1 for h in holes if h.gir is True)
    gir_possible = sum(1 for h in holes if h.gir is not None)
    gir_pct = (gir_total / gir_possible * 100) if gir_possible else None

    putts_vals = [h.putts for h in holes if h.putts is not None]
    putts_per_hole = (sum(putts_vals) / len(putts_vals)) if putts_vals else None

    play_level = None
    if rp.gross_total is not None and c.slope_yellow and c.rating_yellow is not None:
        play_level = ((rp.gross_total - c.rating_yellow) * 113) / c.slope_yellow

    birdies = eagles = pars = bogeys = doubles = triple_plus = 0
    for h in holes:
        if h.gross_strokes is None or not h.par:
            continue
        if h.gross_strokes == 1:
            continue

        diff = h.gross_strokes - h.par
        if diff == -2:
            eagles += 1
        elif diff == -1:
            birdies += 1
        elif diff == 0:
            pars += 1
        elif diff == 1:
            bogeys += 1
        elif diff == 2:
            doubles += 1
        elif diff >= 3:
            triple_plus += 1

    return RoundSnapshot(
        round_id=round_id,
        round_date=r.date,
        course_name=c.name or "",
        gross_total=rp.gross_total,
        net_total=rp.net_total,
        stableford_hcp_total=rp.stableford_hcp_total,
        stableford_scratch_total=rp.stableford_scratch_total,
        putts_total=rp.putts_total,
        fir_pct=fir_pct,
        gir_pct=gir_pct,
        putts_per_hole=putts_per_hole,
        play_level=play_level,
        birdies=birdies,
        eagles=eagles,
        pars=pars,
        bogeys=bogeys,
        doubles=doubles,
        triple_plus=triple_plus,
        holes=holes,
    )


# =========================================================
# Helpers internos del engine
# =========================================================

def _cand(
    _id: str,
    categoria: str,
    score_base: int,
    plantillas: str | list[str],
    data: dict | None = None,
) -> InsightCandidate:
    return InsightCandidate(
        id=_id,
        categoria=categoria,  # type: ignore[arg-type]
        score_base=score_base,
        data=data or {},
        plantillas=plantillas if isinstance(plantillas, list) else [plantillas],
        score_total=0,
    )


def _apply_scoring(c: InsightCandidate) -> None:
    score = c.score_base

    if "hole" in c.data or "holes" in c.data or "hole_from" in c.data:
        score += 1
    if c.data.get("links_achievement"):
        score += 1
    if c.data.get("is_bounce_back"):
        score += 1

    c.score_total = int(score)


def _normalize_round_type(round_type: str | None) -> str:
    if not round_type:
        return ""

    val = round_type.strip().lower()

    if val in ("training",):
        return "training"

    if val in ("amistosa", "partido amistoso", "amistoso", "friendly", "partido"):
        return "amistosa"

    if val in ("liga", "league"):
        return "liga"

    return val


def _is_matchplay_type(round_type: str | None) -> bool:
    if not round_type:
        return False
    val = round_type.strip().lower()
    return val in ("match", "matchplay", "tournament", "torneo matchplay")


def _modulate_scores_by_round_type(
    cands: list[InsightCandidate],
    achievements_ctx: AchievementsContext | None,
) -> None:
    rt = _normalize_round_type(achievements_ctx.round_type if achievements_ctx else None)

    if rt == "training":
        for c in cands:
            if c.id in ("gross_vs_avg", "putts_pph", "putts_total", "fir_strong", "gir_strong", "play_level_vs_hcp"):
                c.score_total += 8
            if c.id in ("bogey_golf", "damage_control"):
                c.score_total -= 4

    elif rt == "amistosa":
        for c in cands:
            if c.id in ("birdie_round", "bounce_back", "strong_finish", "play_level_vs_hcp", "gross_vs_avg"):
                c.score_total += 4

    elif rt == "liga":
        for c in cands:
            if c.id in ("best_stableford_ever", "damage_control", "strong_finish", "bogey_golf", "no_triples"):
                c.score_total += 8
            if c.id in ("fir_strong", "gir_strong", "putts_pph", "putts_total"):
                c.score_total -= 3


def _penalize_small_stats_if_two_strong(cands: list[InsightCandidate]) -> None:
    strong = sum(1 for c in cands if c.score_total >= 80)
    if strong < 2:
        return

    for c in cands:
        if c.id in ("putts_pph", "putts_total", "fir_strong", "gir_strong"):
            c.score_total = max(0, c.score_total - 15)


def _dedupe_redundant(cands: list[InsightCandidate]) -> list[InsightCandidate]:
    best_by_id: dict[str, InsightCandidate] = {}
    for c in cands:
        current = best_by_id.get(c.id)
        if current is None or c.score_total > current.score_total:
            best_by_id[c.id] = c

    result = list(best_by_id.values())
    ids = {c.id for c in result}

    if "best_gross_ever" in ids and "best_gross_year" in ids:
        result = [c for c in result if c.id != "best_gross_year"]

    if "putts_pph" in ids and "putts_total" in ids:
        keep_pph = next((c for c in result if c.id == "putts_pph"), None)
        keep_total = next((c for c in result if c.id == "putts_total"), None)
        if keep_pph and keep_total:
            loser = "putts_total" if keep_pph.score_total >= keep_total.score_total else "putts_pph"
            result = [c for c in result if c.id != loser]

    return result

def _remove_achievement_candidates_from_narrative(cands: list[InsightCandidate]) -> list[InsightCandidate]:
    """
    Los logros desbloqueados ya se muestran en su propio bloque del email.
    No deben ocupar uno de los 4 insights narrativos.
    """
    return [c for c in cands if c.id != "achievement_unlocked"]

# =========================================================
# Inyección DB: récords / logros / stat top
# =========================================================

def _inject_db_candidates(
    db: Session,
    player_id: int,
    round_id: int,
    hist: HistorySnapshot,
    rnd: RoundSnapshot,
    achievements_ctx: AchievementsContext | None,
) -> list[InsightCandidate]:
    cands: list[InsightCandidate] = []

    # Regla 1 — logro desbloqueado
    if achievements_ctx and achievements_ctx.unlocked_names:
        name = achievements_ctx.unlocked_names[0]
        cands.append(
            _cand(
                "achievement_unlocked",
                "evento_especial",
                100,
                "🏆 Has desbloqueado: {name}",
                {"name": name, "links_achievement": True},
            )
        )

    # Regla 2 — mejor gross histórico
    if rnd.gross_total is not None and hist.best.best_round_gross is not None:
        if rnd.gross_total == hist.best.best_round_gross:
            cands.append(
                _cand(
                    "best_gross_ever",
                    "evento_especial",
                    98,
                    "🔥 ¡Tu mejor vuelta histórica! {gross_total} golpes.",
                    {"gross_total": rnd.gross_total},
                )
            )

    # Regla 3 — mejor gross del año
    if rnd.round_date and rnd.gross_total is not None:
        y = rnd.round_date.year
        best_year = (
            db.query(models.RoundPlayer.gross_total)
            .join(models.Round, models.Round.id == models.RoundPlayer.round_id)
            .filter(models.RoundPlayer.player_id == player_id)
            .filter(models.Round.date.isnot(None))
            .filter(models.RoundPlayer.gross_total.isnot(None))
            .filter(models.Round.date >= date(y, 1, 1))
            .filter(models.Round.date < date(y + 1, 1, 1))
            .order_by(models.RoundPlayer.gross_total.asc())
            .limit(1)
            .scalar()
        )
        if best_year is not None and rnd.gross_total == best_year:
            cands.append(
                _cand(
                    "best_gross_year",
                    "evento_especial",
                    92,
                    "⭐ Tu mejor vuelta de {year}: {gross_total} golpes.",
                    {"year": y, "gross_total": rnd.gross_total},
                )
            )

    # Regla 4 — récord stableford
    if rnd.stableford_hcp_total is not None:
        best_pts = (
            db.query(models.RoundPlayer.stableford_hcp_total)
            .filter(models.RoundPlayer.player_id == player_id)
            .filter(models.RoundPlayer.stableford_hcp_total.isnot(None))
            .order_by(models.RoundPlayer.stableford_hcp_total.desc())
            .limit(1)
            .scalar()
        )
        if best_pts is not None and float(rnd.stableford_hcp_total) == float(best_pts):
            cands.append(
                _cand(
                    "best_stableford_ever",
                    "evento_especial",
                    94,
                    "💥 Récord personal de puntos: {pts:.0f} Stableford.",
                    {"pts": rnd.stableford_hcp_total},
                )
            )

    # Regla 5 — nivel de juego vs HCP de juego
    rp = (
        db.query(models.RoundPlayer)
        .filter(
            models.RoundPlayer.round_id == round_id,
            models.RoundPlayer.player_id == player_id,
        )
        .first()
    )

    hcp_juego = float(rp.course_handicap) if rp and rp.course_handicap is not None else None
    nivel_juego = rnd.play_level

    if hcp_juego is not None and nivel_juego is not None:
        mejora = hcp_juego - nivel_juego  # positivo = jugaste mejor

        if mejora >= 3.0:
            score = 90
            if mejora >= 5:
                score += 5

            cands.append(
                _cand(
                    "play_level_vs_hcp",
                    "comparativa_historica",
                    score,
                    [
                        "👏 Gran vuelta: has jugado como HCP {nivel:.1f} (tu HCP de juego era {hcp:.0f}).",
                        "🚀 Hoy has jugado como HCP {nivel:.1f}, muy por debajo de tu HCP de juego ({hcp:.0f}).",
                        "🔥 Nivelazo: HCP jugado {nivel:.1f} frente a tu HCP de juego {hcp:.0f}.",
                    ],
                    {
                        "nivel": nivel_juego,
                        "hcp": hcp_juego,
                        "mejora": mejora,
                    },
                )
            )

    return cands


# =========================================================
# Bloques narrativos
# =========================================================

def _pick_best(
    pool: list[InsightCandidate],
    *,
    preferred_categories: list[str] | None = None,
    preferred_ids: list[str] | None = None,
    exclude_ids: set[str] | None = None,
) -> Optional[InsightCandidate]:
    exclude_ids = exclude_ids or set()

    candidates = [c for c in pool if c.id not in exclude_ids]
    if not candidates:
        return None

    if preferred_ids:
        preferred = [c for c in candidates if c.id in preferred_ids]
        if preferred:
            return sorted(preferred, key=lambda x: x.score_total, reverse=True)[0]

    if preferred_categories:
        preferred = [c for c in candidates if c.categoria in preferred_categories]
        if preferred:
            return sorted(preferred, key=lambda x: x.score_total, reverse=True)[0]

    return sorted(candidates, key=lambda x: x.score_total, reverse=True)[0]


def _select_narrative_blocks(cands: list[InsightCandidate]) -> list[InsightCandidate]:
    """
    Bloques:
    1) titular
    2) explicación
    3) momento clave
    4) cierre
    """
    if not cands:
        return []

    selected: list[InsightCandidate] = []
    used_ids: set[str] = set()

    # 1) TITULAR
    headline = _pick_best(
        cands,
        preferred_ids=[
            "best_gross_ever",
            "best_stableford_ever",
            "best_gross_year",
            "play_level_vs_hcp",
            "gross_vs_avg",
        ],
        exclude_ids=used_ids,
    )
    if headline:
        selected.append(headline)
        used_ids.add(headline.id)

    # 2) EXPLICACIÓN
    support = _pick_best(
        cands,
        preferred_ids=[
            "gross_vs_avg",
            "play_level_vs_hcp",
            "putts_pph",
            "putts_total",
            "fir_strong",
            "gir_strong",
            "best_stableford_ever",
        ],
        exclude_ids=used_ids,
    )
    if support:
        selected.append(support)
        used_ids.add(support.id)

    # 3) MOMENTO CLAVE
    story = _pick_best(
        cands,
        preferred_ids=[
            "bounce_back",
            "birdie_round",
            "strong_finish",
            "no_triples",
            "damage_control",
            "many_pars",
            "bogey_golf",
            "best_hole",
        ],
        exclude_ids=used_ids,
    )
    if story:
        selected.append(story)
        used_ids.add(story.id)

    # 4) CIERRE
    closing = _pick_best(
        cands,
        preferred_ids=[
            "near_break_90",
            "near_break_100",
            "best_hole",
            "neutral_fallback",
            "damage_control",
            "no_triples",
        ],
        exclude_ids=used_ids,
    )
    if closing:
        selected.append(closing)
        used_ids.add(closing.id)

    # Relleno hasta 4
    remaining = sorted(
        [c for c in cands if c.id not in used_ids],
        key=lambda x: x.score_total,
        reverse=True,
    )
    for c in remaining:
        if len(selected) >= 4:
            break
        selected.append(c)
        used_ids.add(c.id)

    return selected[:4]


# =========================================================
# Render
# =========================================================

def _render(selected: list[InsightCandidate]) -> list[str]:
    out: list[str] = []
    for c in selected:
        if not c.plantillas:
            continue

        tpl = random.choice(c.plantillas)
        try:
            out.append(tpl.format(**c.data))
        except Exception:
            out.append(tpl)

    return out[:4]


# =========================================================
# API principal
# =========================================================

def generate_round_insights(
    db: Session,
    player_id: int,
    round_id: int,
    achievements_ctx: AchievementsContext | None = None,
) -> List[str]:
    # Excluir por ahora match play / tournament tipo match
    if achievements_ctx and _is_matchplay_type(achievements_ctx.round_type):
        return []

    hist = build_history_snapshot(db, player_id)
    rnd = build_round_snapshot(db, round_id, player_id)

    candidates: list[InsightCandidate] = []

    # 1) reglas base
    candidates.extend(rules_v1.generate_candidates(hist, rnd, achievements_ctx) or [])

    # 2) reglas con DB / récords / logros / nivel de juego
    candidates.extend(_inject_db_candidates(db, player_id, round_id, hist, rnd, achievements_ctx))

    # 3) scoring base
    for c in candidates:
        _apply_scoring(c)

    # 4) modulación por tipo de ronda
    _modulate_scores_by_round_type(candidates, achievements_ctx)

    # 5) si ya hay 2 insights fuertes, castigar stats pequeñas
    _penalize_small_stats_if_two_strong(candidates)

    # 6) anti-redundancia
    candidates = _dedupe_redundant(candidates)

    # 6.5) los logros desbloqueados van en su propio bloque del email
    candidates = _remove_achievement_candidates_from_narrative(candidates)

    # 7) bloques narrativos
    selected = _select_narrative_blocks(candidates)
    
    # 8) render final
    return _render(selected)