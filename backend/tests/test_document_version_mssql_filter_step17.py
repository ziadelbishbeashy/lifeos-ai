"""Regression guard for SQL Server boolean filtering used by collections."""

from sqlalchemy.dialects import mssql

from services.document_version_service import current_document_filter


def test_current_document_filter_uses_valid_mssql_bit_comparison():
    sql = str(
        current_document_filter().compile(
            dialect=mssql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).upper()

    assert " IS 1" not in sql
    assert "IS_CURRENT_VERSION = 1" in sql
