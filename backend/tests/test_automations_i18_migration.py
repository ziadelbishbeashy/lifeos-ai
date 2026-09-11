from pathlib import Path


def test_i18_visual_flow_migration_is_linear_and_additive():
    path = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "20260830_0002_add_visual_flow_metadata.py"
    text = path.read_text(encoding="utf-8")
    assert 'revision = "20260830_0002"' in text
    assert 'down_revision = "20260830_0001"' in text
    assert '"visual_graph_json"' in text
    assert 'op.add_column(' in text
    assert 'op.create_table(' not in text
