from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import UploadFile, File
from pathlib import Path
from uuid import uuid4
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy import extract, func
from sqlalchemy.exc import OperationalError
from datetime import datetime
from datetime import date
from . import models
from typing import List
from .db import Base, engine, get_db
from . import crud, schemas
from app.models import Player, Course, Round, RoundPlayer, HoleScore, Hole
import os
from fastapi import HTTPException
from fastapi.responses import PlainTextResponse


Base.metadata.create_all(bind=engine)

def ensure_league_logo_column():
    # Añade la columna logo_url si no existe (SQLite)
    with engine.begin() as conn:
        try:
            conn.execute(text("ALTER TABLE leagues ADD COLUMN logo_url VARCHAR"))
        except OperationalError as e:
            # Si ya existe, ignoramos el error
            if "duplicate column name: logo_url" in str(e):
                pass
            else:
                raise

ensure_league_logo_column()


app = FastAPI(title="Golf Stats")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
UPLOAD_PLAYERS_DIR = Path("app/static/uploads/players")
UPLOAD_PLAYERS_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_COURSES_DIR = Path("app/static/uploads/courses")
UPLOAD_COURSES_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_LEAGUES_DIR = Path("app/static/uploads/leagues")
UPLOAD_LEAGUES_DIR.mkdir(parents=True, exist_ok=True)

ADMIN_KEY = os.getenv("ADMIN_KEY", "")  # en local puedes dejarlo vacío si quieres

def require_admin(request: Request):
    # 1) Si no hay ADMIN_KEY configurada, NO protegemos (modo dev)
    if not ADMIN_KEY:
        return

    # 2) Comprobamos cookie
    cookie_key = request.cookies.get("admin_key")
    if cookie_key == ADMIN_KEY:
        return

    # 3) Si no coincide -> fuera
    raise HTTPException(status_code=401, detail="Admin auth required")



# ================================================================================
# =============================== PASSWORD ADMIN =================================
# ================================================================================

@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_form(request: Request):
    return templates.TemplateResponse("admin_login.html", {"request": request})


@app.post("/admin/login")
def admin_login_submit(request: Request, key: str = Form(...)):
    if not ADMIN_KEY:
        return RedirectResponse("/admin", status_code=303)

    if key != ADMIN_KEY:
        return templates.TemplateResponse(
            "admin_login.html",
            {"request": request, "error": "Clave incorrecta"},
            status_code=401,
        )

    resp = RedirectResponse("/admin", status_code=303)
    resp.set_cookie(
        "admin_key",
        key,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 12,  # 12 horas
    )

    return resp


@app.get("/admin/logout")
def admin_logout():
    resp = RedirectResponse("/public", status_code=303)
    resp.delete_cookie("admin_key")
    return resp

@app.middleware("http")
async def admin_guard(request: Request, call_next):
    path = request.url.path

    # Solo proteger /admin...
    if path.startswith("/admin"):
        # permitimos login/logout y static
        if path in ("/admin/login", "/admin/logout"):
            return await call_next(request)

        # si no hay ADMIN_KEY (dev), no protegemos
        if not ADMIN_KEY:
            return await call_next(request)

        # si cookie OK, seguimos
        if request.cookies.get("admin_key") == ADMIN_KEY:
            return await call_next(request)

        # si no, redirigimos a login
        return RedirectResponse("/admin/login", status_code=303)

    return await call_next(request)


# ---------------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/public")


#--------------------------------------------------------------------------------
#------------------------------ ADMIN: PLAYERS ----------------------------------
#--------------------------------------------------------------------------------


@app.get("/admin/players", response_class=HTMLResponse, name="admin_players")
def players_list(request: Request, db: Session = Depends(get_db)):
    players = crud.get_players(db)
    return templates.TemplateResponse(
        "players_list.html",
        {"request": request, "players": players}
    )


# ---- CREAR JUGADOR ----
@app.get("/admin/players/new", response_class=HTMLResponse)
def player_new_form(request: Request):
    return templates.TemplateResponse(
        "player_form.html",
        {"request": request, "title": "Nuevo jugador", "player": None}
    )


