from __future__ import annotations

from typing import Any

from app.insights.types import RoundSnapshot


def _diff_label(diff: int | None) -> str:
    if diff is None:
        return "—"
    if diff == 0:
        return "E"
    if diff > 0:
        return f"+{diff}"
    return str(diff)  # -1, -2...


def _color_for_diff(diff: int | None, gross: int | None = None) -> tuple[str, str]:
    if diff is None:
        return ("#ffffff", "#6b7280")

    # Hole in one
    if gross == 1:
        return ("#f4b400", "#000000")

    # Albatros
    if diff <= -3:
        return ("#ffd6cc", "#000000")

    # Eagle
    if diff == -2:
        return ("#ffb3a6", "#000000")

    # Birdie → rojo
    if diff == -1:
        return ("#ff8a80", "#000000")

    # Par → verde
    if diff == 0:
        return ("#c8e6c9", "#000000")

    # Bogey → azul
    if diff == 1:
        return ("#bbdefb", "#000000")

    # Doble bogey → gris
    if diff == 2:
        return ("#e0e0e0", "#000000")

    # Triple o peor → gris oscuro
    return ("#bdbdbd", "#000000")


def _flag(v: bool | None) -> str:
    if v is True:
        return "hit"
    if v is False:
        return "miss"
    return "na"



def build_email_scorecard_rows(
    rnd: RoundSnapshot,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Returns (holes_out, holes_in) as lists of dicts for the email template.
    Cada hoyo ya trae stableford_points dentro de HoleSnapshot.
    """
    # Aseguramos orden por hoyo 1..18
    holes_sorted = sorted(rnd.holes, key=lambda h: h.hole_number)

    rows: list[dict[str, Any]] = []
    for h in holes_sorted:
        gross = h.gross_strokes
        par = h.par if h.par else None

        diff = None
        if gross is not None and par is not None:
            # HIO lo tratamos por gross==1 dentro de _color_for_diff()
            diff = gross - par

        bg, fg = _color_for_diff(diff, gross)

        pts = getattr(h, "stableford_points", None)
        putts = h.putts

        rows.append(
            {
                "n": h.hole_number,
                "par": par if par is not None else "—",
                "gross": gross if gross is not None else "—",
                "diff_label": _diff_label(diff),
                "bg": bg,
                "fg": fg,
                "pts": pts if pts is not None else "—",
                "putts": putts if putts is not None else "—",
                "fir": _flag(h.fir),
                "gir": _flag(h.gir),
            }
        )

    holes_out = rows[:9]
    holes_in = rows[9:18]
    return holes_out, holes_in