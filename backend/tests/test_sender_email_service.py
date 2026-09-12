"""Provider-neutral transactional email delivery contract."""

import smtplib

import pytest
import requests

from services.email_service import EmailDeliveryError, SENDER_TRANSACTIONAL_ENDPOINT, send_email


class _Response:
    def __init__(self, status_code=202):
        self.status_code = status_code


def test_sender_rest_api_payload_and_authorization(app, monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return _Response(202)

    monkeypatch.setattr("services.email_service.requests.post", fake_post)
    with app.app_context():
        app.config.update(
            MAIL_PROVIDER="sender",
            MAIL_FROM_NAME="V-SPACE",
            SENDER_API_TOKEN="secret-sender-token",
            SENDER_FROM_EMAIL="security@example.com",
            SENDER_TIMEOUT_SECONDS=12,
        )
        assert send_email(
            "student@example.com",
            "Verify your account",
            "Plain body",
            html_body="<p>Plain body</p>",
        ) is True

    assert captured["url"] == SENDER_TRANSACTIONAL_ENDPOINT
    assert captured["headers"]["Authorization"] == "Bearer secret-sender-token"
    assert captured["timeout"] == 12
    assert captured["json"] == {
        "from": {"email": "security@example.com", "name": "V-SPACE"},
        "to": {"email": "student@example.com"},
        "subject": "Verify your account",
        "text": "Plain body",
        "html": "<p>Plain body</p>",
    }


def test_sender_failure_does_not_expose_response_body(app, monkeypatch):
    monkeypatch.setattr("services.email_service.requests.post", lambda *a, **k: _Response(401))
    with app.app_context():
        app.config.update(
            MAIL_PROVIDER="sender",
            SENDER_API_TOKEN="bad-token",
            SENDER_FROM_EMAIL="security@example.com",
        )
        with pytest.raises(EmailDeliveryError, match="HTTP 401"):
            send_email("student@example.com", "Reset", "Reset body")


def test_sender_transport_error_is_wrapped(app, monkeypatch):
    def fail(*args, **kwargs):
        raise requests.Timeout("provider timeout")

    monkeypatch.setattr("services.email_service.requests.post", fail)
    with app.app_context():
        app.config.update(
            MAIL_PROVIDER="sender",
            SENDER_API_TOKEN="sender-token",
            SENDER_FROM_EMAIL="security@example.com",
        )
        with pytest.raises(EmailDeliveryError, match="could not be reached"):
            send_email("student@example.com", "Reset", "Reset body")


def test_smtp_provider_uses_starttls_login_and_message(app, monkeypatch):
    captured = {}

    class FakeSMTP:
        def __init__(self, server, port, timeout):
            captured.update(server=server, port=port, timeout=timeout)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def ehlo(self):
            captured["ehlo"] = captured.get("ehlo", 0) + 1

        def starttls(self, context=None):
            captured["starttls"] = context is not None

        def login(self, username, password):
            captured["login"] = (username, password)

        def send_message(self, message):
            captured["message"] = message

    monkeypatch.setattr("services.email_service.smtplib.SMTP", FakeSMTP)
    with app.app_context():
        app.config.update(
            MAIL_PROVIDER="smtp",
            MAIL_FROM_NAME="V-SPACE",
            MAIL_SERVER="smtp.gmail.com",
            MAIL_PORT=587,
            MAIL_USE_TLS=True,
            MAIL_USERNAME="dev@example.com",
            MAIL_PASSWORD="app-password",
            MAIL_DEFAULT_SENDER="dev@example.com",
            MAIL_TIMEOUT_SECONDS=9,
        )
        assert send_email(
            "student@example.com",
            "Verify your account",
            "Plain body",
            html_body="<p>Plain body</p>",
        ) is True

    assert captured["server"] == "smtp.gmail.com"
    assert captured["port"] == 587
    assert captured["timeout"] == 9
    assert captured["starttls"] is True
    assert captured["login"] == ("dev@example.com", "app-password")
    message = captured["message"]
    assert message["To"] == "student@example.com"
    assert message["Subject"] == "Verify your account"
    assert "V-SPACE" in message["From"]


def test_smtp_transport_error_is_wrapped(app, monkeypatch):
    class FailingSMTP:
        def __init__(self, *args, **kwargs):
            raise OSError("network unavailable")

    monkeypatch.setattr("services.email_service.smtplib.SMTP", FailingSMTP)
    with app.app_context():
        app.config.update(
            MAIL_PROVIDER="smtp",
            MAIL_SERVER="smtp.gmail.com",
            MAIL_PORT=587,
            MAIL_USE_TLS=True,
            MAIL_USERNAME="dev@example.com",
            MAIL_PASSWORD="app-password",
            MAIL_DEFAULT_SENDER="dev@example.com",
        )
        with pytest.raises(EmailDeliveryError, match="SMTP could not deliver"):
            send_email("student@example.com", "Reset", "Reset body")


def test_unknown_provider_fails_closed(app):
    with app.app_context():
        app.config["MAIL_PROVIDER"] = "unknown"
        with pytest.raises(EmailDeliveryError, match="Unsupported MAIL_PROVIDER"):
            send_email("student@example.com", "Reset", "Reset body")
