# app/auth/routes.py
from fastapi import APIRouter, Depends, Request, Form, Query
from fastapi.responses import HTMLResponse
from starlette.responses import RedirectResponse
from starlette.status import HTTP_303_SEE_OTHER
from sqlalchemy.orm import Session

from app.db import get_db
from app import models
from app.web import templates
from app.utils.email import send_user_email
from app.auth.security import (
    make_reset_token,
    reset_expiration_datetime,
    hash_password,
    now_utc,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# ===========================
# FORGOT PASSWORD (FORM)
# ===========================
@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_form(request: Request):
    # Formulario para pedir el email
    return templates.TemplateResponse("forgot_password.html", {"request": request})


# ===========================
# REQUEST RESET (POST)
# ===========================
@router.post("/password-reset/request", response_class=HTMLResponse)
def request_password_reset(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db),
):
    email_norm = (email or "").strip().lower()

    user = (
        db.query(models.User)
        .filter(models.User.email.ilike(email_norm))
        .first()
    )

    if user and user.is_active:
        token = make_reset_token()
        user.reset_token = token
        user.reset_token_expires_at = reset_expiration_datetime()
        db.commit()

        import os

        base = (os.getenv("PUBLIC_BASE_URL") or "").rstrip("/")
        if not base:
            # Fallback seguro (local/dev) si alguien olvidó la env var
            base = str(request.base_url).rstrip("/")

        reset_url = f"{base}/auth/reset-password?token={token}"

        subject = "Golf Mode · Cambiar contraseña"

        text = (
            "Has solicitado cambiar tu contraseña.\n\n"
            f"Abre este enlace:\n{reset_url}\n\n"
            "Si no has sido tú, ignora este email."
        )

        html = f"""
        <div style="font-family:Arial, sans-serif; line-height:1.5">
          <h2 style="margin:0 0 12px 0;">Cambiar contraseña</h2>
          <p style="margin:0 0 12px 0;">Has solicitado cambiar tu contraseña.</p>
          <p style="margin:0 0 16px 0;">
            <a href="{reset_url}" style="display:inline-block; padding:10px 14px; text-decoration:none; border-radius:10px;">
              Abrir enlace de cambio
            </a>
          </p>
          <p style="margin:0 0 12px 0; font-size:14px;">
            Si el botón no funciona, copia y pega este enlace:
            <br>
            <a href="{reset_url}">{reset_url}</a>
          </p>
          <p style="margin:16px 0 0 0; font-size:12px; opacity:0.7;">
            Si no has sido tú, ignora este email.
          </p>
        </div>
        """

        # IMPORTANTE: aquí ajustamos a la firma real del helper
        # (en el siguiente paso te dejo el email.py para que esto encaje 100%)
        send_user_email(
            to_email=user.email,
            subject="Golf Mode · Cambiar contraseña",
            body=(
                "Has solicitado cambiar tu contraseña.\n\n"
                f"Abre este enlace:\n{reset_url}\n\n"
                "Si no has sido tú, ignora este email."
            ),
            html=f"""
            <div style="font-family:Arial, sans-serif; line-height:1.5">
            <h2 style="margin:0 0 12px 0;">Cambiar contraseña</h2>
            <p style="margin:0 0 12px 0;">Has solicitado cambiar tu contraseña.</p>
            <p style="margin:0 0 16px 0;">
                <a href="{reset_url}" style="display:inline-block; padding:10px 14px; border-radius:10px; text-decoration:none;">
                Abrir enlace de cambio
                </a>
            </p>
            <p style="margin:0; font-size:14px;">
                Si el botón no funciona, copia y pega este enlace:<br>
                <a href="{reset_url}">{reset_url}</a>
            </p>
            <p style="margin:16px 0 0 0; font-size:12px; opacity:0.7;">
                Si no has sido tú, ignora este email.
            </p>
            </div>
            """,
        )

    return templates.TemplateResponse(
        "forgot_password_sent.html",
        {"request": request, "email": email_norm},
    )


# ===========================
# RESET PASSWORD (FORM)
# ===========================
@router.get("/reset-password", response_class=HTMLResponse, name="password_reset_form")
def password_reset_form(
    request: Request,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    token = (token or "").strip()
    u = db.query(models.User).filter(models.User.reset_token == token).first()

    if (not u) or (not u.reset_token_expires_at) or (u.reset_token_expires_at < now_utc()):
        return templates.TemplateResponse("reset_password_invalid.html", {"request": request})

    return templates.TemplateResponse("reset_password.html", {"request": request, "token": token})


# ===========================
# RESET PASSWORD (POST)
# ===========================
@router.post("/reset-password")
def password_reset_submit(
    request: Request,
    token: str = Form(...),
    password1: str = Form(...),
    password2: str = Form(...),
    db: Session = Depends(get_db),
):
    token = (token or "").strip()

    if password1 != password2:
        return templates.TemplateResponse(
            "reset_password.html",
            {"request": request, "token": token, "error": "Las contraseñas no coinciden."},
        )

    if len(password1) < 8:
        return templates.TemplateResponse(
            "reset_password.html",
            {"request": request, "token": token, "error": "La contraseña debe tener mínimo 8 caracteres."},
        )

    u = db.query(models.User).filter(models.User.reset_token == token).first()
    if (not u) or (not u.reset_token_expires_at) or (u.reset_token_expires_at < now_utc()):
        return templates.TemplateResponse("reset_password_invalid.html", {"request": request})

    u.password_hash = hash_password(password1)
    u.reset_token = None
    u.reset_token_expires_at = None
    db.commit()

    return RedirectResponse(url="/login?reset=1", status_code=HTTP_303_SEE_OTHER)