"""Provider-neutral transactional email delivery for V-SPACE.

Development can use SMTP (for example Gmail with an app password). Production
is designed to use Sender.net's transactional REST API. Authentication features
call only ``send_email`` and never depend on a provider directly.
"""

from __future__ import annotations

from email.message import EmailMessage
from email.utils import formataddr
import re
import smtplib
import ssl
from typing import Any

import requests
from flask import current_app, has_app_context


SENDER_TRANSACTIONAL_ENDPOINT = "https://api.sender.net/v2/message/send"
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
SUPPORTED_MAIL_PROVIDERS = frozenset({"smtp", "sender"})


class EmailDeliveryError(RuntimeError):
    """Raised when a configured transactional email cannot be delivered."""


def _setting(name: str, default: Any = None):
    if has_app_context():
        return current_app.config.get(name, default)
    return default


def _safe_timeout(value: Any, *, default: float) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        timeout = default
    return min(max(timeout, 1.0), 60.0)


def _safe_port(value: Any, *, default: int = 587) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        return default
    return port if 1 <= port <= 65535 else default


def get_email_settings() -> dict[str, Any]:
    """Return the active mail provider and its backend-only settings."""

    provider = str(_setting("MAIL_PROVIDER", "smtp") or "smtp").strip().lower()
    return {
        "provider": provider,
        "from_name": str(
            _setting("MAIL_FROM_NAME", _setting("SENDER_FROM_NAME", "V-SPACE")) or "V-SPACE"
        ).strip()[:100] or "V-SPACE",
        "sender": {
            "api_token": str(_setting("SENDER_API_TOKEN", "") or "").strip(),
            "from_email": str(_setting("SENDER_FROM_EMAIL", "") or "").strip(),
            "timeout": _safe_timeout(_setting("SENDER_TIMEOUT_SECONDS", 15), default=15.0),
        },
        "smtp": {
            "server": str(_setting("MAIL_SERVER", "smtp.gmail.com") or "smtp.gmail.com").strip(),
            "port": _safe_port(_setting("MAIL_PORT", 587)),
            "use_tls": bool(_setting("MAIL_USE_TLS", True)),
            "username": str(_setting("MAIL_USERNAME", "") or "").strip(),
            "password": str(_setting("MAIL_PASSWORD", "") or ""),
            "from_email": str(
                _setting("MAIL_DEFAULT_SENDER", "") or _setting("MAIL_USERNAME", "") or ""
            ).strip(),
            "timeout": _safe_timeout(_setting("MAIL_TIMEOUT_SECONDS", 20), default=20.0),
        },
    }


def email_is_configured() -> bool:
    settings = get_email_settings()
    provider = settings["provider"]
    if provider == "sender":
        sender = settings["sender"]
        return bool(sender["api_token"] and sender["from_email"])
    if provider == "smtp":
        smtp = settings["smtp"]
        return bool(
            smtp["server"]
            and smtp["port"]
            and smtp["username"]
            and smtp["password"]
            and smtp["from_email"]
        )
    return False


def _valid_email(value: str) -> bool:
    return bool(_EMAIL_RE.fullmatch(str(value or "").strip()))


def _validate_common(*, recipient: str, subject: str, body: str) -> None:
    if not _valid_email(recipient):
        raise EmailDeliveryError("The transactional email recipient is invalid.")
    if not subject or not body.strip():
        raise EmailDeliveryError("Transactional email subject and body are required.")


def _send_with_sender(*, settings: dict[str, Any], recipient: str, subject: str, body: str, html_body: str | None) -> bool:
    sender = settings["sender"]
    if not sender["api_token"] or not sender["from_email"]:
        raise EmailDeliveryError(
            "Sender transactional email is not configured. Set SENDER_API_TOKEN and SENDER_FROM_EMAIL."
        )
    if not _valid_email(sender["from_email"]):
        raise EmailDeliveryError("SENDER_FROM_EMAIL must be a valid verified sender address.")

    payload: dict[str, Any] = {
        "from": {"email": sender["from_email"], "name": settings["from_name"]},
        "to": {"email": recipient},
        "subject": subject,
        "text": body,
    }
    if html_body:
        payload["html"] = str(html_body)

    try:
        response = requests.post(
            SENDER_TRANSACTIONAL_ENDPOINT,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {sender['api_token']}",
            },
            json=payload,
            timeout=sender["timeout"],
        )
    except requests.RequestException as error:
        raise EmailDeliveryError("Sender could not be reached to deliver this email.") from error

    if not 200 <= response.status_code < 300:
        # Never surface Sender's response body to API callers.
        raise EmailDeliveryError(
            f"Sender rejected the transactional email (HTTP {response.status_code})."
        )
    return True


def _send_with_smtp(*, settings: dict[str, Any], recipient: str, subject: str, body: str, html_body: str | None) -> bool:
    smtp_settings = settings["smtp"]
    if not all(
        (
            smtp_settings["server"],
            smtp_settings["port"],
            smtp_settings["username"],
            smtp_settings["password"],
            smtp_settings["from_email"],
        )
    ):
        raise EmailDeliveryError(
            "SMTP email is not configured. Set MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, "
            "MAIL_PASSWORD and MAIL_DEFAULT_SENDER."
        )
    if not _valid_email(smtp_settings["from_email"]):
        raise EmailDeliveryError("MAIL_DEFAULT_SENDER must be a valid email address.")

    message = EmailMessage()
    message["From"] = formataddr((settings["from_name"], smtp_settings["from_email"]))
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    if html_body:
        message.add_alternative(str(html_body), subtype="html")

    try:
        with smtplib.SMTP(
            smtp_settings["server"],
            smtp_settings["port"],
            timeout=smtp_settings["timeout"],
        ) as smtp:
            smtp.ehlo()
            if smtp_settings["use_tls"]:
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            smtp.login(smtp_settings["username"], smtp_settings["password"])
            smtp.send_message(message)
    except (smtplib.SMTPException, OSError) as error:
        # Do not echo provider/server details into user-facing responses.
        raise EmailDeliveryError("SMTP could not deliver this email.") from error
    return True


def send_email(to_email, subject, body, html_body=None):
    """Send one transactional email through the configured provider.

    ``MAIL_PROVIDER=smtp`` is intended for local development. Production should
    set ``MAIL_PROVIDER=sender`` and use a verified Sender.net domain/address.
    Provider credentials never leave the backend.
    """

    settings = get_email_settings()
    recipient = str(to_email or "").strip()
    clean_subject = " ".join(str(subject or "").split())[:255]
    text_body = str(body or "")
    _validate_common(recipient=recipient, subject=clean_subject, body=text_body)

    provider = settings["provider"]
    if provider == "sender":
        return _send_with_sender(
            settings=settings,
            recipient=recipient,
            subject=clean_subject,
            body=text_body,
            html_body=html_body,
        )
    if provider == "smtp":
        return _send_with_smtp(
            settings=settings,
            recipient=recipient,
            subject=clean_subject,
            body=text_body,
            html_body=html_body,
        )
    raise EmailDeliveryError(
        f"Unsupported MAIL_PROVIDER '{provider}'. Use 'smtp' or 'sender'."
    )
