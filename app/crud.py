from sqlalchemy.orm import Session
from . import models, schemas
from collections import defaultdict




#---------------------------------------------------------------------------------
# ---------------------------------- Players -------------------------------------
# --------------------------------------------------------------------------------

def get_players(db: Session):
    return db.query(models.Player).order_by(models.Player.name).all()

def get_player(db: Session, player_id: int):
    return db.query(models.Player).filter(models.Player.id == player_id).first()

def create_player(db: Session, data: schemas.PlayerCreate):
    p = models.Player(**data.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p

def update_player(db: Session, player_id: int, data: schemas.PlayerUpdate):
    p = get_player(db, player_id)
    if not p:
        return None
    for k, v in data.model_dump().items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return p

def delete_player(db: Session, player_id: int):
    p = get_player(db, player_id)
    if not p:
        return False
    db.delete(p)
    db.commit()
    return True


#---------------------------------------------------------------------------------
# ------------------------------------ Course ------------------------------------
# --------------------------------------------------------------------------------

def get_courses(db: Session):
    return db.query(models.Course).order_by(models.Course.name).all()

def get_course(db: Session, course_id: int):
    return db.query(models.Course).filter(models.Course.id == course_id).first()

def create_course(db: Session, data: schemas.CourseCreate):
    c = models.Course(**data.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c

def update_course(db: Session, course_id: int, data: schemas.CourseUpdate):
    c = get_course(db, course_id)
    if not c:
        return None
    for k, v in data.model_dump().items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    return c

def delete_course(db: Session, course_id: int):
    c = get_course(db, course_id)
    if not c:
        return False
    db.delete(c)
    db.commit()
    return True



#---------------------------------------------------------------------------------
# ------------------------------------- Holes ------------------------------------
# --------------------------------------------------------------------------------


def get_holes_for_course(db: Session, course_id: int):
    return (
        db.query(models.Hole)
        .filter(models.Hole.course_id == course_id)
        .order_by(models.Hole.number)
        .all()
    )

def upsert_holes_for_course(db: Session, course_id: int, holes_data):
    # En MVP: borramos y reinsertamos los 18 hoyos
    db.query(models.Hole).filter(models.Hole.course_id == course_id).delete()
    db.commit()

    for h in holes_data:
        hole = models.Hole(course_id=course_id, **h.model_dump())
        db.add(hole)

    db.commit()

from datetime import date
from .golf_calc import course_handicap, strokes_received_per_hole, stableford_points




#---------------------------------------------------------------------------------
# ------------------------------------- Rounds ------------------------------------
# --------------------------------------------------------------------------------



def create_round(db, round_date, course_id, tee, round_type, player_ids, league_id=None):
    r = models.Round(
        date=round_date,
        course_id=course_id,
        tee=tee,
        type=round_type,
        league_id=league_id   # ✅ nuevo campo
    )
    db.add(r)
    db.commit()
    db.refresh(r)

    course = get_course(db, course_id)

    for pid in player_ids:
        player = get_player(db, pid)
        ch = course_handicap(player.hcp_exact, course.slope_yellow)

        rp = models.RoundPlayer(
            round_id=r.id,
            player_id=pid,
            hcp_exact_day=player.hcp_exact,
            course_handicap=ch
        )
        db.add(rp)

    db.commit()
    return r

def get_rounds(db):
    return (
        db.query(models.Round)
        .order_by(models.Round.date.desc(), models.Round.id.desc())
        .all()
    )


def delete_round(db, round_id):
    r = get_round(db, round_id)
    if not r:
        return

    # Borramos primero los RoundPlayer (sus HoleScore se borran por cascade)
    for rp in r.round_players:
        db.delete(rp)

    db.delete(r)
    db.commit()


def get_rounds_by_league(db, league_id):
    return (
        db.query(models.Round)
        .filter(models.Round.league_id == league_id)
        .order_by(models.Round.date.asc())
        .all()
    )

from collections import defaultdict

def compute_league_standings(db: Session, league, rounds):
    """
    Calcula:
    - Clasificación principal (sistema F1: jugadores-1, empates reparten)
    - Clasificación por golpes netos (media)
    - Clasificación por puntos scratch (suma)
    - Tabla ampliada por jugador para la liga (como en tu Excel)
    Y determina campeones cuando la liga está cerrada.
    """

    # stats por jugador dentro de esta liga
    stats = defaultdict(lambda: {
        "player": None,
        "rounds": 0,
        "wins": 0,
        "ties": 0,
        "f1_points": 0.0,

        "gross_sum": 0,
        "gross_count": 0,
        "best_gross": None,

        "net_sum": 0,
        "net_count": 0,

        "scratch_sum": 0,
        "stableford_sum": 0,  # ✅ suma de puntos Stableford HCP en la liga

        "level_hcp_sum": 0.0,
        "level_hcp_count": 0,
    })

    # --- RECORRER TODAS LAS RONDAS DE LA LIGA ---
    for r in rounds:
        rps = [rp for rp in r.round_players if rp.gross_total is not None]
        n = len(rps)
        if n == 0:
            continue

        # ordenar por puntos Stableford HCP (desc) para F1
        rps_sorted = sorted(
            rps,
            key=lambda rp: (rp.stableford_hcp_total is None,
                            -(rp.stableford_hcp_total or 0))
        )

        # actualizar stats base por jugador
        for rp in rps:
            s = stats[rp.player_id]
            if s["player"] is None:
                s["player"] = rp.player

            s["rounds"] += 1

            # resultado win/tie desde RoundPlayer.result
            if rp.result == "win":
                s["wins"] += 1
            elif rp.result == "tie":
                s["ties"] += 1

            # gross
            if rp.gross_total is not None:
                s["gross_sum"] += rp.gross_total
                s["gross_count"] += 1
                if s["best_gross"] is None or rp.gross_total < s["best_gross"]:
                    s["best_gross"] = rp.gross_total

                # nivel de juego para esta vuelta
                course = r.course
                if course and course.slope_yellow and course.rating_yellow is not None:
                    level_hcp = ((rp.gross_total - course.rating_yellow) * 113) / course.slope_yellow
                    s["level_hcp_sum"] += level_hcp
                    s["level_hcp_count"] += 1

            # net
            if rp.net_total is not None:
                s["net_sum"] += rp.net_total
                s["net_count"] += 1

            # scratch points
            if rp.stableford_scratch_total is not None:
                s["scratch_sum"] += rp.stableford_scratch_total

            # puntos Stableford HCP (netos)
            if rp.stableford_hcp_total is not None:
                s["stableford_sum"] += rp.stableford_hcp_total


        # --- PUNTOS DE LIGA POR JORNADA ---
        # Regla: se reparten (n - 1) puntos entre los empatados en 1ª posición,
        # donde n es el nº de jugadores con resultado en esta vuelta.

        # Jugadores con puntos Stableford HCP válidos
        valid_rps = [rp for rp in rps_sorted if rp.stableford_hcp_total is not None]
        n_valid = len(valid_rps)
        if n_valid == 0:
            continue

        # Mejor resultado de la jornada
        best_points = valid_rps[0].stableford_hcp_total

        # Empatados en primera posición
        winners = [
            rp for rp in valid_rps
            if rp.stableford_hcp_total == best_points
        ]

        # Puntos totales a repartir en esta vuelta
        total_points_round = float(n_valid - 1)
        if total_points_round < 0:
            total_points_round = 0.0

        points_per_winner = total_points_round / len(winners) if winners else 0.0

        for rp in winners:
            stats[rp.player_id]["f1_points"] += points_per_winner


    # --- CONSTRUIR TABLAS ---

    main_rows = []
    net_rows = []
    scratch_rows = []
    players_table = []

    for player_id, s in stats.items():
        p = s["player"]
        rounds_played = s["rounds"]

        # principal F1
        main_rows.append({
            "player": p,
            "points": s["f1_points"],
            "rounds": rounds_played,
        })

        # netos
        if s["net_count"] > 0:
            avg_net = s["net_sum"] / s["net_count"]
            net_rows.append({
                "player": p,
                "avg_net": avg_net,
                "rounds": rounds_played,
            })

        # scratch
        if s["scratch_sum"] > 0:
            scratch_rows.append({
                "player": p,
                "total_scratch": s["scratch_sum"],
                "rounds": rounds_played,
            })

        # tabla ampliada por jugador
        avg_gross = (s["gross_sum"] / s["gross_count"]) if s["gross_count"] > 0 else None
        level_hcp = (s["level_hcp_sum"] / s["level_hcp_count"]) if s["level_hcp_count"] > 0 else None

        players_table.append({
            "player": p,
            "rounds": rounds_played,
            "wins": s["wins"],
            "ties": s["ties"],
            "gross_total": s["gross_sum"],
            "net_total": s["net_sum"],
            "stableford_total": s["stableford_sum"],  # ✅ ahora sí: suma de puntos Stableford HCP
            "scratch_total": s["scratch_sum"],
            "avg_gross": avg_gross,
            "level_hcp": level_hcp,
            "best_gross": s["best_gross"],
            "f1_points": s["f1_points"],
        })

    # ordenar clasificaciones
    main_rows = sorted(
        main_rows,
        key=lambda row: (-row["points"], -row["rounds"], row["player"].name)
    )

    net_rows = sorted(
        net_rows,
        key=lambda row: (row["avg_net"], -row["rounds"], row["player"].name)
    )

    scratch_rows = sorted(
        scratch_rows,
        key=lambda row: (-row["total_scratch"], -row["rounds"], row["player"].name)
    )

    # tabla grande ordenada por puntos de liga (F1)
    players_table = sorted(
        players_table,
        key=lambda row: (-row["f1_points"], row["player"].name)
    )

    # --- DETERMINAR CAMPEONES (solo si liga cerrada) ---
    main_champions = []
    net_champions = []
    scratch_champions = []

    if getattr(league, "is_closed", False):
        # 🏆 Campeones (puntos de liga)
        if main_rows:
            best_points = main_rows[0]["points"]
            main_champions = [
                row["player"] for row in main_rows
                if row["points"] == best_points
            ]

        # 🏆 Campeones por golpes netos (mínimo 5 vueltas)
        eligible_net = [row for row in net_rows if row["rounds"] >= 5]
        if eligible_net:
            best_avg_net = eligible_net[0]["avg_net"]
            net_champions = [
                row["player"] for row in eligible_net
                if row["avg_net"] == best_avg_net
            ]

        # 🏆 Campeones por puntos scratch
        if scratch_rows:
            best_scratch = scratch_rows[0]["total_scratch"]
            scratch_champions = [
                row["player"] for row in scratch_rows
                if row["total_scratch"] == best_scratch
            ]

    return {
        "main": main_rows,
        "net": net_rows,
        "scratch": scratch_rows,
        "players_table": players_table,
        "champions": {
            "main_players": [p.id for p in main_champions],
            "net_players": [p.id for p in net_champions],
            "scratch_players": [p.id for p in scratch_champions],
        }
    }


def get_round(db, round_id: int):
    return db.query(models.Round).filter(models.Round.id == round_id).first()

def get_round_players(db, round_id: int):
    return db.query(models.RoundPlayer).filter(models.RoundPlayer.round_id == round_id).all()

def get_round_player(db, rp_id: int):
    return db.query(models.RoundPlayer).filter(models.RoundPlayer.id == rp_id).first()


def save_card_for_round_player(db, rp: models.RoundPlayer, holes, gross_by_hole, putts_by_hole, fir_by_hole):
    # borrar tarjeta previa
    db.query(models.HoleScore).filter(models.HoleScore.round_player_id == rp.id).delete()
    db.commit()

    received = strokes_received_per_hole(rp.course_handicap, holes)

    gross_total = 0
    net_total = 0
    points_total = 0
    scratch_points_total = 0
    putts_total = 0

    birdies = eagles = pars = bogeys = dbl = overdbl = 0
    hio = albatros = 0

    par3_sum = par4_sum = par5_sum = 0
    par3_n = par4_n = par5_n = 0

    fir_total = 0
    fir_possible = 0
    gir_total = 0
    gir_possible = 0

    for h in holes:
        g = int(gross_by_hole[h.number])
        p_raw = putts_by_hole.get(h.number)
        p = int(p_raw) if p_raw not in (None, "", " ") else None

        net = g - received[h.number]
        pts = stableford_points(net, h.par)
        scratch_pts = stableford_points(g, h.par)

        gross_total += g
        net_total += net
        points_total += pts
        scratch_points_total += scratch_pts

        if p is not None:
            putts_total += p

        # FIR (solo par 4/5)
        fir_val = None
        if h.par != 3:
            fir_possible += 1
            fir_val = bool(fir_by_hole.get(h.number, False))
            if fir_val:
                fir_total += 1

        # GIR (si hay putts)
        gir_val = None
        if p is not None:
            gir_possible += 1
            gir_val = (g - p) <= (h.par - 2)
            if gir_val:
                gir_total += 1

        # resultados por gross vs par
        if g == 1:
            hio += 1
        else:
            d = g - h.par
            if d <= -3: albatros += 1
            elif d == -2: eagles += 1
            elif d == -1: birdies += 1
            elif d == 0: pars += 1
            elif d == 1: bogeys += 1
            elif d == 2: dbl += 1
            else: overdbl += 1

        # medias por par
        if h.par == 3:
            par3_sum += g; par3_n += 1
        elif h.par == 4:
            par4_sum += g; par4_n += 1
        elif h.par == 5:
            par5_sum += g; par5_n += 1

        hs = models.HoleScore(
            round_player_id=rp.id,
            hole_number=h.number,
            gross_strokes=g,
            putts=p,
            fir=fir_val,
            gir=gir_val,
            net_strokes=net,
            stableford_points=pts
        )
        db.add(hs)

    # guardar totales en RoundPlayer
    rp.gross_total = gross_total
    rp.net_total = net_total
    rp.stableford_hcp_total = points_total
    rp.stableford_scratch_total = scratch_points_total
    rp.putts_total = putts_total

    db.commit()

    return {
        "gross_total": gross_total,
        "net_total": net_total,
        "points_total": points_total,
        "fir_total": fir_total,
        "fir_possible": fir_possible,
        "gir_total": gir_total,
        "gir_possible": gir_possible,
        "hio": hio,
        "albatros": albatros,
        "eagles": eagles,
        "birdies": birdies,
        "pars": pars,
        "bogeys": bogeys,
        "dbl": dbl,
        "overdbl": overdbl
    }


def close_round_and_set_winner(db, round_id: int):
    r = get_round(db, round_id)
    rps = get_round_players(db, round_id)

    max_pts = max(rp.stableford_hcp_total for rp in rps if rp.stableford_hcp_total is not None)
    winners = [rp for rp in rps if rp.stableford_hcp_total == max_pts]

    if len(winners) == 1:
        r.winner_type = "single"
        r.winner_player_ids = str(winners[0].player_id)
        for rp in rps:
            rp.result = "win" if rp.id == winners[0].id else "loss"
    else:
        r.winner_type = "tie"
        r.winner_player_ids = ",".join(str(w.player_id) for w in winners)
        for rp in rps:
            rp.result = "tie" if rp in winners else "loss"

    db.commit()
def get_leagues(db: Session, only_open: bool = False):
    q = db.query(models.League)
    if only_open:
        q = q.filter(models.League.is_closed == False)
    return q.order_by(models.League.created_at.desc()).all()


def get_league(db: Session, league_id: int):
    return db.query(models.League).filter(models.League.id == league_id).first()


def create_league(db: Session, name: str, logo_url: str | None = None):
    league = models.League(
        name=name,
        logo_url=logo_url
    )
    db.add(league)
    db.commit()
    db.refresh(league)
    return league



def close_league(db: Session, league_id: int):
    league = get_league(db, league_id)
    if league:
        league.is_closed = True
        db.commit()
        db.refresh(league)
    return league

def get_player_league_titles_count(db: Session, player_id: int) -> int:
    """
    Cuenta cuántas ligas cerradas ha ganado un jugador (campeón principal),
    recalculando standings por liga (sin persistencia en BD).
    """
    leagues_closed = (
        db.query(models.League)
        .filter(models.League.is_closed == True)
        .order_by(models.League.created_at.desc())
        .all()
    )

    titles = 0

    for league in leagues_closed:
        rounds = get_rounds_by_league(db, league.id)
        standings = compute_league_standings(db, league, rounds)

        champions_main_ids = standings.get("champions", {}).get("main_players", [])
        if player_id in champions_main_ids:
            titles += 1

    return titles


# =======================================================================================
# ====================================== ACHIEVEMENTS ==================================
# =======================================================================================

def get_achievements(db: Session):
    """
    Devuelve todos los logros disponibles (catálogo de logros).
    """
    return (
        db.query(models.Achievement)
        .order_by(models.Achievement.name.asc())
        .all()
    )


def get_achievement(db: Session, achievement_id: int):
    """
    Devuelve un logro concreto por ID.
    """
    return (
        db.query(models.Achievement)
        .filter(models.Achievement.id == achievement_id)
        .first()
    )


def create_achievement(
    db: Session,
    name: str,
    description: str | None = None,
    icon: str | None = None,
):
    """
    Crea un logro nuevo en el catálogo (no lo asigna a nadie aún).
    """
    ach = models.Achievement(
        name=name,
        description=description,
        icon=icon,
    )
    db.add(ach)
    db.commit()
    db.refresh(ach)
    return ach


def update_achievement(
    db: Session,
    achievement_id: int,
    name: str | None = None,
    description: str | None = None,
    icon: str | None = None,
):
    """
    Actualiza los datos de un logro (nombre, descripción, icono).
    """
    ach = get_achievement(db, achievement_id)
    if not ach:
        return None

    if name is not None:
        ach.name = name
    if description is not None:
        ach.description = description
    if icon is not None:
        ach.icon = icon

    db.commit()
    db.refresh(ach)
    return ach


def delete_achievement(db: Session, achievement_id: int):
    """
    Elimina un logro del catálogo.
    OJO: también conviene borrar las asignaciones a jugadores.
    """
    ach = get_achievement(db, achievement_id)
    if not ach:
        return

    # Borramos primero las relaciones PlayerAchievement
    db.query(models.PlayerAchievement).filter(
        models.PlayerAchievement.achievement_id == achievement_id
    ).delete()

    db.delete(ach)
    db.commit()


# ------------------------ RELACIÓN PLAYER <-> ACHIEVEMENT -----------------------------


def get_player_achievements(db: Session, player_id: int):
    """
    Devuelve todos los logros asociados a un jugador.
    """
    return (
        db.query(models.PlayerAchievement)
        .filter(models.PlayerAchievement.player_id == player_id)
        .all()
    )


def assign_achievement_to_player(
    db: Session,
    player_id: int,
    achievement_id: int,
    unlocked: bool = True,
):
    """
    Asigna (o actualiza) un logro a un jugador.
    Si ya existía, solo se actualiza el estado.
    """
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
        pa.unlocked = unlocked
        if unlocked:
            pa.unlocked_at = now
    else:
        pa = models.PlayerAchievement(
            player_id=player_id,
            achievement_id=achievement_id,
            unlocked=unlocked,
            unlocked_at=now if unlocked else None,
        )
        db.add(pa)

    db.commit()
    db.refresh(pa)
    return pa


def revoke_achievement_from_player(
    db: Session,
    player_id: int,
    achievement_id: int,
):
    """
    Quita un logro a un jugador (borra la fila de PlayerAchievement).
    """
    pa = (
        db.query(models.PlayerAchievement)
        .filter(
            models.PlayerAchievement.player_id == player_id,
            models.PlayerAchievement.achievement_id == achievement_id,
        )
        .first()
    )

    if not pa:
        return

    db.delete(pa)
    db.commit()

from .models import PlayerAchievement

# Obtener logros asignados a un jugador
def get_player_achievements(db, player_id: int):
    return (
        db.query(PlayerAchievement)
        .filter(PlayerAchievement.player_id == player_id)
        .all()
    )

# Asignar logro al jugador (si no existe ya)
def assign_achievement_to_player(db, player_id: int, achievement_id: int):
    existing = (
        db.query(PlayerAchievement)
        .filter(
            PlayerAchievement.player_id == player_id,
            PlayerAchievement.achievement_id == achievement_id
        )
        .first()
    )
    if existing:
        return existing

    pa = PlayerAchievement(player_id=player_id, achievement_id=achievement_id)
    db.add(pa)
    db.commit()
    db.refresh(pa)
    return pa

# Eliminar logro del jugador
def remove_achievement_from_player(db, player_id: int, achievement_id: int):
    pa = (
        db.query(PlayerAchievement)
        .filter(
            PlayerAchievement.player_id == player_id,
            PlayerAchievement.achievement_id == achievement_id
        )
        .first()
    )
    if pa:
        db.delete(pa)
        db.commit()