@app.post("/admin/players/new")
async def player_new(
    name: str = Form(...),
    nickname: str = Form(None),
    license_number: str | None = Form(None),
    hcp_exact: float = Form(0.0),
    active: bool = Form(False),
    photo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    # 📸 Guardar la foto si se ha subido
    photo_url: str | None = None

    if photo and photo.filename:
        filename = f"{uuid4().hex}_{photo.filename}"
        dest_path = UPLOAD_PLAYERS_DIR / filename
        with open(dest_path, "wb") as f:
            f.write(await photo.read())
        # 🔹 Lo que se guarda en BBDD es relativo a /static
        #     -> static/uploads/players/filename
        #     -> photo_url = "uploads/players/filename"
        photo_url = f"uploads/players/{filename}"

    data = schemas.PlayerCreate(
        name=name,
        nickname=nickname,
        license_number=license_number,
        photo_url=photo_url,
        hcp_exact=hcp_exact,
        active=active,
    )
    crud.create_player(db, data)
    return RedirectResponse("/admin/players", status_code=303)


# ---- EDITAR JUGADOR ----
@app.get("/admin/players/{player_id}/edit", response_class=HTMLResponse)
def player_edit_form(request: Request, player_id: int, db: Session = Depends(get_db)):
    player = crud.get_player(db, player_id)
    if not player:
        return RedirectResponse("/admin/players", status_code=303)

    return templates.TemplateResponse(
        "player_form.html",
        {"request": request, "title": "Editar jugador", "player": player}
    )


@app.post("/admin/players/{player_id}/edit")
async def player_edit(
    player_id: int,
    name: str = Form(...),
    nickname: str = Form(None),
    license_number: str | None = Form(None),
    hcp_exact: float = Form(0.0),
    active: bool = Form(False),
    photo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    existing = crud.get_player(db, player_id)
    if not existing:
        return RedirectResponse("/admin/players", status_code=303)

    photo_url = existing.photo_url

    # Si suben una foto nueva, la guardamos y borramos la anterior
    if photo and photo.filename:
        # 1) borrar foto previa si había
        if existing.photo_url:
            old_filename = Path(existing.photo_url).name
            old_path = UPLOAD_PLAYERS_DIR / old_filename
            if old_path.exists():
                try:
                    old_path.unlink()
                except OSError:
                    pass  # si falla, no queremos romper la edición

        # 2) guardar nueva foto
        filename = f"{uuid4().hex}_{photo.filename}"
        dest_path = UPLOAD_PLAYERS_DIR / filename
        with open(dest_path, "wb") as f:
            f.write(await photo.read())
        photo_url = f"uploads/players/{filename}"

    data = schemas.PlayerUpdate(
        name=name,
        nickname=nickname,
        license_number=license_number,
        photo_url=photo_url,
        hcp_exact=hcp_exact,
        active=active,
    )
    crud.update_player(db, player_id, data)
    return RedirectResponse("/admin/players", status_code=303)


# ---- ELIMINAR JUGADOR ----
@app.get("/admin/players/{player_id}/delete")
def player_delete(player_id: int, db: Session = Depends(get_db)):
    # 1) Recuperar jugador para saber qué foto tiene
    player = crud.get_player(db, player_id)

    # 2) Borrar foto del disco si existe
    if player and player.photo_url:
        filename = Path(player.photo_url).name
        photo_path = UPLOAD_PLAYERS_DIR / filename
        if photo_path.exists():
            try:
                photo_path.unlink()
            except OSError:
                pass  # si falla, no queremos romper el borrado

    # 3) Borrar registro en la BBDD
    crud.delete_player(db, player_id)

    return RedirectResponse("/admin/players", status_code=303)


# =======================================================================================
# ========================== ADMIN: ACHIEVEMENTS (CATÁLOGO) =============================
# =======================================================================================

@app.get("/admin/achievements", response_class=HTMLResponse, name="admin_achievements")
def admin_achievements(request: Request, db: Session = Depends(get_db)):
    achievements = crud.get_achievements(db)
    return templates.TemplateResponse(
        "admin_achievements.html",
        {"request": request, "achievements": achievements}
    )


@app.post("/admin/achievements/new", response_class=HTMLResponse)
def admin_create_achievement(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    icon: str = Form(""),
    db: Session = Depends(get_db)
):
    crud.create_achievement(db, name=name, description=description, icon=icon)
    return RedirectResponse("/admin/achievements", status_code=303)

@app.post("/admin/achievements/{achievement_id}/edit", response_class=HTMLResponse)
def admin_edit_achievement(
    achievement_id: int,
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    icon: str = Form(""),
    db: Session = Depends(get_db)
):
    crud.update_achievement(db, achievement_id, name=name, description=description, icon=icon)
    return RedirectResponse("/admin/achievements", status_code=303)

@app.post("/admin/achievements/{achievement_id}/delete")
def admin_delete_achievement(achievement_id: int, db: Session = Depends(get_db)):
    crud.delete_achievement(db, achievement_id)
    return RedirectResponse("/admin/achievements", status_code=303)

# =======================================================================================
# =========================== ADMIN: ASIGNACIÓN DE LOGROS ===============================
# =======================================================================================

@app.get("/admin/players/{player_id}/achievements", response_class=HTMLResponse)
def admin_player_achievements(player_id: int, request: Request, db: Session = Depends(get_db)):
    player = crud.get_player(db, player_id)
    if not player:
        return HTMLResponse("Jugador no encontrado", status_code=404)

    all_achievements = crud.get_achievements(db)
    owned = crud.get_player_achievements(db, player_id)
    owned_ids = {a.achievement_id for a in owned}

    return templates.TemplateResponse(
        "admin_player_achievements.html",
        {
            "request": request,
            "player": player,
            "all_achievements": all_achievements,
            "owned_ids": owned_ids,
        }
    )


@app.post("/admin/players/{player_id}/achievements/add")
def admin_assign_achievement_to_player(
    player_id: int,
    achievement_id: int = Form(...),
    db: Session = Depends(get_db)
):
    crud.assign_achievement_to_player(db, player_id, achievement_id)
    return RedirectResponse(f"/admin/players/{player_id}/achievements", status_code=303)


@app.post("/admin/players/{player_id}/achievements/remove")
def admin_remove_achievement_from_player(
    player_id: int,
    achievement_id: int = Form(...),
    db: Session = Depends(get_db)
):
    crud.remove_achievement_from_player(db, player_id, achievement_id)
    return RedirectResponse(f"/admin/players/{player_id}/achievements", status_code=303)


# ---------------------------------------------------------------------------
# -------------------------- ADMIN: COURSES ---------------------------------
# ---------------------------------------------------------------------------



@app.get("/admin/courses", response_class=HTMLResponse, name="admin_courses")
def courses_list(
    request: Request,
    db: Session = Depends(get_db),
    city: str | None = None
):
    # Lista de ciudades distintas para el filtro
    cities_q = (
        db.query(models.Course.city)
        .filter(models.Course.city.isnot(None))
        .distinct()
        .order_by(models.Course.city)
        .all()
    )
    cities = [c[0] for c in cities_q]

    # Query base de campos
    q = db.query(models.Course)
    if city and city.strip() != "":
        q = q.filter(models.Course.city == city)

    courses = q.order_by(models.Course.name).all()

    return templates.TemplateResponse(
        "courses_list.html",
        {
            "request": request,
            "courses": courses,
            "cities": cities,
            "selected_city": city,
        }
    )


@app.get("/admin/courses/new", response_class=HTMLResponse)
def course_new_form(request: Request):
    return templates.TemplateResponse(
        "course_form.html",
        {"request": request, "title": "Nuevo campo", "course": None}
    )

@app.post("/admin/courses/new")
async def course_new(
    name: str = Form(...),
    city: str = Form(None),
    par_total: int = Form(72),
    slope_yellow: int = Form(113),
    rating_yellow: float = Form(72.0),
    meters_total: int | None = Form(None),
    logo: UploadFile | None = File(None),
    db: Session = Depends(get_db)
):
    # Guardar logo si se sube archivo
    logo_url = None
    if logo and logo.filename:
        filename = f"{uuid4().hex}_{logo.filename}"
        dest_path = UPLOAD_COURSES_DIR / filename
        with open(dest_path, "wb") as f:
            f.write(await logo.read())
        logo_url = f"uploads/courses/{filename}"

    data = schemas.CourseCreate(
        name=name,
        city=city,
        par_total=par_total,
        slope_yellow=slope_yellow,
        rating_yellow=rating_yellow,
        meters_total=meters_total,
        logo_url=logo_url
    )
    crud.create_course(db, data)
    return RedirectResponse("/admin/courses", status_code=303)



@app.get("/admin/courses/{course_id}/edit", response_class=HTMLResponse)
def course_edit_form(course_id: int, request: Request, db: Session = Depends(get_db)):
    course = crud.get_course(db, course_id)
    return templates.TemplateResponse(
        "course_form.html",
        {"request": request, "title": "Editar campo", "course": course}
    )

@app.post("/admin/courses/{course_id}/edit")
async def course_edit(
    course_id: int,
    name: str = Form(...),
    city: str = Form(None),
    par_total: int = Form(72),
    slope_yellow: int = Form(113),
    rating_yellow: float = Form(72.0),
    meters_total: int | None = Form(None),
    logo: UploadFile | None = File(None),
    db: Session = Depends(get_db)
):
    existing = crud.get_course(db, course_id)
    if not existing:
        return RedirectResponse("/admin/courses", status_code=303)

    logo_url = existing.logo_url

    # Si se sube un nuevo logo, se reemplaza
    if logo and logo.filename:
        filename = f"{uuid4().hex}_{logo.filename}"
        dest_path = UPLOAD_COURSES_DIR / filename
        with open(dest_path, "wb") as f:
            f.write(await logo.read())
        logo_url = f"uploads/courses/{filename}"

    data = schemas.CourseUpdate(
        name=name,
        city=city,
        par_total=par_total,
        slope_yellow=slope_yellow,
        rating_yellow=rating_yellow,
        meters_total=meters_total,
        logo_url=logo_url
    )
    crud.update_course(db, course_id, data)
    return RedirectResponse("/admin/courses", status_code=303)



@app.get("/admin/courses/{course_id}/delete")
def course_delete(course_id: int, db: Session = Depends(get_db)):
    crud.delete_course(db, course_id)
    return RedirectResponse("/admin/courses", status_code=303)




# ======================================================================
# -------------------------- ADMIN: HOLES ------------------------------
#=======================================================================


@app.get("/admin/courses/{course_id}/holes", response_class=HTMLResponse)
def holes_form(course_id: int, request: Request, db: Session = Depends(get_db)):
    course = crud.get_course(db, course_id)
    holes = crud.get_holes_for_course(db, course_id)
    holes_map = {h.number: h for h in holes}

    return templates.TemplateResponse(
        "holes_form.html",
        {"request": request, "course": course, "holes_map": holes_map}
    )


@app.post("/admin/courses/{course_id}/holes")
async def holes_save(course_id: int, request: Request, db: Session = Depends(get_db)):
    form = await request.form()

    holes_data = []
    for i in range(1, 19):
        par = int(form.get(f"par_{i}"))
        si = int(form.get(f"si_{i}"))
        m = form.get(f"m_{i}")
        meters = int(m) if m not in (None, "", " ") else None

        holes_data.append(
            schemas.HoleCreate(
                number=i,
                par=par,
                stroke_index=si,
                meters_yellow=meters
            )
        )

    crud.upsert_holes_for_course(db, course_id, holes_data)
    return RedirectResponse(f"/admin/courses/{course_id}/holes", status_code=303)



# ======================================================================
# ------------------------ ADMIN: ROUND LIST ---------------------------
#=======================================================================


@app.get("/admin/rounds", response_class=HTMLResponse, name="admin_rounds")
def admin_rounds_list(request: Request, db: Session = Depends(get_db)):
    rounds = crud.get_rounds(db)
    return templates.TemplateResponse(
        "admin_rounds.html",
        {"request": request, "rounds": rounds}
    )

@app.post("/admin/rounds/{round_id}/delete")
def admin_round_delete(round_id: int, db: Session = Depends(get_db)):
    crud.delete_round(db, round_id)
    return RedirectResponse("/admin/rounds", status_code=303)


# =================================================================================
# ============================== ADMIN: HOME / PANEL ==============================
# =================================================================================


@app.get("/admin", response_class=HTMLResponse, name="admin_home")
def admin_home(request: Request, db: Session = Depends(get_db)):
    players = crud.get_players(db)  # asumo que ya tienes este crud
    return templates.TemplateResponse(
        "admin_home.html",
        {
            "request": request,
            "players": players,
        }
    )



# ------------------------------------------------------------------------------------------
# -------------------------------------- ADMIN: ROUNDS -------------------------------------
# ------------------------------------------------------------------------------------------

@app.get("/admin/rounds/new", response_class=HTMLResponse, name="admin_rounds_new")
def round_new_form(request: Request, db: Session = Depends(get_db)):
    courses = crud.get_courses(db)
    players = crud.get_players(db)
    leagues = crud.get_leagues(db, only_open=True)  # ✅ ligas abiertas

    return templates.TemplateResponse(
        "round_new.html",
        {
            "request": request,
            "courses": courses,
            "players": players,
            "leagues": leagues,  # ✅ pasamos ligas al template
        }
    )


@app.post("/admin/rounds/new")
async def round_new_create(request: Request, db: Session = Depends(get_db)):
    form = await request.form()

    course_id = int(form.get("course_id"))
    date_str = form.get("date")
    tee = form.get("tee") or "yellow"

    # Campo unificado: match_type
    match_type = form.get("match_type") or ""

    if match_type == "":
        # Partido amistoso
        round_type = "amistosa"
        league_id = None
    else:
        # Partido de liga: el valor del select es el id de la liga
        round_type = "liga"
        league_id = int(match_type)

    # 🔻 NUEVO: recogemos la lista dinámica de jugadores
    #
    # En el formulario habrá varios:
    #   <select name="player_ids">...</select>
    #   <select name="player_ids">...</select>
    #   ...
    # y aquí los recibimos todos como lista.
    raw_player_ids = form.getlist("player_ids")

    player_ids: list[int] = []
    for v in raw_player_ids:
        if v and v.strip() != "":
            pid = int(v)
            if pid not in player_ids:  # evitamos duplicados
                player_ids.append(pid)

    # Asegurarnos de que hay al menos 1 jugador
    if len(player_ids) == 0:
        return RedirectResponse("/admin/rounds/new", status_code=303)

    # Fecha
    round_date = datetime.strptime(date_str, "%Y-%m-%d").date()

    # create_round ya acepta league_id y lista de player_ids
    r = crud.create_round(
        db,
        round_date,
        course_id,
        tee,
        round_type,
        player_ids,
        league_id,
    )

    return RedirectResponse(f"/admin/rounds/{r.id}/summary", status_code=303)


@app.get("/admin/rounds/{round_id}/summary", response_class=HTMLResponse)
def round_summary(round_id: int, request: Request, db: Session = Depends(get_db)):
    r = crud.get_round(db, round_id)
    course = crud.get_course(db, r.course_id)
    rps = crud.get_round_players(db, round_id)

    # Mapa rápido de par por hoyo para no buscar mil veces
    par_map = {h.number: h.par for h in course.holes}

    results = []

    for rp in rps:
        scores = rp.hole_scores  # lista HoleScore

        # --- FIR / GIR ---
        fir_total = sum(1 for s in scores if s.fir is True)
        fir_possible = sum(1 for s in scores if s.fir is not None)
        fir_pct = (fir_total / fir_possible * 100) if fir_possible > 0 else None

        gir_total = sum(1 for s in scores if s.gir is True)
        gir_possible = sum(1 for s in scores if s.gir is not None)
        gir_pct = (gir_total / gir_possible * 100) if gir_possible > 0 else None

        # --- Putts por hoyo ---
        putts_holes = [s.putts for s in scores if s.putts is not None]
        putts_per_hole = (sum(putts_holes) / len(putts_holes)) if putts_holes else None

        # --- Nivel de juego (diferencial WHS simplificado) ---
        level_hcp = None
        if rp.gross_total is not None:
            level_hcp = ((rp.gross_total - course.rating_yellow) * 113) / course.slope_yellow

        # --- Resultados por gross vs par ---
        hio = sum(1 for s in scores if s.gross_strokes == 1)

        albatros = sum(
            1 for s in scores
            if s.gross_strokes != 1 and (s.gross_strokes - par_map[s.hole_number]) <= -3
        )
        eagles = sum(
            1 for s in scores
            if s.gross_strokes != 1 and (s.gross_strokes - par_map[s.hole_number]) == -2
        )
        birdies = sum(
            1 for s in scores
            if s.gross_strokes != 1 and (s.gross_strokes - par_map[s.hole_number]) == -1
        )
        pars = sum(
            1 for s in scores
            if s.gross_strokes != 1 and (s.gross_strokes - par_map[s.hole_number]) == 0
        )
        bogeys = sum(
            1 for s in scores
            if s.gross_strokes != 1 and (s.gross_strokes - par_map[s.hole_number]) == 1
        )
        dbl = sum(
            1 for s in scores
            if s.gross_strokes != 1 and (s.gross_strokes - par_map[s.hole_number]) == 2
        )
        overdbl = sum(
            1 for s in scores
            if s.gross_strokes != 1 and (s.gross_strokes - par_map[s.hole_number]) >= 3
        )

        results.append({
            "rp_id": rp.id,
            "player": rp.player,
            "course_handicap": rp.course_handicap,

            "gross_total": rp.gross_total,
            "net_total": rp.net_total,
            "points": rp.stableford_hcp_total,
            "scratch_points": rp.stableford_scratch_total,

            "putts": rp.putts_total,
            "putts_per_hole": putts_per_hole,
            "level_hcp": level_hcp,

            "fir": fir_total,
            "fir_possible": fir_possible,
            "fir_pct": fir_pct,

            "gir": gir_total,
            "gir_possible": gir_possible,
            "gir_pct": gir_pct,

            "hio": hio,
            "albatros": albatros,
            "eagles": eagles,
            "birdies": birdies,
            "pars": pars,
            "bogeys": bogeys,
            "dbl": dbl,
            "overdbl": overdbl,
        })

    return templates.TemplateResponse(
        "round_summary.html",
        {
            "request": request,
            "round": r,
            "course": course,
            "results": results
        }
    )


@app.get("/admin/rounds/{round_id}/player/{rp_id}/card", response_class=HTMLResponse)
def round_card_player_form(round_id: int, rp_id: int, request: Request, db: Session = Depends(get_db)):
    r = crud.get_round(db, round_id)
    course = crud.get_course(db, r.course_id)
    holes = crud.get_holes_for_course(db, r.course_id)
    rp = crud.get_round_player(db, rp_id)
    player = crud.get_player(db, rp.player_id)

    existing_scores = {hs.hole_number: hs for hs in rp.hole_scores}

    return templates.TemplateResponse(
        "round_card_player.html",
        {
            "request": request,
            "round": r,
            "course": course,
            "holes": holes,
            "rp": rp,
            "player": player,
            "existing": existing_scores
        }
    )


@app.post("/admin/rounds/{round_id}/player/{rp_id}/card")
async def round_card_player_save(round_id: int, rp_id: int, request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    r = crud.get_round(db, round_id)
    holes = crud.get_holes_for_course(db, r.course_id)
    rp = crud.get_round_player(db, rp_id)

    # 1) Actualizar HCP de juego si viene en el formulario
    ch_raw = form.get("course_handicap")
    if ch_raw is not None and ch_raw != "":
        try:
            rp.course_handicap = int(ch_raw)
            db.commit()
            db.refresh(rp)
        except ValueError:
            # Si algo raro ocurre, simplemente ignoramos el cambio de HCP
            pass

    # 2) Leer tarjeta hoyo a hoyo
    gross_by_hole: dict[int, int] = {}
    putts_by_hole: dict[int, int | None] = {}
    fir_by_hole: dict[int, bool] = {}

    for h in holes:
        g_val = form.get(f"g_{h.number}")
        p_val = form.get(f"p_{h.number}")
        fir_val = form.get(f"fir_{h.number}")

        # golpes brutos
        gross_by_hole[h.number] = int(g_val) if g_val not in (None, "", " ") else 0

        # putts
        putts_by_hole[h.number] = int(p_val) if p_val not in (None, "", " ") else None

        # FIR:
        # - en par 3 no aplica -> None (no cuenta ni como acierto ni como posible)
        # - en par 4/5 sí aplican -> True/False según checkbox
        if h.par <= 3:
            fir_by_hole[h.number] = None
        else:
            fir_by_hole[h.number] = (fir_val is not None)


    # 3) Guardar la tarjeta y recalcular totales (gross/neto/puntos/putts_total, etc.)
    crud.save_card_for_round_player(db, rp, holes, gross_by_hole, putts_by_hole, fir_by_hole)

    # 4) Si todos tienen tarjeta cerrada -> cerrar vuelta + ganador
    rps = crud.get_round_players(db, round_id)
    if all(x.gross_total is not None for x in rps):
        crud.close_round_and_set_winner(db, round_id)

    return RedirectResponse(f"/admin/rounds/{round_id}/summary", status_code=303)


# ===========================================================================================
# ----------------------------------- ADMIN: LEAGUES ----------------------------------------
# ===========================================================================================


@app.get("/admin/leagues", response_class=HTMLResponse, name="admin_leagues")
def admin_leagues(request: Request, db: Session = Depends(get_db)):
    leagues = crud.get_leagues(db)
    return templates.TemplateResponse("admin_leagues.html", {"request": request, "leagues": leagues})


@app.post("/admin/leagues/new")
async def admin_leagues_new(
    name: str = Form(...),
    logo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    logo_url = None

    # si el usuario ha subido archivo
    if logo and logo.filename:
        filename = f"{uuid4().hex}_{logo.filename}"
        dest_path = UPLOAD_LEAGUES_DIR / filename

        with open(dest_path, "wb") as f:
            f.write(await logo.read())

        # lo guardamos en BBDD como ruta relativa a /static
        logo_url = f"uploads/leagues/{filename}"

    crud.create_league(db, name=name, logo_url=logo_url)
    return RedirectResponse("/admin/leagues", status_code=303)



@app.post("/admin/leagues/{league_id}/close")
def admin_leagues_close(league_id: int, db: Session = Depends(get_db)):
    crud.close_league(db, league_id)
    return RedirectResponse("/admin/leagues", status_code=303)



# =============================================================================================================
# =========================================== PUBLIC PAYER PROFILE ============================================
# =============================================================================================================

@app.get("/players/{player_id}", response_class=HTMLResponse)
def player_profile(
    player_id: int,
    request: Request,
    year: int | None = None,   # 👈 NUEVO
    db: Session = Depends(get_db)
):
    player = crud.get_player(db, player_id)
    if not player:
        return HTMLResponse("Jugador no encontrado", status_code=404)

    # Todas sus participaciones en vueltas
    rps = (
        db.query(models.RoundPlayer)
        .filter(models.RoundPlayer.player_id == player_id)
        .all()
    )

    # Años disponibles (para el selector)
    years_available = sorted(
        {rp.round.date.year for rp in rps if rp.round and rp.round.date},
        reverse=True
    )

    # Filtrado por año (para KPIs / stats / gráficos)
    filtered_rps = rps
    if year:
        filtered_rps = [
            rp for rp in rps
            if rp.round and rp.round.date and rp.round.date.year == year
        ]

    # -------------------------
    # KPI básicos por vuelta
    # -------------------------
    valid_rps = [rp for rp in filtered_rps if rp.gross_total is not None]

    rounds_played = len(valid_rps)
    wins = len([rp for rp in valid_rps if rp.result == "win"])
    ties = len([rp for rp in valid_rps if rp.result == "tie"])

    gross_list = [rp.gross_total for rp in valid_rps if rp.gross_total is not None]
    net_list = [rp.net_total for rp in valid_rps if rp.net_total is not None]
    pts_hcp_list = [rp.stableford_hcp_total for rp in valid_rps if rp.stableford_hcp_total is not None]
    pts_scratch_list = [rp.stableford_scratch_total for rp in valid_rps if rp.stableford_scratch_total is not None]
    putts_list = [rp.putts_total for rp in valid_rps if rp.putts_total is not None]

    avg_gross = (sum(gross_list) / len(gross_list)) if gross_list else None
    avg_net = (sum(net_list) / len(net_list)) if net_list else None
    avg_pts_hcp = (sum(pts_hcp_list) / len(pts_hcp_list)) if pts_hcp_list else None
    avg_pts_scratch = (sum(pts_scratch_list) / len(pts_scratch_list)) if pts_scratch_list else None
    avg_putts = (sum(putts_list) / len(putts_list)) if putts_list else None

    # Mejor vuelta bruta
    best_round_gross = min(gross_list) if gross_list else None

    # -------------------------
    # FIR / GIR globales y Putts/Hoyo global
    # -------------------------
    hole_scores = []
    for rp in filtered_rps:
        hole_scores.extend(rp.hole_scores)

    fir_total = sum(1 for s in hole_scores if s.fir is True)
    fir_possible = sum(1 for s in hole_scores if s.fir is not None)
    fir_pct = (fir_total / fir_possible * 100) if fir_possible else None

    gir_total = sum(1 for s in hole_scores if s.gir is True)
    gir_possible = sum(1 for s in hole_scores if s.gir is not None)
    gir_pct = (gir_total / gir_possible * 100) if gir_possible else None

    putts_holes = [s.putts for s in hole_scores if s.putts is not None]
    putts_per_hole = (sum(putts_holes) / len(putts_holes)) if putts_holes else None

    # HCP de juego medio (course_handicap de cada vuelta jugada)
    play_hcps = [rp.course_handicap for rp in filtered_rps if rp.course_handicap is not None]
    avg_play_hcp = (sum(play_hcps) / len(play_hcps)) if play_hcps else None


    # --------------------------------------------------------------------
    # DISTRIBUCIÓN GLOBAL DE RESULTADOS POR HOYO (stats_results)
    # --------------------------------------------------------------------
    stats = {
        "hio": 0,
        "albatros": 0,
        "eagles": 0,
        "birdies": 0,
        "pars": 0,
        "bogeys": 0,
        "dbl": 0,
        "overdbl": 0,
        "total_holes": 0,
    }

    # Para medias por tipo de hoyo
    par3_sum = par3_count = 0
    par4_sum = par4_count = 0
    par5_sum = par5_count = 0

    for rp in filtered_rps:
        course = rp.round.course
        if not course:
            continue

        par_map = {h.number: h.par for h in course.holes}

        for s in rp.hole_scores:
            if s.gross_strokes is None:
                continue

            par = par_map.get(s.hole_number)
            if par is None:
                continue

            stats["total_holes"] += 1

              # medias por Par
            if par == 3:
                par3_sum += s.gross_strokes
                par3_count += 1
            elif par == 4:
                par4_sum += s.gross_strokes
                par4_count += 1
            elif par == 5:
                par5_sum += s.gross_strokes
                par5_count += 1


            # HIO
            if s.gross_strokes == 1:
                stats["hio"] += 1
                continue

            diff = s.gross_strokes - par

            if diff <= -3:
                stats["albatros"] += 1
            elif diff == -2:
                stats["eagles"] += 1
            elif diff == -1:
                stats["birdies"] += 1
            elif diff == 0:
                stats["pars"] += 1
            elif diff == 1:
                stats["bogeys"] += 1
            elif diff == 2:
                stats["dbl"] += 1
            elif diff >= 3:
                stats["overdbl"] += 1

    total_holes = stats["total_holes"] or 1  # evita división por 0

    stats_results = {
        "hio": stats["hio"],
        "albatros": stats["albatros"],
        "eagles": stats["eagles"],
        "birdies": stats["birdies"],
        "pars": stats["pars"],
        "bogeys": stats["bogeys"],
        "dbl": stats["dbl"],
        "overdbl": stats["overdbl"],
        "total_holes": stats["total_holes"],
        # porcentajes para el donut
        "birdie_pct": round(stats["birdies"] / total_holes * 100, 1),
        "par_pct": round(stats["pars"] / total_holes * 100, 1),
        "bogey_pct": round(stats["bogeys"] / total_holes * 100, 1),
        "double_pct": round(stats["dbl"] / total_holes * 100, 1),
        "worse_pct": round(stats["overdbl"] / total_holes * 100, 1),
    }

    total_birdies = stats["birdies"]
    total_eagles = stats_results["eagles"]

        # Medias globales por tipo de hoyo
    par_stats = {
        "avg_par3": (par3_sum / par3_count) if par3_count else None,
        "avg_par4": (par4_sum / par4_count) if par4_count else None,
        "avg_par5": (par5_sum / par5_count) if par5_count else None,
    }


    # -------------------------
    # Historial de vueltas (filtrado por año)
    # -------------------------
    history = sorted(
        [
            {
                "date": rp.round.date,
                "course": rp.round.course.name if rp.round.course else "",
                "gross": rp.gross_total,
                "net": rp.net_total,
                "points": rp.stableford_hcp_total,
                "scratch_points": rp.stableford_scratch_total,
                "putts": rp.putts_total,
                "result": rp.result,
                "round_id": rp.round_id,
            }
            for rp in filtered_rps
            if rp.round and rp.round.date and rp.gross_total is not None
        ],
        key=lambda x: x["date"],
        reverse=True,   # recientes primero
    )

    # 10 últimas para el gráfico (cronológico para dibujar)
    last10_gross = [
        {"date": h["date"], "gross": h["gross"], "course": h["course"]}
        for h in history[:10]
    ]
    last10_gross = list(reversed(last10_gross))  # antiguo -> reciente

    last10_hcp = sorted(
        [
            {"date": rp.round.date, "hcp": float(rp.course_handicap)}
            for rp in filtered_rps
            if rp.round and rp.round.date and rp.course_handicap is not None
        ],
        key=lambda x: x["date"]
    )[-10:]



    # -------------------------
    # LOGROS DEL JUGADOR
    # -------------------------
    all_achievements = crud.get_achievements(db)
    player_achievements = crud.get_player_achievements(db, player_id)
    owned_ids = {pa.achievement_id for pa in player_achievements}

    achievements_data = []
    for a in all_achievements:
        achievements_data.append({
            "id": a.id,
            "name": a.name,
            "description": a.description,
            "icon": a.icon,
            "unlocked": a.id in owned_ids,   # 👈 TRUE si el jugador lo tiene
        })



    return templates.TemplateResponse(
        "player_profile.html",
        {
            "request": request,
            "player": player,
            "rounds_played": rounds_played,
            "wins": wins,
            "ties": ties,
            "avg_gross": avg_gross,
            "avg_net": avg_net,
            "avg_pts_hcp": avg_pts_hcp,
            "avg_pts_scratch": avg_pts_scratch,
            "avg_putts": avg_putts,
            "fir_pct": fir_pct,
            "gir_pct": gir_pct,
            "putts_per_hole": putts_per_hole,
            "best_round_gross": best_round_gross,
            "total_birdies": total_birdies,
            "stats_results": stats_results,
            "history": history,
            "avg_play_hcp": avg_play_hcp,        
            "total_eagles": total_eagles,        
            "par_stats": par_stats,
            "achievements": achievements_data,
            "last10_hcp": last10_hcp,
            "last10_gross": last10_gross,
            "year": year,
            "years_available": years_available,

        },
    )


def build_rankings_data(db: Session):
    players = crud.get_players(db)

    ranking_rows = []

    for p in players:
        rps = (
            db.query(models.RoundPlayer)
            .filter(models.RoundPlayer.player_id == p.id)
            .all()
        )

        rounds_played = len([rp for rp in rps if rp.gross_total is not None])
        wins = len([rp for rp in rps if rp.result == "win"])
        ties = len([rp for rp in rps if rp.result == "tie"])

        pts_list = [rp.stableford_hcp_total for rp in rps if rp.stableford_hcp_total is not None]
        scr_list = [rp.stableford_scratch_total for rp in rps if rp.stableford_scratch_total is not None]
        gross_list = [rp.gross_total for rp in rps if rp.gross_total is not None]

        avg_pts = (sum(pts_list) / len(pts_list)) if pts_list else None
        avg_scr = (sum(scr_list) / len(scr_list)) if scr_list else None
        avg_gross = (sum(gross_list) / len(gross_list)) if gross_list else None
        best_round = max(pts_list) if pts_list else None

        # hole scores globales
        hole_scores = []
        for rp in rps:
            hole_scores.extend(rp.hole_scores)

        fir_total = sum(1 for s in hole_scores if s.fir is True)
        fir_possible = sum(1 for s in hole_scores if s.fir is not None)
        fir_pct = (fir_total / fir_possible * 100) if fir_possible else None

        gir_total = sum(1 for s in hole_scores if s.gir is True)
        gir_possible = sum(1 for s in hole_scores if s.gir is not None)
        gir_pct = (gir_total / gir_possible * 100) if gir_possible else None

        putts_holes = [s.putts for s in hole_scores if s.putts is not None]
        putts_per_hole = (sum(putts_holes) / len(putts_holes)) if putts_holes else None

        birdies = eagles = 0
        for rp in rps:
            holes = rp.round.course.holes
            par_map = {h.number: h.par for h in holes}
            for s in rp.hole_scores:
                d = s.gross_strokes - par_map[s.hole_number]
                if s.gross_strokes == 1:
                    birdies += 1
                elif d == -1:
                    birdies += 1
                elif d == -2:
                    eagles += 1

        ranking_rows.append({
            "player": p,
            "rounds_played": rounds_played,
            "wins": wins,
            "ties": ties,
            "avg_pts": avg_pts,
            "best_round": best_round,
            "avg_scr": avg_scr,
            "avg_gross": avg_gross,
            "fir_pct": fir_pct,
            "gir_pct": gir_pct,
            "putts_per_hole": putts_per_hole,
            "birdies": birdies,
            "eagles": eagles,
        })

    by_avg_pts = sorted(ranking_rows, key=lambda x: (x["avg_pts"] is None, -(x["avg_pts"] or 0)))
    by_avg_scr = sorted(ranking_rows, key=lambda x: (x["avg_scr"] is None, -(x["avg_scr"] or 0)))
    by_wins = sorted(ranking_rows, key=lambda x: (x["wins"] is None, -x["wins"], -x["ties"]))
    by_fir = sorted(ranking_rows, key=lambda x: (x["fir_pct"] is None, -(x["fir_pct"] or 0)))
    by_gir = sorted(ranking_rows, key=lambda x: (x["gir_pct"] is None, -(x["gir_pct"] or 0)))
    by_putts = sorted(ranking_rows, key=lambda x: (x["putts_per_hole"] is None, (x["putts_per_hole"] or 999)))
    by_birdies = sorted(ranking_rows, key=lambda x: (x["birdies"] is None, -x["birdies"]))
    by_eagles = sorted(ranking_rows, key=lambda x: (x["eagles"] is None, -x["eagles"]))

    return {
        "by_avg_pts": by_avg_pts,
        "by_avg_scr": by_avg_scr,
        "by_wins": by_wins,
        "by_fir": by_fir,
        "by_gir": by_gir,
        "by_putts": by_putts,
        "by_birdies": by_birdies,
        "by_eagles": by_eagles
    }

@app.get("/rankings", response_class=HTMLResponse)
def rankings(request: Request, db: Session = Depends(get_db)):
    data = build_rankings_data(db)
    return templates.TemplateResponse("rankings.html", {"request": request, **data})





# -----------------------------------------------------------------------------------------
# ---------------------------------- PAGINA PUBLICA ---------------------------------------
# -----------------------------------------------------------------------------------------




@app.get("/public", response_class=HTMLResponse)
def public_home(request: Request):
    return templates.TemplateResponse(
        "public_home.html",
        {"request": request}
    )



# ===========================================================================================
# ---------------------------------- PUBLIC: ROUNDS LIST ------------------------------------
# ===========================================================================================



@app.get("/public/rounds", response_class=HTMLResponse)
def public_rounds_list(
    request: Request,
    db: Session = Depends(get_db),
    course_id: str | None = None,
    player_id: str | None = None,
    year: str | None = None,
    month: str | None = None
):
    courses = crud.get_courses(db)
    players = crud.get_players(db)

    # Convertimos "" -> None y strings numéricas -> int
    course_id_int = int(course_id) if course_id and course_id.strip() != "" else None
    player_id_int = int(player_id) if player_id and player_id.strip() != "" else None
    year_int = int(year) if year and year.strip() != "" else None
    month_int = int(month) if month and month.strip() != "" else None

    q = db.query(models.Round)

    if course_id_int:
        q = q.filter(models.Round.course_id == course_id_int)

    if year_int:
        q = q.filter(
            models.Round.date >= date(year_int, 1, 1),
            models.Round.date < date(year_int + 1, 1, 1)
        )

    if month_int and year_int:
        start = date(year_int, month_int, 1)
        end = date(year_int + (month_int // 12), (month_int % 12) + 1, 1)
        q = q.filter(models.Round.date >= start, models.Round.date < end)

    if player_id_int:
        q = q.join(models.RoundPlayer).filter(models.RoundPlayer.player_id == player_id_int)

    rounds = q.order_by(models.Round.date.desc(), models.Round.id.desc()).all()

    return templates.TemplateResponse(
        "public_rounds.html",
        {
            "request": request,
            "rounds": rounds,
            "courses": courses,
            "players": players,
            "selected_course": course_id_int,
            "selected_player": player_id_int,
            "selected_year": year_int,
            "selected_month": month_int
        }
    )


# ===========================================================================================
# ------------------------------------ PUBLIC: RANKINGS -------------------------------------
# ===========================================================================================


@app.get("/public/rankings", response_class=HTMLResponse)
def public_rankings(request: Request, db: Session = Depends(get_db)):
    data = build_rankings_data(db)
    return templates.TemplateResponse("rankings.html", {"request": request, **data})




# ===========================================================================================
# ----------------------------------- PUBLIC: PLAYERS ---------------------------------------
# ===========================================================================================



@app.get("/public/players", response_class=HTMLResponse)
def public_players(request: Request, db: Session = Depends(get_db)):
    players = (
        db.query(models.Player)
        .filter(models.Player.active == True)
        .order_by(models.Player.name)
        .all()
    )
    return templates.TemplateResponse(
        "public_players.html",
        {"request": request, "players": players}
    )




# ===========================================================================================
# -------------------------------- PUBLIC: COURSES LIST -------------------------------------
# ===========================================================================================


@app.get("/public/courses", response_class=HTMLResponse)
def public_courses(
    request: Request,
    db: Session = Depends(get_db),
    city: str | None = None
):
    # lista de ciudades disponibles
    cities_q = (
        db.query(models.Course.city)
        .filter(models.Course.city.isnot(None))
        .distinct()
        .order_by(models.Course.city)
        .all()
    )
    cities = [c[0] for c in cities_q]

    q = db.query(models.Course)
    if city and city.strip() != "":
        q = q.filter(models.Course.city == city)

    courses = q.order_by(models.Course.name).all()

    return templates.TemplateResponse(
        "public_courses.html",
        {
            "request": request,
            "courses": courses,
            "cities": cities,
            "selected_city": city,
        }
    )


@app.get("/public/courses/{course_id}", response_class=HTMLResponse)
def public_course_detail(course_id: int, request: Request, db: Session = Depends(get_db)):
    course = crud.get_course(db, course_id)
    if not course:
        return HTMLResponse("Campo no encontrado", status_code=404)

    holes = crud.get_holes_for_course(db, course_id)
    holes_sorted = sorted(holes, key=lambda h: h.number)

    return templates.TemplateResponse(
        "public_course_detail.html",
        {
            "request": request,
            "course": course,
            "holes": holes_sorted,
        }
    )


# ===========================================================================================
# ------------------------------------ PUBLIC: LEAGUES LIST ---------------------------------
# ===========================================================================================


@app.get("/public/leagues", response_class=HTMLResponse)
def public_leagues(request: Request, db: Session = Depends(get_db)):
    leagues = crud.get_leagues(db)

    # Para cada liga, calculamos los jugadores que han participado
    for lg in leagues:
        rounds = crud.get_rounds_by_league(db, lg.id)

        players_set: dict[int, str] = {}
        for r in rounds:
            for rp in r.round_players:
                if rp.player is not None:
                    players_set[rp.player.id] = rp.player.name

        # cadena tipo "Arnau Segura, Javier Díaz, ..."
        players_names = ", ".join(
            sorted(players_set.values(), key=lambda n: n.lower())
        )

        # añadimos un atributo dinámico que Jinja puede leer
        lg.players_names = players_names

    return templates.TemplateResponse(
        "public_leagues.html",
        {
            "request": request,
            "leagues": leagues,
        }
    )




@app.get("/public/leagues/{league_id}", response_class=HTMLResponse)
def public_league_detail(
    league_id: int,
    request: Request,
    player_id: int | None = None,
    db: Session = Depends(get_db),
):
    league = crud.get_league(db, league_id)
    if not league:
        return HTMLResponse("Liga no encontrada", status_code=404)

    rounds = crud.get_rounds_by_league(db, league_id)
    standings = crud.compute_league_standings(db, league, rounds)

    # ---- jugadores que han jugado en esta liga ----
    players_set = {}
    for r in rounds:
        for rp in r.round_players:
            if rp.player is not None:
                players_set[rp.player.id] = rp.player

    players_in_league = sorted(players_set.values(), key=lambda p: p.name)

    # jugador seleccionado (query ?player_id=...)
    selected_player_id = player_id
    if selected_player_id is None and players_in_league:
        selected_player_id = players_in_league[0].id

    player_detail = None
    player_history: list[dict] = []

    if selected_player_id is not None:
        # participaciones de este jugador en la liga
        rps_player = []
        for r in rounds:
            for rp in r.round_players:
                if rp.player_id == selected_player_id and rp.gross_total is not None:
                    rps_player.append(rp)

        if rps_player:
            selected_player = rps_player[0].player

            rounds_played = len(rps_player)
            wins = len([rp for rp in rps_player if rp.result == "win"])
            ties = len([rp for rp in rps_player if rp.result == "tie"])

            gross_list = [rp.gross_total for rp in rps_player if rp.gross_total is not None]
            net_list = [rp.net_total for rp in rps_player if rp.net_total is not None]
            scratch_list = [
                rp.stableford_scratch_total
                for rp in rps_player
                if rp.stableford_scratch_total is not None
            ]

            avg_gross = (sum(gross_list) / len(gross_list)) if gross_list else None
            avg_net = (sum(net_list) / len(net_list)) if net_list else None
            avg_scratch = (sum(scratch_list) / len(scratch_list)) if scratch_list else None
            scratch_points_total = sum(scratch_list) if scratch_list else 0

            # 🔹 Acumuladores para NIVEL de juego medio (diferencial WHS)
            level_sum = 0.0
            level_count = 0

            # 🔹 Estadísticas por hoyo en TODA la liga
            par3_sum = par3_count = 0
            par4_sum = par4_count = 0
            par5_sum = par5_count = 0

            total_putts = 0
            putts_count = 0

            fir_total = fir_possible = 0
            gir_total = gir_possible = 0

            hio = albatros = eagles = birdies = pars = bogeys = dbl = overdbl = 0

            for rp in rps_player:
                r = rp.round
                course = r.course
                if not course:
                    continue

                # 🔹 Nivel de juego de ESTA vuelta (diferencial WHS)
                if (
                    rp.gross_total is not None
                    and course
                    and course.slope_yellow
                    and course.rating_yellow is not None
                ):
                    level = ((rp.gross_total - course.rating_yellow) * 113) / course.slope_yellow
                    level_sum += level
                    level_count += 1

                holes = course.holes
                par_map = {h.number: h.par for h in holes}

                for s in rp.hole_scores:
                    par = par_map.get(s.hole_number)
                    if par is None or s.gross_strokes is None:
                        continue

                    # Medias Par 3 / 4 / 5
                    if par == 3:
                        par3_sum += s.gross_strokes
                        par3_count += 1
                    elif par == 4:
                        par4_sum += s.gross_strokes
                        par4_count += 1
                    elif par == 5:
                        par5_sum += s.gross_strokes
                        par5_count += 1

                    # Putts
                    if s.putts is not None:
                        total_putts += s.putts
                        putts_count += 1

                    # FIR
                    if s.fir is not None:
                        fir_possible += 1
                        if s.fir:
                            fir_total += 1

                    # GIR
                    if s.gir is not None:
                        gir_possible += 1
                        if s.gir:
                            gir_total += 1

                    # Distribución resultados por hoyo
                    if s.gross_strokes == 1:
                        hio += 1
                        continue

                    d = s.gross_strokes - par
                    if d <= -3:
                        albatros += 1
                    elif d == -2:
                        eagles += 1
                    elif d == -1:
                        birdies += 1
                    elif d == 0:
                        pars += 1
                    elif d == 1:
                        bogeys += 1
                    elif d == 2:
                        dbl += 1
                    elif d >= 3:
                        overdbl += 1

            # 🔹 Medias y porcentajes
            avg_par3 = (par3_sum / par3_count) if par3_count > 0 else None
            avg_par4 = (par4_sum / par4_count) if par4_count > 0 else None
            avg_par5 = (par5_sum / par5_count) if par5_count > 0 else None
            putts_per_hole = (total_putts / putts_count) if putts_count > 0 else None

            fir_pct = (fir_total / fir_possible * 100) if fir_possible > 0 else None
            gir_pct = (gir_total / gir_possible * 100) if gir_possible > 0 else None

            # 🔹 MEDIA del NIVEL de juego (AHORA SÍ)
            level_hcp_avg = (level_sum / level_count) if level_count > 0 else None

            # 🔹 Historial de vueltas del jugador SOLO en esta liga
            for rp in sorted(rps_player, key=lambda x: x.round.date, reverse=True):
                course = rp.round.course

                # Nivel de juego por vuelta (para la tabla)
                level_hcp_round = None
                if (
                    rp.gross_total is not None
                    and course
                    and course.slope_yellow
                    and course.rating_yellow is not None
                ):
                    level_hcp_round = ((rp.gross_total - course.rating_yellow) * 113) / course.slope_yellow

                player_history.append({
                    "date": rp.round.date,
                    "course": course.name if course else "",
                    "course_hcp": rp.course_handicap,   # HCP asignado
                    "level_hcp": level_hcp_round,       # Nivel de juego por vuelta
                    "gross": rp.gross_total,
                    "net": rp.net_total,
                    "points": rp.stableford_hcp_total,
                    "scratch_points": rp.stableford_scratch_total,
                    "putts": rp.putts_total,
                    "result": rp.result,
                    "round_id": rp.round_id,
                })

            # Mejor vuelta bruta
            best_gross = min(gross_list) if gross_list else None

            player_detail = {
                "player": selected_player,
                "rounds": rounds_played,
                "wins": wins,
                "ties": ties,
                "avg_gross": avg_gross,
                "avg_net": avg_net,
                "avg_scratch": avg_scratch,
                "level_hcp_avg": level_hcp_avg,      # 👉 nivel de juego medio
                "best_gross": best_gross,
                "avg_par3": avg_par3,
                "avg_par4": avg_par4,
                "avg_par5": avg_par5,
                "total_putts": total_putts,
                "putts_per_hole": putts_per_hole,
                "fir_pct": fir_pct,
                "gir_pct": gir_pct,
                "hio": hio,
                "albatros": albatros,
                "eagles": eagles,
                "birdies": birdies,
                "pars": pars,
                "bogeys": bogeys,
                "dbl": dbl,
                "overdbl": overdbl,
                "scratch_points_total": scratch_points_total,   # 👈 NUEVO

            }

    return templates.TemplateResponse(
        "public_league_detail.html",
        {
            "request": request,
            "league": league,
            "rounds": rounds,
            "standings": standings,
            "players_in_league": players_in_league,
            "selected_player_id": selected_player_id,
            "player_detail": player_detail,
            "player_history": player_history,
        }
    )




# ===========================================================================================
# --------------------------------- PUBLIC: ROUND SUMMARY -----------------------------------
# ===========================================================================================


@app.get("/public/rounds/{round_id}", response_class=HTMLResponse)
def public_round_summary(
    round_id: int,
    request: Request,
    league_id: int | None = None,   # 👈 NUEVO
    player_id: int | None = None,
    db: Session = Depends(get_db),
):
    r = crud.get_round(db, round_id)
    if not r:
        return HTMLResponse("Vuelta no encontrada", status_code=404)

    course = crud.get_course(db, r.course_id)
    rps = crud.get_round_players(db, round_id)

    par_map = {h.number: h.par for h in course.holes}

    results = []
    summary_by_player: dict[int, dict] = {}

    # ---- Ganadores con nombre ----
    winner_names: list[str] = []
    if r.winner_player_ids:
        id_strings = [x.strip() for x in r.winner_player_ids.split(",") if x.strip()]
        ids = [int(x) for x in id_strings]
        winner_names = [crud.get_player(db, pid).name for pid in ids]

    # ---- resumen por jugador para la tabla de arriba + totales ----
    for rp in rps:
        scores = rp.hole_scores

        fir_total = sum(1 for s in scores if s.fir is True)
        fir_possible = sum(1 for s in scores if s.fir is not None)
        fir_pct = (fir_total / fir_possible * 100) if fir_possible > 0 else None

        gir_total = sum(1 for s in scores if s.gir is True)
        gir_possible = sum(1 for s in scores if s.gir is not None)
        gir_pct = (gir_total / gir_possible * 100) if gir_possible > 0 else None

        putts_holes = [s.putts for s in scores if s.putts is not None]
        putts_per_hole = (sum(putts_holes) / len(putts_holes)) if putts_holes else None

        level_hcp = None
        if rp.gross_total is not None and course and course.slope_yellow and course.rating_yellow is not None:
            level_hcp = ((rp.gross_total - course.rating_yellow) * 113) / course.slope_yellow

        hio = sum(1 for s in scores if s.gross_strokes == 1)
        albatros = sum(
            1 for s in scores
            if s.gross_strokes != 1 and (s.gross_strokes - par_map[s.hole_number]) <= -3
        )
        eagles = sum(
            1 for s in scores
            if s.gross_strokes != 1 and (s.gross_strokes - par_map[s.hole_number]) == -2
        )
        birdies = sum(
            1 for s in scores
            if s.gross_strokes != 1 and (s.gross_strokes - par_map[s.hole_number]) == -1
        )
        pars = sum(
            1 for s in scores
            if s.gross_strokes != 1 and (s.gross_strokes - par_map[s.hole_number]) == 0
        )
        bogeys = sum(
            1 for s in scores
            if s.gross_strokes != 1 and (s.gross_strokes - par_map[s.hole_number]) == 1
        )
        dbl = sum(
            1 for s in scores
            if s.gross_strokes != 1 and (s.gross_strokes - par_map[s.hole_number]) == 2
        )
        overdbl = sum(
            1 for s in scores
            if s.gross_strokes != 1 and (s.gross_strokes - par_map[s.hole_number]) >= 3
        )

        row = {
            "player": rp.player,
            "course_handicap": rp.course_handicap,
            "gross_total": rp.gross_total,
            "net_total": rp.net_total,
            "points": rp.stableford_hcp_total,
            "scratch_points": rp.stableford_scratch_total,
            "putts": rp.putts_total,
            "putts_per_hole": putts_per_hole,
            "level_hcp": level_hcp,
            "fir": fir_total,
            "fir_possible": fir_possible,
            "fir_pct": fir_pct,
            "gir": gir_total,
            "gir_possible": gir_possible,
            "gir_pct": gir_pct,
            "hio": hio,
            "albatros": albatros,
            "eagles": eagles,
            "birdies": birdies,
            "pars": pars,
            "bogeys": bogeys,
            "dbl": dbl,
            "overdbl": overdbl,
        }
        results.append(row)

        summary_by_player[rp.player_id] = {
            "player": rp.player,                    # 👈 AÑADIMOS ESTO
            "gross_total": rp.gross_total,
            "net_total": rp.net_total,
            "points": rp.stableford_hcp_total,
            "scratch_points": rp.stableford_scratch_total,
            "putts": rp.putts_total,
            "fir": fir_total,
            "fir_possible": fir_possible,
            "gir": gir_total,
            "gir_possible": gir_possible,
        }


    players_in_round = [rp.player for rp in rps]

    selected_player_id_final = player_id
    if selected_player_id_final is None and players_in_round:
        selected_player_id_final = players_in_round[0].id

    selected_rows: list[dict] = []
    selected_totals: dict | None = None

    if selected_player_id_final is not None:
        holes = crud.get_holes_for_course(db, r.course_id)
        holes_sorted = sorted(holes, key=lambda h: h.number)

        for rp in rps:
            if rp.player_id != selected_player_id_final:
                continue

            scores_map = {s.hole_number: s for s in rp.hole_scores}

            par3_sum = par3_count = 0
            par4_sum = par4_count = 0
            par5_sum = par5_count = 0
            putts_sum = 0
            putts_count = 0

            for h in holes_sorted:
                s = scores_map.get(h.number)

                gross = s.gross_strokes if s else None
                net = s.net_strokes if s else None
                pts = s.stableford_points if s else None
                putts = s.putts if s else None
                fir = s.fir if s else None
                gir = s.gir if s else None

                selected_rows.append({
                    "number": h.number,
                    "par": h.par,
                    "stroke_index": h.stroke_index,
                    "meters": h.meters_yellow,
                    "gross": gross,
                    "net": net,
                    "pts": pts,
                    "putts": putts,
                    "fir": fir,
                    "gir": gir,
                })

                if gross is not None and h.par is not None:
                    if h.par == 3:
                        par3_sum += gross
                        par3_count += 1
                    elif h.par == 4:
                        par4_sum += gross
                        par4_count += 1
                    elif h.par == 5:
                        par5_sum += gross
                        par5_count += 1

                if putts is not None:
                    putts_sum += putts
                    putts_count += 1

            avg_par3 = (par3_sum / par3_count) if par3_count > 0 else None
            avg_par4 = (par4_sum / par4_count) if par4_count > 0 else None
            avg_par5 = (par5_sum / par5_count) if par5_count > 0 else None
            putts_per_hole_round = (putts_sum / putts_count) if putts_count > 0 else None

            st = summary_by_player.get(selected_player_id_final)
            if st:
                selected_totals = {
                    "gross": st["gross_total"],
                    "net": st["net_total"],
                    "points": st["points"],
                    "scratch_points": st["scratch_points"],
                    "putts": st["putts"],
                    "fir": st["fir"],
                    "fir_possible": st["fir_possible"],
                    "gir": st["gir"],
                    "gir_possible": st["gir_possible"],
                    "avg_par3": avg_par3,
                    "avg_par4": avg_par4,
                    "avg_par5": avg_par5,
                    "putts_per_hole": putts_per_hole_round,
                }
            break

    return templates.TemplateResponse(
        "public_round_summary.html",
        {
            "request": request,
            "round": r,
            "course": course,
            "results": results,
            "winner_names": winner_names,
            "summary_by_player": summary_by_player,   # 👈 ESTA LÍNEA ES CLAVE
            "players_in_round": players_in_round,
            "selected_player_id": selected_player_id_final,
            "selected_rows": selected_rows,
            "selected_totals": selected_totals,
            "league_id": league_id,   # 👈 NUEVO
        }
    )




# ======================================================================================
# ------------------------------------ PUBLIC: STATS -----------------------------------
# ======================================================================================



@app.get("/public/stats", response_class=HTMLResponse)
def public_stats(
    request: Request,
    player_id: str | None = None,
    course_id: str | None = None,
    year: str | None = None,
    db: Session = Depends(get_db),
):
    # ---- helpers ----
    def as_int(v: str | None) -> int | None:
        if v is None or v == "":
            return None
        try:
            return int(v)
        except ValueError:
            return None

    player_id_i = as_int(player_id)
    course_id_i = as_int(course_id)
    year_i = as_int(year)

    # ---- combos filtros ----
    players = db.query(Player).order_by(Player.name).all()
    courses = db.query(Course).order_by(Course.name).all()

    years = [
        int(y[0]) for y in (
            db.query(extract("year", Round.date))
              .distinct()
              .order_by(extract("year", Round.date).desc())
              .all()
        )
        if y[0] is not None
    ]

    # ---- query base: RoundPlayer (1 fila por jugador y vuelta) ----
    q = (
        db.query(RoundPlayer)
          .join(RoundPlayer.round)     # -> Round
          .join(RoundPlayer.player)    # -> Player
          .join(Round.course)          # -> Course
    )

    if player_id_i is not None:
        q = q.filter(RoundPlayer.player_id == player_id_i)
    if course_id_i is not None:
        q = q.filter(Round.course_id == course_id_i)
    if year_i is not None:
        q = q.filter(extract("year", Round.date) == year_i)

    round_players = q.order_by(Round.date.desc(), RoundPlayer.id.desc()).all()

    # ---- Precargar HoleScore de los RoundPlayer seleccionados ----
    rp_ids = [rp.id for rp in round_players]
    holes_by_rp: dict[int, dict[int, int]] = {}

    if rp_ids:
        hole_scores = (
            db.query(HoleScore)
              .filter(HoleScore.round_player_id.in_(rp_ids))
              .all()
        )
        for hs in hole_scores:
            holes_by_rp.setdefault(hs.round_player_id, {})[hs.hole_number] = hs.gross_strokes

    # ---- construir rows para la tabla (dict con h1..h18) ----
    rounds_rows: list[dict] = []
    for rp in round_players:
        r = rp.round
        c = r.course
        p = rp.player

        row = {
            "date": r.date,
            "course_name": c.name if c else "-",
            "course_id": c.id if c else None,
            "player_name": p.name if p else "-",
            "player_id": p.id if p else None,

            # (La columna Torneo ya no la mostramos, pero la dejo por si luego la quieres recuperar)
            "tournament_name": (r.league.name if r.league else r.type),

            "hcp": rp.course_handicap,
            "play_level": rp.stableford_scratch_total,
            "total": rp.gross_total,
            "points": rp.stableford_hcp_total,
        }

        hs_map = holes_by_rp.get(rp.id, {})
        for i in range(1, 19):
            row[f"h{i}"] = hs_map.get(i)

        rounds_rows.append(row)

    # ---- Par por hoyo por campo (para colorear resultados y calcular birdies) ----
    course_ids = sorted({rp.round.course_id for rp in round_players if rp.round and rp.round.course_id})
    hole_par_by_course: dict[int, dict[int, int]] = {}

    if course_ids:
        holes = (
            db.query(Hole)
              .filter(Hole.course_id.in_(course_ids))
              .all()
        )
        for h in holes:
            hole_par_by_course.setdefault(h.course_id, {})[h.number] = h.par

    # ---- Birdies totales en el set (golpes = par-1) ----
    birdies_total = 0
    for rr in rounds_rows:
        cid = rr.get("course_id")
        if not cid:
            continue
        par_map = hole_par_by_course.get(cid, {})
        for i in range(1, 19):
            s_h = rr.get(f"h{i}")
            p_h = par_map.get(i)
            if s_h is not None and p_h is not None and (s_h - p_h) == -1:
                birdies_total += 1

    # ---- KPIs sobre el set filtrado ----
    stats_q = (
        db.query(
            func.count(RoundPlayer.id).label("rounds_count"),
            func.avg(RoundPlayer.course_handicap).label("avg_hcp"),
            func.avg(RoundPlayer.gross_total).label("avg_gross"),
            func.avg(RoundPlayer.net_total).label("avg_net"),
            func.avg(RoundPlayer.stableford_hcp_total).label("avg_stb"),
        )
        .join(RoundPlayer.round)
    )

    if player_id_i is not None:
        stats_q = stats_q.filter(RoundPlayer.player_id == player_id_i)
    if course_id_i is not None:
        stats_q = stats_q.filter(Round.course_id == course_id_i)
    if year_i is not None:
        stats_q = stats_q.filter(extract("year", Round.date) == year_i)

    s = stats_q.one()

    # ---- FIR / GIR (calculado desde HoleScore) ----
    fir_pct = None
    gir_pct = None

    if rp_ids:
        fir_total = (
            db.query(func.count(HoleScore.id))
              .filter(HoleScore.round_player_id.in_(rp_ids))
              .filter(HoleScore.fir.isnot(None))
              .scalar()
        ) or 0

        fir_yes = (
            db.query(func.count(HoleScore.id))
              .filter(HoleScore.round_player_id.in_(rp_ids))
              .filter(HoleScore.fir.is_(True))
              .scalar()
        ) or 0

        gir_total = (
            db.query(func.count(HoleScore.id))
              .filter(HoleScore.round_player_id.in_(rp_ids))
              .filter(HoleScore.gir.isnot(None))
              .scalar()
        ) or 0

        gir_yes = (
            db.query(func.count(HoleScore.id))
              .filter(HoleScore.round_player_id.in_(rp_ids))
              .filter(HoleScore.gir.is_(True))
              .scalar()
        ) or 0

        if fir_total > 0:
            fir_pct = 100.0 * fir_yes / fir_total
        if gir_total > 0:
            gir_pct = 100.0 * gir_yes / gir_total

    stats = {
        "rounds_count": int(s.rounds_count or 0),
        "avg_hcp": float(s.avg_hcp) if s.avg_hcp is not None else None,
        "avg_gross": float(s.avg_gross) if s.avg_gross is not None else None,
        "avg_net": float(s.avg_net) if s.avg_net is not None else None,
        "avg_stb": float(s.avg_stb) if s.avg_stb is not None else None,
        "fir_pct": fir_pct,
        "gir_pct": gir_pct,
        "birdies": int(birdies_total),
    }

    # ---- Mejor vuelta (por Puntos, desempate por Total menor) ----
    best_round = None
    if rounds_rows:
        def best_key(rw: dict):
            pts = rw.get("points")
            tot = rw.get("total")
            return (
                pts if pts is not None else -1,         # mayor mejor
                -(tot if tot is not None else 10**9),   # menor mejor
            )
        best_round = max(rounds_rows, key=best_key)

    return templates.TemplateResponse("public_stats.html", {
        "request": request,
        "players": players,
        "courses": courses,
        "years": years,
        "player_id": player_id_i,
        "course_id": course_id_i,
        "year": year_i,
        "rounds": rounds_rows,
        "stats": stats,
        "hole_par_by_course": hole_par_by_course,
        "best_round": best_round,
    })



# ---------------------------------------------------------------------------


@app.get("/health")
def health():
    return {"status": "ok"}
