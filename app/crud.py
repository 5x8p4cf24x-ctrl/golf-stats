from sqlalchemy.orm import Session
from . import models, schemas
from collections import defaultdict
from .models import News
from datetime import datetime
from app.models import (
    Tournament,
    TournamentTeam,
    TournamentTeamPlayer,
    TournamentStage,
    TournamentMatch,
    TournamentMatchParticipant,
)



#---------------------------------------------------------------------------------
# ---------------------------------- Players -------------------------------------
# --------------------------------------------------------------------------------

def get_players(db: Session):
    return (
        db.query(models.Player)
        .filter(models.Player.active == True)
        .order_by(models.Player.name.asc())
        .all()
    )

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

def update_player_hcp(db: Session, player_id: int, hcp_exact: float):
    p = get_player(db, player_id)
    if not p:
        return None
    p.hcp_exact = hcp_exact
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



#---------------------------------------------------------------------------------
# ------------------------------------- Rounds ------------------------------------
# --------------------------------------------------------------------------------

from datetime import date
from .golf_calc import course_handicap, strokes_received_per_hole, stableford_points


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
        .filter(models.Round.is_cancelled.is_(False))
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
    Y devuelve campeones SI la liga está cerrada (PERO NO otorga logros aquí).
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
        "stableford_sum": 0,  # suma puntos Stableford HCP

        "level_hcp_sum": 0.0,
        "level_hcp_count": 0,
    })

    # --- RECORRER TODAS LAS RONDAS DE LA LIGA ---
    for r in rounds:
        rps = [rp for rp in r.round_players if rp.gross_total is not None]
        if not rps:
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

                # nivel de juego vuelta
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

            # puntos Stableford HCP
            if rp.stableford_hcp_total is not None:
                s["stableford_sum"] += rp.stableford_hcp_total

        # --- PUNTOS DE LIGA POR JORNADA (F1) ---
        valid_rps = [rp for rp in rps_sorted if rp.stableford_hcp_total is not None]
        n_valid = len(valid_rps)
        if n_valid == 0:
            continue

        best_points = valid_rps[0].stableford_hcp_total
        winners = [rp for rp in valid_rps if rp.stableford_hcp_total == best_points]

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

        main_rows.append({
            "player": p,
            "points": s["f1_points"],
            "rounds": rounds_played,
        })

        if s["net_count"] > 0:
            avg_net = s["net_sum"] / s["net_count"]
            net_rows.append({
                "player": p,
                "avg_net": avg_net,
                "rounds": rounds_played,
            })

        if s["scratch_sum"] > 0:
            scratch_rows.append({
                "player": p,
                "total_scratch": s["scratch_sum"],
                "rounds": rounds_played,
            })

        avg_gross = (s["gross_sum"] / s["gross_count"]) if s["gross_count"] > 0 else None
        level_hcp = (s["level_hcp_sum"] / s["level_hcp_count"]) if s["level_hcp_count"] > 0 else None

        players_table.append({
            "player": p,
            "rounds": rounds_played,
            "wins": s["wins"],
            "ties": s["ties"],
            "gross_total": s["gross_sum"],
            "net_total": s["net_sum"],
            "stableford_total": s["stableford_sum"],
            "scratch_total": s["scratch_sum"],
            "avg_gross": avg_gross,
            "level_hcp": level_hcp,
            "best_gross": s["best_gross"],
            "f1_points": s["f1_points"],
        })

    # ordenar
    main_rows = sorted(main_rows, key=lambda row: (-row["points"], -row["rounds"], row["player"].name))
    net_rows = sorted(net_rows, key=lambda row: (row["avg_net"], -row["rounds"], row["player"].name))
    scratch_rows = sorted(scratch_rows, key=lambda row: (-row["total_scratch"], -row["rounds"], row["player"].name))
    players_table = sorted(players_table, key=lambda row: (-row["f1_points"], row["player"].name))

    # --- CAMPEONES (solo calcular, NO escribir en DB aquí) ---
    main_champions = []
    net_champions = []
    scratch_champions = []

    if getattr(league, "is_closed", False):
        if main_rows:
            best = main_rows[0]["points"]
            main_champions = [row["player"] for row in main_rows if row["points"] == best]

        eligible_net = [row for row in net_rows if row["rounds"] >= 5]
        if eligible_net:
            best = eligible_net[0]["avg_net"]
            net_champions = [row["player"] for row in eligible_net if row["avg_net"] == best]

        if scratch_rows:
            best = scratch_rows[0]["total_scratch"]
            scratch_champions = [row["player"] for row in scratch_rows if row["total_scratch"] == best]

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

