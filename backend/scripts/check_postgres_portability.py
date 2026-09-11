"""Static guard for new SQL Server-specific code.

The existing historical Alembic revisions are allowed because they describe the
legacy SQL Server database. New application code and new migrations should be
portable PostgreSQL/SQLAlchemy code.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN = {
    r"sqlalchemy\.dialects\.mssql": "mssql dialect import",
    r"\bmssql\+pyodbc\b": "SQL Server connection URL",
    r"\bsysutcdatetime\s*\(": "SQL Server sysutcdatetime()",
    r"\bgetdate\s*\(": "SQL Server getdate()",
    r"\bNVARCHAR\b": "SQL Server-specific NVARCHAR text",
}

ALLOWED_PATH_PREFIXES = {
    Path("migrations/versions"),
    Path("sql"),  # historical SQL Server setup/manual scripts
    Path("requirements-legacy-sqlserver.txt"),
    Path("lifeos/core/database.py"),
    Path("scripts/check_postgres_portability.py"),
}


def allowed(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    return any(prefix == relative or prefix in relative.parents for prefix in ALLOWED_PATH_PREFIXES)


def main() -> int:
    failures = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in {".py", ".sql", ".txt"}:
            continue
        if allowed(path):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern, label in FORBIDDEN.items():
            if re.search(pattern, text, flags=re.IGNORECASE):
                failures.append((path.relative_to(ROOT), label))

    if failures:
        print("PostgreSQL portability violations:")
        for path, label in failures:
            print(f"- {path}: {label}")
        return 1

    print("PostgreSQL portability guard: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
