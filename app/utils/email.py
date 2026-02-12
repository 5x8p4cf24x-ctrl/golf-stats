import os
import requests


def send_admin_email(subject: str, body: str) -> None:
    api_key = os.environ["RESEND_API_KEY"]
    to_email = os.environ["ADMIN_EMAIL"]
    from_email = os.environ["EMAIL_FROM"]

    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "from": f"GolfMode <{from_email}>",
            "to": [to_email],
            "subject": subject,
            "text": body,
        },
    )

    if response.status_code >= 400:
        print("ERROR resend:", response.text)
    else:
        print("Resend email sent successfully")
