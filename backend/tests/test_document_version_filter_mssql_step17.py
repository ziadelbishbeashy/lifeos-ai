"""Regression test for SQL Server boolean syntax used by Step 17 collections."""

from sqlalchemy.dialects import mssql

from services.document_version_service import current_document_filter


def test_current_document_filter_uses_sql_server_compatible_boolean_comparison():
    sql = str(
        current_document_filter().compile(
            dialect=mssql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).upper()

    # MSSQL BIT columns must be compared with = 1; ``IS 1`` is invalid SQL.
    assert "IS 1" not in sql
    assert "IS_CURRENT_VERSION = 1" in sql
