"""CSV exports must not create spreadsheet formulas from user input."""

from services.export_service import build_csv, safe_csv_value


def test_dangerous_csv_values_are_escaped():
    assert safe_csv_value("=SUM(A1:A2)") == "'=SUM(A1:A2)"
    assert safe_csv_value("Normal title") == "Normal title"


def test_csv_builder_escapes_rows():
    content = build_csv(
        [{"title": "=1+1", "status": "Pending"}],
        ["title", "status"],
    )
    assert "'=1+1" in content
