from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from . import models, crud



# ============================================================
# Helpers DB
# ============================================================

def find_achievement_id_by_number(db: Session, number: int) -> int | None:
    # Acepta "04." y "4." (por si el admin edita nombres)
    p1 = f"{number:02d}."
    p2 = f"{number}."

    ach = (
        db.query(models.Achievement)
        .filter(
            (models.Achievement.name.ilike(f"{p1}%")) |
            (models.Achievement.name.ilike(f"{p2}%"))
        )
        .first()
    )
    return ach.id if ach else None


def set_achievement_auto(db: Session, player_id: int, achievement_id: int, achieved: bool) -> None:
    """
    AUTO = solo desbloquea.
    - achieved=False: NO revoca (no apaga).
    - Respeta locked_by_admin.
    """
    if not achieved:
        return

    pa = (
        db.query(models.PlayerAchievement)
        .filter(
            models.PlayerAchievement.player_id == player_id,
            models.PlayerAchievement.achievement_id == achievement_id,
        )
        .first()
    )

    now = datetime.utcnow()

    if pa:
        if pa.locked_by_admin:
            return
        if not pa.unlocked:
            pa.unlocked = True
            pa.unlocked_at = now
            pa.source = "auto"
    else:
        pa = models.PlayerAchievement(
            player_id=player_id,
            achievement_id=achievement_id,
            unlocked=True,
            unlocked_at=now,
            source="auto",
            locked_by_admin=False,
        )
        db.add(pa)

    db.commit()


def get_round_hole_stats(db: Session, round_id: int, player_id: int):
    """
    Devuelve lista ordenada por hoyo de tuplas:
    (hole_number, par, fir, gir, putts, gross_strokes)

    Nota: par viene de Hole cruzando por course_id de la Round.
    """
    return (
        db.query(
            models.HoleScore.hole_number,
            models.Hole.par,
            models.HoleScore.fir,
            models.HoleScore.gir,
            models.HoleScore.putts,
            models.HoleScore.gross_strokes,
        )
        .join(models.RoundPlayer, models.HoleScore.round_player_id == models.RoundPlayer.id)
        .join(models.Round, models.RoundPlayer.round_id == models.Round.id)
        .join(
            models.Hole,
            and_(
                models.Hole.course_id == models.Round.course_id,
                models.Hole.number == models.HoleScore.hole_number,
            )
        )
        .filter(models.Round.id == round_id)
        .filter(models.RoundPlayer.player_id == player_id)
        .order_by(models.HoleScore.hole_number.asc())
        .all()
    )


def count_player_birdies(db: Session, player_id: int) -> int:
    """
    Cuenta birdies globales del jugador SOLO en rondas cerradas.
    Criterio de cierre actual: Round.winner_type IS NOT NULL
    Birdie = gross_strokes == (par - 1)
    """
    q = (
        db.query(models.HoleScore)
        .join(models.RoundPlayer, models.HoleScore.round_player_id == models.RoundPlayer.id)
        .join(models.Round, models.RoundPlayer.round_id == models.Round.id)
        .join(
            models.Hole,
            and_(
                models.Hole.course_id == models.Round.course_id,
                models.Hole.number == models.HoleScore.hole_number,
            )
        )
        .filter(models.RoundPlayer.player_id == player_id)
        .filter(models.Round.winner_type.isnot(None))  # ✅ solo rondas cerradas
        .filter(models.HoleScore.gross_strokes == (models.Hole.par - 1))
    )
    return q.count()

def count_player_closed_rounds(db: Session, player_id: int) -> int:
    """
    Cuenta rondas cerradas del jugador.
    Criterio: Round.winner_type IS NOT NULL
    """
    return (
        db.query(models.Round)
        .join(models.RoundPlayer, models.RoundPlayer.round_id == models.Round.id)
        .filter(models.RoundPlayer.player_id == player_id)
        .filter(models.Round.winner_type.isnot(None))  # ✅ solo cerradas
        .distinct()
        .count()
    )


def compute_level_hcp_for_round_player(db: Session, rp: models.RoundPlayer) -> float | None:
    """
    Calcula el "Nivel juego (HCP)" de UNA vuelta para un RoundPlayer:
    level_hcp = ((gross_total - rating_yellow) * 113) / slope_yellow

    Devuelve None si falta algún dato.
    """
    if rp.gross_total is None:
        return None

    r = db.query(models.Round).filter(models.Round.id == rp.round_id).first()
    if not r:
        return None

    c = db.query(models.Course).filter(models.Course.id == r.course_id).first()
    if not c:
        return None

    rating = getattr(c, "rating_yellow", None)
    slope = getattr(c, "slope_yellow", None)

    if rating is None or slope in (None, 0):
        return None

    return ((rp.gross_total - float(rating)) * 113.0) / float(slope)

