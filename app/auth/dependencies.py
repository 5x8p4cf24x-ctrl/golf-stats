from fastapi import Request, Depends, HTTPException
from sqlalchemy.orm import Session
from starlette.status import HTTP_401_UNAUTHORIZED

from app.db import get_db
from app.models import User, Player


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED)

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED)

    return user


def get_current_player(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Player:
    player = db.query(Player).filter(Player.user_id == user.id).first()
    if not player:
        raise HTTPException(status_code=400, detail="Usuario sin jugador vinculado")

    return player

from typing import Optional
from sqlalchemy.orm import Session

def get_current_player_optional(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[Player]:
    try:
        user = get_current_user(request, db)
    except Exception:
        return None

    player = db.query(Player).filter(Player.user_id == user.id).first()
    return player