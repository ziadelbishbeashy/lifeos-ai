"""Focus domain-service tests."""

import pytest

from services.focus_service import (
    FocusConflictError,
    cancel_session,
    start_session,
)


def test_only_one_active_focus_session_is_allowed(app, user):
    with app.app_context():
        session = start_session(user, None, 25, "First session")
        with pytest.raises(FocusConflictError):
            start_session(user, None, 25, "Second session")
        cancel_session(session)
