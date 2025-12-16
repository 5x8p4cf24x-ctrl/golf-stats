# app/routers/public.py

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.templates import templates   # 👈 importante
from app import crud                   # o como lo tengas

router = APIRouter()
