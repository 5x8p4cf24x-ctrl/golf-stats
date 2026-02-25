from passlib.context import CryptContext
import secrets
from datetime import datetime, timedelta, timezone
import os

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)

RESET_TTL_HOURS = int(os.getenv("RESET_TTL_HOURS", "24"))

def make_reset_token() -> str:
    return secrets.token_urlsafe(32)

def now_utc():
    return datetime.utcnow()

def reset_expiration_datetime() -> datetime:
    return now_utc() + timedelta(hours=RESET_TTL_HOURS)