def delete_league(db: Session, league_id: int) -> bool:
    """
    Borra una liga SOLO si no tiene rondas asociadas.
    Devuelve True si borrada, False si no se puede (porque tiene rondas o no existe).
    """
    league = get_league(db, league_id)
    if not league:
        return False

    # Si hay rondas asociadas, no permitimos borrar (seguro)
    has_rounds = (
        db.query(models.Round.id)
        .filter(models.Round.league_id == league_id)
        .first()
        is not None
    )
    if has_rounds:
        return False

    db.delete(league)
    db.commit()
    return True



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

    # ✅ Si es entrenamiento, NO hay winner ni result
    if r and getattr(r, "context", None) == "training":
        r.winner_type = None
        r.winner_player_ids = None

        # muy importante: borrar resultados previos por si acaso
        rps = get_round_players(db, round_id)
        for rp in rps:
            rp.result = None

        db.commit()
        return

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

from datetime import datetime

def get_player_achievements(db: Session, player_id: int):
    """
    Devuelve TODAS las filas PlayerAchievement del jugador (unlocked True/False).
    Esto es clave para admin/debug porque una fila manual con unlocked=False y locked_by_admin=True
    sigue existiendo y bloquea el AUTO.
    """
    return (
        db.query(models.PlayerAchievement)
        .filter(models.PlayerAchievement.player_id == player_id)
        .all()
    )


def get_player_owned_achievement_ids(db: Session, player_id: int) -> set[int]:
    """
    Devuelve SOLO los achievement_id que el jugador tiene desbloqueados (unlocked=True).
    Ideal para el template.
    """
    rows = (
        db.query(models.PlayerAchievement.achievement_id)
        .filter(
            models.PlayerAchievement.player_id == player_id,
            models.PlayerAchievement.unlocked == True,
        )
        .all()
    )
    return {aid for (aid,) in rows}


def assign_achievement_to_player(db: Session, player_id: int, achievement_id: int):
    """
    Asignación MANUAL:
    - unlocked=True
    - source='manual'
    - locked_by_admin=True (el motor AUTO no toca)
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
        pa.unlocked = True
        pa.unlocked_at = now
        pa.source = "manual"
        pa.locked_by_admin = True
    else:
        pa = models.PlayerAchievement(
            player_id=player_id,
            achievement_id=achievement_id,
            unlocked=True,
            unlocked_at=now,
            source="manual",
            locked_by_admin=True,
        )
        db.add(pa)

    db.commit()
    db.refresh(pa)
    return pa


def remove_achievement_from_player(db: Session, player_id: int, achievement_id: int):
    """
    “Quitar” TEMPORAL:
    - Deja de mostrarlo (unlocked=False)
    - NO bloquea el AUTO (locked_by_admin=False)
    - Reset AUTO + Recalcular lo puede recuperar
    - No crea filas nuevas si no existía el logro
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
        return None  # no había nada que quitar

    pa.unlocked = False
    pa.unlocked_at = None
    pa.locked_by_admin = False
    # pa.source = pa.source  # no hace falta tocarlo
    db.commit()
    db.refresh(pa)
    return pa



# ==============================================================================
# NEWS – READ
# ==============================================================================

def get_latest_news(db: Session, limit: int = 6):
    return (
        db.query(News)
        .filter(News.published == True)
        .order_by(News.created_at.desc())
        .limit(limit)
        .all()
    )

