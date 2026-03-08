from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.insights.types import (
    AchievementsContext,
    HistorySnapshot,
    InsightCandidate,
    RoundSnapshot,
)


# =========================================================
# Helpers
# =========================================================

def _cand(
    _id: str,
    categoria: str,
    score_base: int,
    plantillas: str | list[str],
    data: dict[str, Any] | None = None,
) -> InsightCandidate:
    return InsightCandidate(
        id=_id,
        categoria=categoria,  # type: ignore[arg-type]
        score_base=score_base,
        data=data or {},
        plantillas=plantillas if isinstance(plantillas, list) else [plantillas],
        score_total=0,
    )


def _hole_map(rnd: RoundSnapshot) -> dict[int, Any]:
    return {h.hole_number: h for h in (rnd.holes or [])}


def _diff(hole) -> Optional[int]:
    if hole is None or hole.gross_strokes is None or not hole.par:
        return None
    if hole.gross_strokes == 1:
        return -99  # HIO / súper evento
    return hole.gross_strokes - hole.par


def _fir_possible(rnd: RoundSnapshot) -> int:
    return sum(1 for h in rnd.holes if h.fir is not None)


def _gir_possible(rnd: RoundSnapshot) -> int:
    return sum(1 for h in rnd.holes if h.gir is not None)


def _holes_no_points(rnd: RoundSnapshot) -> Optional[int]:
    pts = [h.stableford_points for h in rnd.holes if h.stableford_points is not None]
    if not pts:
        return None
    return sum(1 for p in pts if p == 0)


def _best_hole_of_day(rnd: RoundSnapshot) -> Optional[Dict[str, Any]]:
    best_info: Optional[Dict[str, Any]] = None

    for h in rnd.holes:
        if h.gross_strokes is None or not h.par:
            continue

        if h.gross_strokes == 1:
            diff = -99
            label = "Hole in One"
        else:
            diff = h.gross_strokes - h.par
            if diff <= -3:
                label = "Albatros o mejor"
            elif diff == -2:
                label = "Eagle"
            elif diff == -1:
                label = "Birdie"
            elif diff == 0:
                label = "Par"
            elif diff == 1:
                label = "Bogey"
            else:
                label = "Doble o peor"

        info = {
            "best_hole": h.hole_number,
            "gross": h.gross_strokes,
            "par": h.par,
            "diff": diff,
            "label": label,
        }

        if best_info is None or info["diff"] < best_info["diff"]:
            best_info = info

    return best_info


# =========================================================
# Reglas scorecard / narrativa
# =========================================================

def rule_birdie_simple(hist: HistorySnapshot, rnd: RoundSnapshot) -> Optional[InsightCandidate]:
    if rnd.birdies >= 1:
        base = 70 + (5 if rnd.birdies >= 2 else 0)
        return _cand(
            "birdie_round",
            "narrativa_resiliencia",
            base,
            [
                "🐦 Birdie en la vuelta (hoy: {birdies}). Eso siempre cambia el día.",
                "🐦 Hubo premio: {birdies} birdie(s) en la ronda.",
            ],
            {"birdies": rnd.birdies},
        )
    return None


def rule_many_pars(hist: HistorySnapshot, rnd: RoundSnapshot) -> Optional[InsightCandidate]:
    if rnd.pars >= 6:
        return _cand(
            "many_pars",
            "narrativa_resiliencia",
            58,
            "🧊 En control: {pars} pares. Así se construye una vuelta.",
            {"pars": rnd.pars},
        )
    return None


def rule_bogey_golf(hist: HistorySnapshot, rnd: RoundSnapshot) -> Optional[InsightCandidate]:
    if rnd.bogeys >= 7 and rnd.stableford_hcp_total is not None and rnd.stableford_hcp_total >= 30:
        return _cand(
            "bogey_golf",
            "narrativa_resiliencia",
            54,
            "🧱 Bogey-golf inteligente: con {bogeys} bogeys seguiste sumando puntos.",
            {"bogeys": rnd.bogeys},
        )
    return None


def rule_no_triple_plus(hist: HistorySnapshot, rnd: RoundSnapshot) -> Optional[InsightCandidate]:
    if rnd.gross_total is not None and rnd.triple_plus == 0:
        return _cand(
            "no_triples",
            "narrativa_resiliencia",
            70,
            "🛡️ Sin desastres: no hubo triples o peor. Tarjeta muy viva.",
            {},
        )
    return None