def count_total_achievements_excluding(db: Session, exclude_achievement_id: int) -> int:
    """
    Total de logros en el catálogo, excluyendo uno (normalmente el 24).
    """
    return (
        db.query(models.Achievement.id)
        .filter(models.Achievement.id != exclude_achievement_id)
        .count()
    )


def count_player_unlocked_achievements_excluding(db: Session, player_id: int, exclude_achievement_id: int) -> int:
    """
    Total de logros desbloqueados por el jugador, excluyendo uno (normalmente el 24).
    """
    return (
        db.query(models.PlayerAchievement.id)
        .filter(models.PlayerAchievement.player_id == player_id)
        .filter(models.PlayerAchievement.unlocked.is_(True))
        .filter(models.PlayerAchievement.achievement_id != exclude_achievement_id)
        .count()
    )


def player_has_all_achievements(db: Session, player_id: int, all_achievement_id: int) -> bool:
    """
    Devuelve True si el jugador tiene todos los logros del catálogo desbloqueados
    (excepto el propio logro "Todos los logros").
    """
    total = count_total_achievements_excluding(db, all_achievement_id)
    if total <= 0:
        return False

    unlocked = count_player_unlocked_achievements_excluding(db, player_id, all_achievement_id)
    return unlocked >= total



# ============================================================
# Evaluadores (solo lógica, sin DB)
# ============================================================

def eval_round_flags(stats_rows) -> dict:
    """
    Flags para logros por ronda:
    - desde_fuera: existe putts == 0
    - hole_in_one: existe gross == 1
    - eagle: existe gross == par - 2
    - no_triple_bogey: ningún hoyo con gross >= par + 3
    - tripateo_free: ningún hoyo con putts >= 3 (si putts None, asume 3)
    """
    if not stats_rows:
        return {
            "desde_fuera": False,
            "no_triple_bogey": False,
            "tripateo_free": False,
            "hole_in_one": False,
            "eagle": False,
        }

    desde_fuera = any((putts is not None and putts == 0) for _, _, _, _, putts, _ in stats_rows)
    hole_in_one = any(
        gross == 1
        for _, _, _, _, _, gross in stats_rows
    )

    eagle = any(
        (gross == par - 2) and (gross != 1)
        for _, par, _, _, _, gross in stats_rows
    )

    # triple bogey o peor => gross >= par+3, así que "no triple bogey" => gross <= par+2
    no_triple_bogey = all(gross <= (par + 2) for _, par, _, _, _, gross in stats_rows)

    # Si putts es None, lo tratamos como 3 (tu regla de negocio)
    tripateo_free = all(((putts if putts is not None else 3) <= 2) for _, _, _, _, putts, _ in stats_rows)

    return {
        "desde_fuera": desde_fuera,
        "no_triple_bogey": no_triple_bogey,
        "tripateo_free": tripateo_free,
        "hole_in_one": hole_in_one,
        "eagle": eagle,
    }


def eval_fir_gir_achievements(stats_rows) -> dict:
    """
    Flags:
    - fir_70: FIR >= 70% en par4/5
    - gir_50: GIR >= 50% en todos los hoyos (normalmente 18)
    - par3_all_gir: GIR en todos los par3
    """
    if not stats_rows:
        return {"fir_70": False, "gir_50": False, "par3_all_gir": False}

    # FIR: solo par 4/5
    fir_rows = [r for r in stats_rows if r[1] >= 4]
    fir_total = len(fir_rows)
    fir_hits = sum(1 for _, _, fir, _, _, _ in fir_rows if fir is True)
    fir_70 = (fir_total > 0) and ((fir_hits / fir_total) >= 0.70)

    # GIR: None cuenta como False
    gir_hits = sum(1 for _, _, _, gir, _, _ in stats_rows if gir is True)
    gir_total = len(stats_rows)
    gir_50 = (gir_total > 0) and ((gir_hits / gir_total) >= 0.50)

    # Par3 con GIR: todos los par3 deben tener gir True
    par3_rows = [r for r in stats_rows if r[1] == 3]
    par3_all_gir = (len(par3_rows) > 0) and all(gir is True for _, _, _, gir, _, _ in par3_rows)

    return {"fir_70": fir_70, "gir_50": gir_50, "par3_all_gir": par3_all_gir}


