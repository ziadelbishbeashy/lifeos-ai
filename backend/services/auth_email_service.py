"""Transactional authentication email helpers for V-SPACE."""

from __future__ import annotations

from html import escape

from flask import current_app

from services.auth_security_service import RESET_PURPOSE, VERIFY_PURPOSE, issue_user_auth_token
from services.email_service import send_email


def _frontend_url(path: str) -> str:
    base = str(current_app.config.get("FRONTEND_BASE_URL") or current_app.config.get("PUBLIC_BASE_URL") or "").rstrip("/")
    return f"{base}{path}"


def _action_email_html(*, name: str, title: str, message: str, action_label: str, link: str, expiry: str) -> str:
    safe_name = escape(str(name or "there"))
    safe_title = escape(title)
    safe_message = escape(message)
    safe_label = escape(action_label)
    safe_link = escape(link, quote=True)
    safe_expiry = escape(expiry)
    return f"""<!doctype html>
<html>
  <body style="margin:0;background:#080d18;color:#f5f8ff;font-family:Arial,sans-serif;padding:32px 16px;">
    <div style="max-width:560px;margin:0 auto;background:#111b2e;border:1px solid #21314b;border-radius:18px;padding:30px;">
      <div style="font-weight:700;font-size:18px;color:#67b7ff;margin-bottom:22px;">V-SPACE AI</div>
      <h1 style="font-size:24px;margin:0 0 14px;">{safe_title}</h1>
      <p style="color:#a7b4ca;line-height:1.65;">Hi {safe_name},</p>
      <p style="color:#a7b4ca;line-height:1.65;">{safe_message}</p>
      <p style="margin:26px 0;">
        <a href="{safe_link}" style="display:inline-block;background:#4d8dff;color:#fff;text-decoration:none;font-weight:700;padding:12px 18px;border-radius:10px;">{safe_label}</a>
      </p>
      <p style="color:#6f7d94;font-size:13px;line-height:1.55;">{safe_expiry}</p>
      <p style="color:#6f7d94;font-size:13px;line-height:1.55;">If you did not request this action, you can ignore this email.</p>
    </div>
  </body>
</html>"""


def send_password_reset_email(user):
    minutes = int(current_app.config.get("PASSWORD_RESET_MINUTES") or 30)
    issued = issue_user_auth_token(
        user=user,
        purpose=RESET_PURPOSE,
        lifetime_minutes=minutes,
    )
    link = _frontend_url(f"/reset-password?token={issued.raw_token}")
    send_email(
        user.email,
        "Reset your V-SPACE password",
        (
            f"Hi {user.name},\n\n"
            "We received a request to reset your V-SPACE password.\n\n"
            f"Reset your password: {link}\n\n"
            f"This link expires in {minutes} minutes and can be used once.\n"
            "If you did not request this, you can ignore this email."
        ),
        html_body=_action_email_html(
            name=user.name,
            title="Reset your password",
            message="We received a request to reset your V-SPACE password.",
            action_label="Reset password",
            link=link,
            expiry=f"This secure link expires in {minutes} minutes and can be used once.",
        ),
    )
    return issued


def send_email_verification(user):
    minutes = int(current_app.config.get("EMAIL_VERIFICATION_MINUTES") or 60)
    issued = issue_user_auth_token(
        user=user,
        purpose=VERIFY_PURPOSE,
        lifetime_minutes=minutes,
    )
    link = _frontend_url(f"/verify-email?token={issued.raw_token}")
    send_email(
        user.email,
        "Verify your V-SPACE email",
        (
            f"Hi {user.name},\n\n"
            "Verify this email address for your V-SPACE account.\n\n"
            f"Verify email: {link}\n\n"
            f"This link expires in {minutes} minutes and can be used once.\n"
            "If you did not create this account, you can ignore this email."
        ),
        html_body=_action_email_html(
            name=user.name,
            title="Verify your email",
            message="Verify this email address to secure your V-SPACE account and enable account recovery.",
            action_label="Verify email",
            link=link,
            expiry=f"This secure link expires in {minutes} minutes and can be used once.",
        ),
    )
    return issued
