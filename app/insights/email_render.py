from fastapi.templating import Jinja2Templates
from starlette.requests import Request
import os

templates = Jinja2Templates(directory="app/templates")

def render_round_email_html(
    request: Request,
    player_name: str,
    course_name: str,
    round_date: str,
    gross_total: str,
    play_level: str,
    gir_pct: str,
    fir_pct: str,
    putts_total: str,
    putts_per_hole: str,
    stableford: str,
    tips: list[str],
    round_url: str,
    achievements: list[str] | None = None,
    holes_out: list[dict] | None = None,
    holes_in: list[dict] | None = None,
    course_hcp: str | None = None,
) -> str:
    base_url = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

    if base_url:
        logo_url = f"{base_url}/static/LogoGMwhite.png"
    else:
        logo_url = str(request.url_for("static", path="LogoGMwhite.png"))

    ctx = {
        "request": request,
        "logo_url": logo_url,
        "player_name": player_name,
        "course_name": course_name,
        "course_hcp": course_hcp,
        "round_date": round_date,
        "gross_total": gross_total,
        "play_level": play_level,
        "gir_pct": gir_pct,
        "fir_pct": fir_pct,
        "putts_total": putts_total,
        "putts_per_hole": putts_per_hole,
        "stableford": stableford,
        "tips": tips,
        "round_url": round_url,
        "achievements": achievements or [],
        "holes_out": holes_out or [],
        "holes_in": holes_in or [],
    }
    return templates.get_template("emails/round_summary.html").render(ctx)