def eval_streak_and_par_achievements(stats_rows) -> dict:
    """
    Flags:
    - birdie3plus_in_round: 3 birdies o mejor (gross <= par-1), no necesariamente consecutivos
    - par3_all_par_or_better: suma total en par3 <= par total de los par3
    - par5_all_par_or_better: suma total en par5 <= par total de los par5
    - five_par_or_better_streak: hay 5 hoyos consecutivos con gross <= par
    """
    if not stats_rows:
        return {
            "birdie3plus_in_round": False,
            "par3_all_par_or_better": False,
            "par5_all_par_or_better": False,
            "five_par_or_better_streak": False,
        }

    # 18) 3 birdies o mejor (no consecutivos)
    birdie_or_better_count = sum(
        1 for _, par, _, _, _, gross in stats_rows
        if gross is not None and gross <= (par - 1)
    )
    birdie3plus_in_round = birdie_or_better_count >= 3

    # 21) Rey del Par3 → suma total
    par3_rows = [r for r in stats_rows if r[1] == 3]
    par3_all_par_or_better = False
    if len(par3_rows) > 0:
        par3_sum = sum(gross for _, _, _, _, _, gross in par3_rows if gross is not None)
        par3_par_total = 3 * len(par3_rows)
        par3_all_par_or_better = par3_sum <= par3_par_total

    # 22) Rey del Par5 → suma total
    par5_rows = [r for r in stats_rows if r[1] == 5]
    par5_all_par_or_better = False
    if len(par5_rows) > 0:
        par5_sum = sum(gross for _, _, _, _, _, gross in par5_rows if gross is not None)
        par5_par_total = 5 * len(par5_rows)
        par5_all_par_or_better = par5_sum <= par5_par_total

    # 23) 5 pares o mejor consecutivos
    flags = [
        (gross is not None and gross <= par)
        for _, par, _, _, _, gross in stats_rows
    ]

    run = 0
    five_par_or_better_streak = False
    for ok in flags:
        if ok:
            run += 1
            if run >= 5:
                five_par_or_better_streak = True
                break
        else:
            run = 0

    return {
        "birdie3plus_in_round": birdie3plus_in_round,
        "par3_all_par_or_better": par3_all_par_or_better,
        "par5_all_par_or_better": par5_all_par_or_better,
        "five_par_or_better_streak": five_par_or_better_streak,
    }



# ============================================================
# Entry points
# ============================================================

