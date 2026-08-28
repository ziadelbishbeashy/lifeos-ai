"""Step 15 OCR migration contract."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "versions" / "20260826_0001_add_document_ocr_state.py"


def test_ocr_migration_follows_document_versioning():
    text = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260826_0001"' in text
    assert 'down_revision = "20260811_0002"' in text
    assert "ocr_status" in text
    assert "ocr_pages_requested" in text
    assert "ocr_average_confidence" in text

LAYOUT_MIGRATION = ROOT / "migrations" / "versions" / "20260826_0002_add_document_ocr_layout.py"


def test_ocr_layout_migration_follows_ocr_state_migration():
    text = LAYOUT_MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260826_0002"' in text
    assert 'down_revision = "20260826_0001"' in text
    assert "ocr_layout_json" in text

QUALITY_MIGRATION = ROOT / "migrations" / "versions" / "20260827_0001_add_document_ocr_quality_metrics.py"


def test_ocr_quality_migration_follows_layout_migration():
    text = QUALITY_MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260827_0001"' in text
    assert 'down_revision = "20260826_0002"' in text
    assert "ocr_total_characters" in text
    assert "ocr_total_words" in text
    assert "ocr_quality" in text
