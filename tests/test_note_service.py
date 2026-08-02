"""Notes domain-service tests."""

import pytest

from database import db
from models import Note
from services.note_service import (
    NoteValidationError,
    build_note_input,
    create_note,
    delete_note,
    list_notes,
    toggle_note_pin,
)


def test_note_input_requires_title(app, user):
    with app.app_context():
        data = build_note_input(
            {
                "title": " ",
                "content": "content",
                "note_type": "Quick Note",
            },
            user,
        )
        with pytest.raises(NoteValidationError):
            create_note(user, data)


def test_note_service_create_pin_list_and_delete(app, user):
    with app.app_context():
        data = build_note_input(
            {
                "title": "Service note",
                "content": "Created through the domain service.",
                "note_type": "Quick Note",
            },
            user,
        )
        note = create_note(user, data)
        assert note.id is not None
        assert toggle_note_pin(note) is True

        result = list_notes(user)
        assert [item.id for item in result.pinned_notes] == [note.id]

        note_id = note.id
        title = delete_note(note)
        assert title == "Service note"
        assert db.session.get(Note, note_id) is None
