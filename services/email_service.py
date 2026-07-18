import os
import smtplib
from email.message import EmailMessage


TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_bool(name, default=False):
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in TRUE_VALUES


def get_email_settings():
    """Return SMTP settings from environment variables."""

    username = os.getenv("MAIL_USERNAME")
    default_sender = os.getenv("MAIL_DEFAULT_SENDER") or username

    return {
        "server": os.getenv("MAIL_SERVER", "smtp.gmail.com"),
        "port": int(os.getenv("MAIL_PORT", "587")),
        "use_tls": _env_bool("MAIL_USE_TLS", True),
        "username": username,
        "password": os.getenv("MAIL_PASSWORD"),
        "default_sender": default_sender,
    }


def email_is_configured():
    settings = get_email_settings()

    required_values = [
        settings["server"],
        settings["port"],
        settings["username"],
        settings["password"],
        settings["default_sender"],
    ]

    return all(required_values)


def send_email(to_email, subject, body, html_body=None):
    """Send one email using SMTP.

    This service intentionally uses Python standard-library SMTP so Phase 5.1
    does not require another Flask extension.
    """

    settings = get_email_settings()

    if not email_is_configured():
        raise RuntimeError(
            "Email is not configured. Add MAIL_USERNAME, MAIL_PASSWORD, "
            "MAIL_SERVER, MAIL_PORT and MAIL_DEFAULT_SENDER to .env."
        )

    message = EmailMessage()
    message["From"] = settings["default_sender"]
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    if html_body:
        message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(settings["server"], settings["port"]) as smtp:
        if settings["use_tls"]:
            smtp.starttls()

        smtp.login(settings["username"], settings["password"])
        smtp.send_message(message)

    return True