def rule_damage_control_no_points(hist: HistorySnapshot, rnd: RoundSnapshot) -> Optional[InsightCandidate]:
    n0 = _holes_no_points(rnd)
    if n0 is not None and n0 <= 2:
        return _cand(
            "damage_control",
            "narrativa_resiliencia",
            66,
            "💪 Daño minimizado: solo {n0} hoyos sin puntuar.",
            {"n0": n0},
        )
    return None


def rule_bounce_back_after_big_hole(hist: HistorySnapshot, rnd: RoundSnapshot) -> Optional[InsightCandidate]:
    hm = _hole_map(rnd)

    for hn in range(1, 18):
        d1 = _diff(hm.get(hn))
        d2 = _diff(hm.get(hn + 1))
        if d1 is None or d2 is None:
            continue

        if d1 >= 3 and d2 <= 0:
            return _cand(
                "bounce_back",
                "narrativa_resiliencia",
                72,
                "⚡ Respuesta inmediata: tras el {bad_hole} llegó el {good_hole}. Bien jugado.",
                {"bad_hole": hn, "good_hole": hn + 1, "is_bounce_back": True},
            )

    return None


def rule_strong_finish_16_18(hist: HistorySnapshot, rnd: RoundSnapshot) -> Optional[InsightCandidate]:
    hm = _hole_map(rnd)

    diffs: list[int] = []
    for hn in (16, 17, 18):
        d = _diff(hm.get(hn))
        if d is None:
            return None
        diffs.append(d)

    # Cierre fuerte real:
    # - ningún hoyo peor que bogey
    # - al menos un par o mejor
    # - suma total del tramo <= +2
    if all(d <= 1 for d in diffs) and any(d <= 0 for d in diffs) and sum(diffs) <= 2:
        return _cand(
            "strong_finish",
            "narrativa_resiliencia",
            68,
            "🏁 Buen cierre en 16–18. Terminar así vale oro.",
            {},
        )

    return None

# =========================================================
# Reglas performance / stats
# =========================================================

def rule_gross_improvement(hist: HistorySnapshot, rnd: RoundSnapshot) -> Optional[InsightCandidate]:
    if rnd.gross_total is None or hist.averages.avg_gross is None:
        return None

    delta = hist.averages.avg_gross - rnd.gross_total
    if delta >= 2:
        base = 78
        if delta >= 5:
            base = 85

        return _cand(
            "gross_vs_avg",
            "comparativa_historica",
            base,
            [
                "📉 {gross_total} golpes: {delta:.1f} mejor que tu media ({avg_gross:.1f}).",
                "✅ Vuelta sólida: {gross_total} golpes, {delta:.1f} por debajo de tu media ({avg_gross:.1f}).",
            ],
            {
                "gross_total": rnd.gross_total,
                "delta": delta,
                "avg_gross": hist.averages.avg_gross,
            },
        )

    return None


def rule_putts_per_hole_improvement(hist: HistorySnapshot, rnd: RoundSnapshot) -> Optional[InsightCandidate]:
    if rnd.putts_per_hole is None or hist.averages.avg_putts_per_hole is None:
        return None

    delta = hist.averages.avg_putts_per_hole - rnd.putts_per_hole
    if delta >= 0.10:
        return _cand(
            "putts_pph",
            "comparativa_historica",
            62,
            "🧠 El putt fue clave: {pph:.2f} putts/hoyo (tu media es {avg:.2f}).",
            {
                "pph": rnd.putts_per_hole,
                "avg": hist.averages.avg_putts_per_hole,
                "delta": delta,
            },
        )

    return None


def rule_putts_total_improvement(hist: HistorySnapshot, rnd: RoundSnapshot) -> Optional[InsightCandidate]:
    if rnd.putts_total is None or hist.averages.avg_putts_total is None:
        return None

    delta = hist.averages.avg_putts_total - rnd.putts_total
    if delta >= 2:
        return _cand(
            "putts_total",
            "comparativa_historica",
            62,
            "🧠 El putt ayudó mucho: {putts_total} putts, {delta:.1f} mejor que tu media.",
            {
                "putts_total": rnd.putts_total,
                "delta": delta,
            },
        )

    return None


