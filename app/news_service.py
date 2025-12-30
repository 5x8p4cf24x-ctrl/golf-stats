from sqlalchemy.orm import Session
from . import crud

def news_league_started(db: Session, *, league_name: str, league_url: str | None = None):
    title = f"Arranca la liga: {league_name}"
    excerpt = (
        f"Ya está en marcha {league_name}. "
        "¡Mucha suerte a todos y a por el título!"
    )
    return crud.create_news(
        db,
        title=title,
        excerpt=excerpt,
        category="league",
        related_url=league_url,
    )

def news_achievement_unlocked(
    db: Session,
    *,
    player_name: str,
    achievement_name: str,
    player_url: str | None = None,
):
    title = f"{player_name} desbloquea: {achievement_name}"
    excerpt = (
        f"Nuevo logro para {player_name}: {achievement_name}. "
        "Seguimos sumando hitos en GolfMode."
    )
    return crud.create_news(
        db,
        title=title,
        excerpt=excerpt,
        category="achievement",
        related_url=player_url,
    )

def news_record_broken(
    db: Session,
    *,
    player_name: str,
    record_name: str,
    value: str,
    related_url: str | None = None,
):
    title = f"Récord batido: {record_name}"
    excerpt = (
        f"{player_name} marca un nuevo récord en {record_name}: {value}. "
        "Histórico."
    )
    return crud.create_news(
        db,
        title=title,
        excerpt=excerpt,
        category="record",
        related_url=related_url,
    )
