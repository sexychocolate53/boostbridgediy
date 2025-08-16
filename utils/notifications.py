# utils/notifications.py
import os, smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from dotenv import load_dotenv

load_dotenv()

# Email config (choose one)
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
EMAIL_FROM       = os.getenv("NOTIFY_EMAIL_FROM", "no-reply@boostbridgediy.com")

# SMTP fallback (if no SendGrid)
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or "587")
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_TLS  = (os.getenv("SMTP_TLS", "true").lower() == "true")

# SMS via Twilio (optional)
TWILIO_SID   = os.getenv("TWILIO_SID", "")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM  = os.getenv("TWILIO_FROM", "")

def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """Send email via SendGrid if configured; else SMTP; else simulate."""
    if not to_email:
        return False

    # Try SendGrid first
    if SENDGRID_API_KEY:
        try:
            import requests, json
            resp = requests.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {SENDGRID_API_KEY}",
                         "Content-Type": "application/json"},
                json={
                    "personalizations": [{"to": [{"email": to_email}]}],
                    "from": {"email": EMAIL_FROM, "name": "BoostBridgeDIY"},
                    "subject": subject,
                    "content": [{"type": "text/html", "value": html_body}],
                },
                timeout=15
            )
            return resp.status_code in (200, 202)
        except Exception:
            pass

    # SMTP fallback
    if SMTP_HOST and SMTP_USER and SMTP_PASS:
        try:
            msg = MIMEText(html_body, "html")
            msg["Subject"] = subject
            msg["From"] = formataddr(("BoostBridgeDIY", EMAIL_FROM))
            msg["To"] = to_email
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20)
            if SMTP_TLS:
                server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(EMAIL_FROM, [to_email], msg.as_string())
            server.quit()
            return True
        except Exception:
            return False

    # If nothing configured, pretend success (for dev)
    return True

def send_sms(to_phone: str, body: str) -> bool:
    """Send SMS via Twilio if configured; else simulate."""
    if not to_phone:
        return False
    if TWILIO_SID and TWILIO_TOKEN and TWILIO_FROM:
        try:
            from twilio.rest import Client
            client = Client(TWILIO_SID, TWILIO_TOKEN)
            client.messages.create(from_=TWILIO_FROM, to=to_phone, body=body)
            return True
        except Exception:
            return False
    return True  # simulate in dev