def rule_fir_strong(hist: HistorySnapshot, rnd: RoundSnapshot) -> Optional[InsightCandidate]:
    poss = _fir_possible(rnd)
    if rnd.fir_pct is not None and rnd.fir_pct >= 50 and poss >= 10:
        return _cand(
            "fir_strong",
            "comparativa_historica",
            60,
            "🎯 Muy sólido desde el tee: FIR {fir:.0f}% (en {poss} salidas medidas).",
            {"fir": rnd.fir_pct, "poss": poss},
        )
    return None


def rule_gir_strong(hist: HistorySnapshot, rnd: RoundSnapshot) -> Optional[InsightCandidate]:
    poss = _gir_possible(rnd)
    if rnd.gir_pct is not None and rnd.gir_pct >= 30 and poss >= 12:
        return _cand(
            "gir_strong",
            "comparativa_historica",
            60,
            "🟩 Buen día a green: GIR {gir:.0f}% (en {poss} greens medidos).",
            {"gir": rnd.gir_pct, "poss": poss},
        )
    return None


# =========================================================
# Reglas casi-logro / fallback
# =========================================================

def rule_near_from_achievements_ctx(
    hist: HistorySnapshot,
    rnd: RoundSnapshot,
    achievements_ctx: AchievementsContext | None,
) -> Optional[InsightCandidate]:
    if not achievements_ctx or not achievements_ctx.near:
        return None

    first = achievements_ctx.near[0]
    near_type = first.get("type")
    distance = first.get("distance")

    if near_type == "break_100" and distance is not None:
        return _cand(
            "near_break_100",
            "casi_logro",
            64,
            "👀 Te has quedado a {distance} golpes de bajar de 100. Está muy cerca.",
            {"distance": distance},
        )

    if near_type == "break_90" and distance is not None:
        return _cand(
            "near_break_90",
            "casi_logro",
            67,
            "👀 Te has quedado a {distance} golpes de bajar de 90. Ya lo tienes muy cerca.",
            {"distance": distance},
        )

    return None


def rule_best_hole_fallback(hist: HistorySnapshot, rnd: RoundSnapshot) -> Optional[InsightCandidate]:
    info = _best_hole_of_day(rnd)
    if not info:
        return None

    return _cand(
        "best_hole",
        "narrativa_resiliencia",
        45,
        "✨ Tu mejor hoyo fue el {best_hole}: {label} con {gross} golpes.",
        info,
    )


def rule_neutral_fallback(hist: HistorySnapshot, rnd: RoundSnapshot) -> InsightCandidate:
    return _cand(
        "neutral_fallback",
        "casi_logro",
        10,
        "📌 Vuelta completa. Elige 1 cosa concreta a mejorar en la próxima: tee, hierros o putt.",
        {},
    )


# =========================================================
# API principal de reglas
# =========================================================

def generate_candidates(
    hist: HistorySnapshot,
    rnd: RoundSnapshot,
    achievements_ctx: AchievementsContext | None = None,
) -> List[InsightCandidate]:
    cands: List[InsightCandidate] = []

    # Scorecard / narrativa
    for fn in (
        rule_birdie_simple,
        rule_many_pars,
        rule_bogey_golf,
        rule_no_triple_plus,
        rule_damage_control_no_points,
        rule_bounce_back_after_big_hole,
        rule_strong_finish_16_18,
    ):
        c = fn(hist, rnd)
        if c:
            cands.append(c)

    # Comparativa histórica
    if hist.has_min_history:
        for fn in (
            rule_gross_improvement,
            rule_putts_per_hole_improvement,
            rule_putts_total_improvement,
            rule_fir_strong,
            rule_gir_strong,
        ):
            c = fn(hist, rnd)
            if c:
                cands.append(c)

    # Casi logro
    c = rule_near_from_achievements_ctx(hist, rnd, achievements_ctx)
    if c:
        cands.append(c)

    # Fallbacks
    c = rule_best_hole_fallback(hist, rnd)
    if c:
        cands.append(c)

    cands.append(rule_neutral_fallback(hist, rnd))
    return cands