import os
import smtplib
from email.message import EmailMessage


def send_admin_email(subject: str, body: str) -> None:
    host = os.environ.get("SMTP_HOST")
    port = os.environ.get("SMTP_PORT")
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS", "")
    to_email = os.environ.get("ADMIN_EMAIL")

    print("EMAIL DEBUG host:", host)
    print("EMAIL DEBUG port env:", port)
    print("EMAIL DEBUG user:", user)
    print("EMAIL DEBUG pass_len:", len(password))
    print("EMAIL DEBUG pass_head_tail:", (password[:2] + "***" + password[-2:]) if password else "EMPTY")
    print("EMAIL DEBUG to:", to_email)


    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    # ✅ SMTP SSL (NO starttls)
    with smtplib.SMTP_SSL(host, 465) as server:
        server.login(user, password)
        server.send_message(msg)
        