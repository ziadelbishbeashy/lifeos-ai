from pathlib import Path


def test_i16_migration_extends_i15_head_with_memory_table():
    path = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "20260829_0004_add_structured_memory.py"
    text = path.read_text(encoding="utf-8")
    assert 'revision = "20260829_0004"' in text
    assert 'down_revision = "20260829_0003"' in text
    assert '"lifeos_memories"' in text
    assert '"user_confirmed"' in text
