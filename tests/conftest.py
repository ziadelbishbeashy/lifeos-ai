"""Shared pytest fixtures for LifeOS."""

from __future__ import annotations

import pytest

from app import create_app
from database import db
from models import User


@pytest.fixture()
def app():
    application = create_app(
        "testing",
        {
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "WTF_CSRF_ENABLED": False,
        },
    )

    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def user(app):
    with app.app_context():
        account = User(name="Test Student", email="student@example.com")
        account.set_password("StrongPass123!")
        db.session.add(account)
        db.session.commit()
        return account.id