def evaluate_achievements_on_round_close(db: Session, round_id: int) -> None:
    """
    Se llama al cerrar ronda. Evalúa logros automáticos.
    """
    # IDs logros (score bruto)
    ach_100 = find_achievement_id_by_number(db, 4)
    ach_90  = find_achievement_id_by_number(db, 5)
    ach_80  = find_achievement_id_by_number(db, 6)

    # Birdies acumulados
    ach_b10 = find_achievement_id_by_number(db, 13)
    ach_b25 = find_achievement_id_by_number(db, 14)
    ach_b50 = find_achievement_id_by_number(db, 15)

    # Por ronda (hoyos)
    ach_out = find_achievement_id_by_number(db, 7)
    ach_no3 = find_achievement_id_by_number(db, 16)
    ach_3pf = find_achievement_id_by_number(db, 17)
    ach_hio = find_achievement_id_by_number(db, 11)
    ach_eag = find_achievement_id_by_number(db, 12)

    # FIR/GIR
    ach_fir70 = find_achievement_id_by_number(db, 9)
    ach_gir50 = find_achievement_id_by_number(db, 10)
    ach_par3g = find_achievement_id_by_number(db, 19)

    # 18/21/22/23
    ach_bbb     = find_achievement_id_by_number(db, 18)
    ach_par3    = find_achievement_id_by_number(db, 21)
    ach_par5    = find_achievement_id_by_number(db, 22)
    ach_streak5 = find_achievement_id_by_number(db, 23)

    ach_hcp18 = find_achievement_id_by_number(db, 8)
    ach_addict100 = find_achievement_id_by_number(db, 20)
    ach_all = find_achievement_id_by_number(db, 24)

    # ✅ OJO: NO return temprano por un subset (antes te cortaba cosas)
    if not any([
        ach_100, ach_90, ach_80,
        ach_b10, ach_b25, ach_b50,
        ach_out, ach_no3, ach_3pf, ach_hio, ach_eag,
        ach_fir70, ach_gir50, ach_par3g,
        ach_bbb, ach_par3, ach_par5, ach_streak5,
        ach_hcp18, 
        ach_addict100,
    ]):
        return

    rps = (
        db.query(models.RoundPlayer)
        .filter(models.RoundPlayer.round_id == round_id)
        .all()
    )

    processed_players: set[int] = set()

    for rp in rps:
        if not rp.player_id:
            continue
        player_id = rp.player_id

        # 04/05/06 (bruto)
        if rp.gross_total is not None:
            gross = rp.gross_total
            if ach_100:
                set_achievement_auto(db, player_id, ach_100, gross < 100)
            if ach_90:
                set_achievement_auto(db, player_id, ach_90, gross < 90)
            if ach_80:
                set_achievement_auto(db, player_id, ach_80, gross < 80)

        # Birdies globales (una vez por jugador)
        if player_id not in processed_players:
            processed_players.add(player_id)
            if any([ach_b10, ach_b25, ach_b50]):
                birdies_total = count_player_birdies(db, player_id)
                if ach_b10:
                    set_achievement_auto(db, player_id, ach_b10, birdies_total >= 10)
                if ach_b25:
                    set_achievement_auto(db, player_id, ach_b25, birdies_total >= 25)
                if ach_b50:
                    set_achievement_auto(db, player_id, ach_b50, birdies_total >= 50)

        # 20) Adicto al juego (100 rondas cerradas)
            if ach_addict100:
                rounds_closed = count_player_closed_rounds(db, player_id)
                set_achievement_auto(db, player_id, ach_addict100, rounds_closed >= 100)

        # 24) Todos los logros (global)
            if ach_all:
                if player_has_all_achievements(db, player_id, ach_all):
                    set_achievement_auto(db, player_id, ach_all, True)


        # Datos hoyo-a-hoyo (una sola query) para el resto
        needs_rows = any([
            ach_out, ach_no3, ach_3pf, ach_hio, ach_eag,
            ach_fir70, ach_gir50, ach_par3g,
            ach_bbb, ach_par3, ach_par5, ach_streak5
        ])

        if not needs_rows:
            continue

        stats_rows = get_round_hole_stats(db, round_id, player_id)

        # 07/11/12/16/17
        if any([ach_out, ach_no3, ach_3pf, ach_hio, ach_eag]):
            flags = eval_round_flags(stats_rows)
            if ach_out:
                set_achievement_auto(db, player_id, ach_out, flags["desde_fuera"])
            if ach_no3:
                set_achievement_auto(db, player_id, ach_no3, flags["no_triple_bogey"])
            if ach_3pf:
                set_achievement_auto(db, player_id, ach_3pf, flags["tripateo_free"])
            if ach_hio:
                set_achievement_auto(db, player_id, ach_hio, flags["hole_in_one"])
            if ach_eag:
                set_achievement_auto(db, player_id, ach_eag, flags["eagle"])

        # 09/10/19
        if any([ach_fir70, ach_gir50, ach_par3g]):
            fg = eval_fir_gir_achievements(stats_rows)
            if ach_fir70:
                set_achievement_auto(db, player_id, ach_fir70, fg["fir_70"])
            if ach_gir50:
                set_achievement_auto(db, player_id, ach_gir50, fg["gir_50"])
            if ach_par3g:
                set_achievement_auto(db, player_id, ach_par3g, fg["par3_all_gir"])

        # 18/21/22/23
        if any([ach_bbb, ach_par3, ach_par5, ach_streak5]):
            sp = eval_streak_and_par_achievements(stats_rows)
            if ach_bbb:
                set_achievement_auto(db, player_id, ach_bbb, sp["birdie3plus_in_round"])
            if ach_par3:
                set_achievement_auto(db, player_id, ach_par3, sp["par3_all_par_or_better"])
            if ach_par5:
                set_achievement_auto(db, player_id, ach_par5, sp["par5_all_par_or_better"])
            if ach_streak5:
                set_achievement_auto(db, player_id, ach_streak5, sp["five_par_or_better_streak"])
        
        # 08 HCP 18 (nivel juego real de esa ronda)
        if ach_hcp18:
            level_hcp = compute_level_hcp_for_round_player(db, rp)
            if level_hcp is not None:
                set_achievement_auto(db, player_id, ach_hcp18, level_hcp <= 18.0)


# ============================================================
# Liga: logros 01/02/03
# ============================================================