def get_news_page(db: Session, skip: int = 0, limit: int = 30):
    return (
        db.query(News)
        .filter(News.published == True)
        .order_by(News.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

# ==============================================================================
# NEWS – CREATE / DELETE
# ==============================================================================

DEFAULT_NEWS_IMAGES = {
    "league": "news/default_league.jpg",
    "achievement": "news/default_achievement.jpg",
    "round": "news/default_round.jpg",
    "record": "news/default_league.jpg",
    "general": "news/default_league.jpg",
}



def create_news(
    db: Session,
    *,
    title: str,
    excerpt: str,
    category: str = "general",
    image_path: str | None = None,
    related_url: str | None = None,
    published: bool = True,
) -> News:
    img = image_path or DEFAULT_NEWS_IMAGES.get(category, DEFAULT_NEWS_IMAGES["general"])

    item = News(
        title=title.strip(),
        excerpt=excerpt.strip(),
        category=category,
        image_path=img,
        related_url=related_url,
        published=published,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def delete_news(db: Session, news_id: int):
    item = db.query(News).filter(News.id == news_id).first()
    if not item:
        return
    db.delete(item)
    db.commit()

def get_news_by_id(db: Session, news_id: int):
    return db.query(News).filter(News.id == news_id).first()


# ======================================================================================
#                                   Tournament Teams
# ======================================================================================

def create_team_tournament(db, name, date, image_path=None):
    t = Tournament(
        name=name,
        date=date,
        mode="team",
        status="draft",
        image_path=image_path,
        course_id=1  # temporal (no se usa en team realmente)
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t

def create_team(db, tournament_id, side, name, logo_path=None):
    team = TournamentTeam(
        tournament_id=tournament_id,
        side=side,
        name=name,
        logo_path=logo_path
    )
    db.add(team)
    db.commit()
    db.refresh(team)
    return team

def add_player_to_team(db, team_id, player_id):
    tp = TournamentTeamPlayer(
        team_id=team_id,
        player_id=player_id
    )
    db.add(tp)
    db.commit()
    return tp

def create_stage(db, tournament_id, order_index, modality, course_id, name=None):
    stage = TournamentStage(
        tournament_id=tournament_id,
        order_index=order_index,
        modality=modality,
        course_id=course_id,
        name=name or f"Round {order_index}"
    )
    db.add(stage)
    db.commit()
    db.refresh(stage)
    return stage

def generate_matches_for_stage(db, stage: TournamentStage):
    db.refresh(stage)
    tournament = stage.tournament

    team_a = next(t for t in tournament.teams if t.side == "A")
    team_b = next(t for t in tournament.teams if t.side == "B")

    players_a = team_a.players
    players_b = team_b.players

    if len(players_a) != len(players_b):
        raise ValueError("Los dos equipos deben tener el mismo número de jugadores")

    num_players = len(players_a)

    if stage.modality == "individual":
        matches_count = num_players
        side_size = 1
    else:
        if num_players % 2 != 0:
            raise ValueError("En modalidades por parejas el número de jugadores debe ser par")
        matches_count = num_players // 2
        side_size = 2

    matches = []
    for i in range(matches_count):
        m = TournamentMatch(
            tournament_id=tournament.id,
            round=f"S{stage.order_index}",   # <- importante por compatibilidad con legacy
            position=i + 1,
            stage_id=stage.id,
            team_a_id=team_a.id,
            team_b_id=team_b.id,
            side_size=side_size,
            match_mode=stage.modality,
            status="draft",
        )
        db.add(m)
        matches.append(m)

    db.commit()

    for m in matches:
        db.refresh(m)

    return matches

def set_match_participants(
    db,
    match_id: int,
    side_a_player_ids: list[int],
    side_b_player_ids: list[int],
):
    match = (
        db.query(models.TournamentMatch)
        .filter(models.TournamentMatch.id == match_id)
        .first()
    )
    if not match:
        raise ValueError("Match no encontrado")

    expected_size = match.side_size or 1

    if len(side_a_player_ids) != expected_size:
        raise ValueError(f"El lado A debe tener {expected_size} jugador(es)")

    if len(side_b_player_ids) != expected_size:
        raise ValueError(f"El lado B debe tener {expected_size} jugador(es)")

    all_ids = side_a_player_ids + side_b_player_ids
    if len(all_ids) != len(set(all_ids)):
        raise ValueError("No se puede repetir un jugador dentro del mismo match")

    (
        db.query(models.TournamentMatchParticipant)
        .filter(models.TournamentMatchParticipant.match_id == match_id)
        .delete(synchronize_session=False)
    )

    for idx, player_id in enumerate(side_a_player_ids, start=1):
        db.add(models.TournamentMatchParticipant(
            match_id=match_id,
            player_id=player_id,
            side="A",
            slot=idx,
        ))

    for idx, player_id in enumerate(side_b_player_ids, start=1):
        db.add(models.TournamentMatchParticipant(
            match_id=match_id,
            player_id=player_id,
            side="B",
            slot=idx,
        ))

    match.status = "ready"

    db.commit()
    db.refresh(match)
    return match

def generate_stage_matches_with_participants(db, tournament_id: int, stage_id: int):
    stage = (
        db.query(models.TournamentStage)
        .filter(
            models.TournamentStage.id == stage_id,
            models.TournamentStage.tournament_id == tournament_id,
        )
        .first()
    )
    if not stage:
        raise ValueError("Stage no encontrado")

    tournament = (
        db.query(models.Tournament)
        .filter(models.Tournament.id == tournament_id)
        .first()
    )
    if not tournament:
        raise ValueError("Torneo no encontrado")

    team_a = (
        db.query(models.TournamentTeam)
        .filter(
            models.TournamentTeam.tournament_id == tournament_id,
            models.TournamentTeam.side == "A",
        )
        .first()
    )
    team_b = (
        db.query(models.TournamentTeam)
        .filter(
            models.TournamentTeam.tournament_id == tournament_id,
            models.TournamentTeam.side == "B",
        )
        .first()
    )

    if not team_a or not team_b:
        raise ValueError("El torneo debe tener equipo A y equipo B")

    team_a_players = (
        db.query(models.TournamentTeamPlayer)
        .filter(models.TournamentTeamPlayer.team_id == team_a.id)
        .order_by(models.TournamentTeamPlayer.id.asc())
        .all()
    )
    team_b_players = (
        db.query(models.TournamentTeamPlayer)
        .filter(models.TournamentTeamPlayer.team_id == team_b.id)
        .order_by(models.TournamentTeamPlayer.id.asc())
        .all()
    )

    a_ids = [tp.player_id for tp in team_a_players]
    b_ids = [tp.player_id for tp in team_b_players]

    if not a_ids or not b_ids:
        raise ValueError("Ambos equipos deben tener jugadores")

    if len(a_ids) != len(b_ids):
        raise ValueError("Ambos equipos deben tener el mismo número de jugadores")

    # No regenerar si ya existen matches en esta ronda
    existing = (
        db.query(models.TournamentMatch)
        .filter(models.TournamentMatch.stage_id == stage_id)
        .count()
    )
    if existing > 0:
        raise ValueError("Esta ronda ya tiene partidos generados")

    modality = (stage.modality or "").lower().strip()

    if modality == "individual":
        side_size = 1
        matches_count = len(a_ids)
    else:
        if len(a_ids) % 2 != 0:
            raise ValueError("En modalidades por parejas el número de jugadores debe ser par")
        side_size = 2
        matches_count = len(a_ids) // 2

    created_matches = []

    for i in range(matches_count):
        match = models.TournamentMatch(
            tournament_id=tournament_id,
            round=f"S{stage.order_index}",   # compatibilidad legacy
            position=i + 1,
            stage_id=stage.id,
            team_a_id=team_a.id,
            team_b_id=team_b.id,
            side_size=side_size,
            match_mode=modality,
            status="draft",
        )
        db.add(match)
        db.flush()  # para tener match.id sin commit

        if side_size == 1:
            side_a_ids = [a_ids[i]]
            side_b_ids = [b_ids[i]]
        else:
            start = i * 2
            side_a_ids = [a_ids[start], a_ids[start + 1]]
            side_b_ids = [b_ids[start], b_ids[start + 1]]

        for slot, player_id in enumerate(side_a_ids, start=1):
            db.add(models.TournamentMatchParticipant(
                match_id=match.id,
                player_id=player_id,
                side="A",
                slot=slot,
            ))

        for slot, player_id in enumerate(side_b_ids, start=1):
            db.add(models.TournamentMatchParticipant(
                match_id=match.id,
                player_id=player_id,
                side="B",
                slot=slot,
            ))

        match.status = "ready"
        created_matches.append(match)

    stage.status = "ready"
    db.commit()

    for m in created_matches:
        db.refresh(m)

    return created_matches
