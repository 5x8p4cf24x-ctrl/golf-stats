# app/utils/email.py
import os
import requests
from typing import Optional


RESEND_URL = "https://api.resend.com/emails"


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _post_resend(payload: dict, api_key: str) -> bool:
    resp = requests.post(
        RESEND_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=15,
    )

    if resp.status_code >= 400:
        print("ERROR resend:", resp.status_code, resp.text)
        return False

    print("Resend email sent successfully")
    return True


def send_email(
    *,
    to_email: str,
    subject: str,
    text: str,
    html: Optional[str] = None,
) -> bool:
    api_key = _env("RESEND_API_KEY")
    from_email = _env("EMAIL_FROM")

    if not api_key or not from_email:
        print("⚠️ EMAIL NO ENVIADO (faltan RESEND_API_KEY o EMAIL_FROM)")
        print("To:", to_email)
        print("Subject:", subject)
        print("Text:\n", text)
        if html:
            print("HTML:\n", html)
        return False

    payload = {
        "from": f"GolfMode <{from_email}>",
        "to": [to_email],
        "subject": subject,
        "text": text,
    }
    if html:
        payload["html"] = html

    return _post_resend(payload, api_key)


def send_admin_email(subject: str, body: str, html: Optional[str] = None) -> bool:
    to_email = _env("ADMIN_EMAIL")
    if not to_email:
        print("⚠️ EMAIL ADMIN NO ENVIADO (falta ADMIN_EMAIL)")
        print("Subject:", subject)
        print("Body:\n", body)
        return False

    return send_email(to_email=to_email, subject=subject, text=body, html=html)


def send_user_email(to_email: str, subject: str, body: str, html: Optional[str] = None) -> bool:
    # Mantengo 'body' para que NO te rompa nada en el código existente
    return send_email(to_email=to_email, subject=subject, text=body, html=html)