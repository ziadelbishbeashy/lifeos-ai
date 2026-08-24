"""Local storage foundation tests."""

from io import BytesIO

from storage.local import LocalStorage


def test_local_storage_round_trip(tmp_path):
    storage = LocalStorage(tmp_path)
    key = storage.save(
        BytesIO(b"LifeOS document"),
        original_name="lecture notes.pdf",
        namespace="user-1",
    )
    assert storage.exists(key)
    with storage.open(key, "rb") as stored:
        assert stored.read() == b"LifeOS document"
    storage.delete(key)
    assert not storage.exists(key)