def award_league_champion_achievements(
    db: Session,
    main_champions: list[models.Player],
    net_champions: list[models.Player],
    scratch_champions: list[models.Player],
) -> None:
    """
    Otorga logros de liga (01/02/03) a los campeones calculados al cerrar la liga.
    """
    ach_01 = find_achievement_id_by_number(db, 1)  # 01. Campeón Liga
    ach_02 = find_achievement_id_by_number(db, 2)  # 02. Campeón Golpes
    ach_03 = find_achievement_id_by_number(db, 3)  # 03. Campeón Puntos

    if ach_01:
        for p in (main_champions or []):
            if p and getattr(p, "id", None):
                set_achievement_auto(db, p.id, ach_01, True)

    if ach_02:
        for p in (net_champions or []):
            if p and getattr(p, "id", None):
                set_achievement_auto(db, p.id, ach_02, True)

    if ach_03:
        for p in (scratch_champions or []):
            if p and getattr(p, "id", None):
                set_achievement_auto(db, p.id, ach_03, True)

    # 24) Todos los logros (re-evaluación tras otorgar logros de liga)
    ach_all = find_achievement_id_by_number(db, 24)
    if ach_all:
        # revisa candidatos de esta liga (los campeones que acabas de premiar)
        candidates = []
        candidates.extend(main_champions or [])
        candidates.extend(net_champions or [])
        candidates.extend(scratch_champions or [])

        # evitar duplicados por id
        seen: set[int] = set()
        for p in candidates:
            if not p or not getattr(p, "id", None):
                continue
            if p.id in seen:
                continue
            seen.add(p.id)

            if player_has_all_achievements(db, p.id, ach_all):
                set_achievement_auto(db, p.id, ach_all, True)


def evaluate_achievements_on_league_close(db: Session, league_id: int) -> None:
    """
    Se llama cuando cierras la liga. Calcula campeones desde standings y otorga 01/02/03.
    """
    league = db.query(models.League).filter(models.League.id == league_id).first()
    if not league or not getattr(league, "is_closed", False):
        return

    rounds = (
        db.query(models.Round)
        .filter(models.Round.league_id == league_id)
        .all()
    )

    standings = crud.compute_league_standings(db, league, rounds)

    main_ids = standings["champions"]["main_players"]
    net_ids = standings["champions"]["net_players"]
    scratch_ids = standings["champions"]["scratch_players"]

    main_players = db.query(models.Player).filter(models.Player.id.in_(main_ids)).all() if main_ids else []
    net_players = db.query(models.Player).filter(models.Player.id.in_(net_ids)).all() if net_ids else []
    scratch_players = db.query(models.Player).filter(models.Player.id.in_(scratch_ids)).all() if scratch_ids else []

    award_league_champion_achievements(
        db,
        main_champions=main_players,
        net_champions=net_players,
        scratch_champions=scratch_players,
    )

from sqlalchemy import func  # arriba del archivo si no lo tienes


def reset_player_auto_achievements(db: Session, player_id: int) -> None:
    """
    Reset total del estado AUTO del jugador:
    - Borra TODO PlayerAchievement del jugador que NO sea un bloqueo manual "positivo".
    - Como tú quieres que Reset recupere, borramos también los bloqueos manuales (unlocked=False).
    """
    rows = (
        db.query(models.PlayerAchievement)
        .filter(models.PlayerAchievement.player_id == player_id)
        .all()
    )

    for pa in rows:
        # Si algún día quieres "bloqueo permanente", este sería el único que conservarías.
        # Pero ahora mismo, tu regla es: reset recupera -> así que solo conservaríamos manual unlocked=True.
        if pa.source == "manual" and pa.unlocked is True and pa.locked_by_admin:
            continue

        db.delete(pa)

    db.commit()


def recalculate_player_auto_achievements(db: Session, player_id: int) -> None:
    """
    Recalcula AUTO desde TODAS las rondas cerradas del jugador.
    Criterio de cierre: Round.winner_type IS NOT NULL
    """
    round_ids = (
        db.query(models.Round.id)
        .join(models.RoundPlayer, models.RoundPlayer.round_id == models.Round.id)
        .filter(models.RoundPlayer.player_id == player_id)
        .filter(models.Round.winner_type.isnot(None))
        .order_by(models.Round.date.asc(), models.Round.id.asc())
        .all()
    )
    round_ids = [rid for (rid,) in round_ids]

    for rid in round_ids:
        evaluate_achievements_on_round_close(db, rid)

    # ✅ NUEVO: recalcular logros de ligas cerradas donde participa el jugador
    league_ids = (
        db.query(models.League.id)
        .join(models.Round, models.Round.league_id == models.League.id)
        .join(models.RoundPlayer, models.RoundPlayer.round_id == models.Round.id)
        .filter(models.RoundPlayer.player_id == player_id)
        .filter(models.League.is_closed.is_(True))
        .distinct()
        .all()
    )
    league_ids = [lid for (lid,) in league_ids]

    for lid in league_ids:
        evaluate_achievements_on_league_close(db, lid)
