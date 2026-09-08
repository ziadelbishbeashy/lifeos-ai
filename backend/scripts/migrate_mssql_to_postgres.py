"""One-time LifeOS SQL Server -> PostgreSQL/Neon data migration.

Design goals:
- SQL Server is source-only; this script never issues DDL/DML to the source.
- PostgreSQL target must already contain the current LifeOS schema and be empty.
- Explicit primary keys are preserved so all existing relationships remain stable.
- Inserts are ordered by PostgreSQL foreign-key dependencies.
- The whole target copy runs in one transaction and rolls back on any failure.
- PostgreSQL sequences are reset after explicit-ID inserts.
- Row counts and foreign keys are verified before commit and can be re-verified later.
- Transient AI operation locks are intentionally not migrated.

Typical usage from backend/:

    py -3.11 scripts/migrate_mssql_to_postgres.py preflight
    py -3.11 scripts/migrate_mssql_to_postgres.py migrate
    py -3.11 scripts/migrate_mssql_to_postgres.py verify

Credentials stay in backend/.env. See the migration variables documented in
.env.example and PATCH_MANIFEST_MSSQL_TO_NEON_DATA_MIGRATION.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import Boolean, Integer, MetaData, Table, and_, create_engine, exists, func, select, text
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.exc import SQLAlchemyError


BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")

EXPECTED_ALEMBIC_HEAD = "20260906_0001"
SOURCE_SCHEMA = "dbo"
TARGET_SCHEMA = "public"
SKIP_TABLES = {
    "alembic_version",      # target migration marker is already established
    "ai_operation_locks",   # ephemeral cross-worker locks must never survive a DB cutover
}


class MigrationError(RuntimeError):
    """Raised for a migration safety or integrity failure."""


@dataclass
class TablePlan:
    name: str
    source_rows: int
    target_rows_before: int
    common_columns: list[str]
    source_only_columns: list[str] = field(default_factory=list)
    target_only_columns: list[str] = field(default_factory=list)


@dataclass
class MigrationReport:
    mode: str
    started_at_utc: str
    finished_at_utc: str | None = None
    expected_alembic_head: str = EXPECTED_ALEMBIC_HEAD
    source_database_family: str = "mssql"
    target_database_family: str = "postgresql"
    skipped_tables: list[str] = field(default_factory=lambda: sorted(SKIP_TABLES))
    table_order: list[str] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    inserted_rows: dict[str, int] = field(default_factory=dict)
    row_count_verification: dict[str, dict[str, int]] = field(default_factory=dict)
    foreign_key_violations: list[dict[str, Any]] = field(default_factory=list)
    sequences_reset: list[dict[str, Any]] = field(default_factory=list)
    success: bool = False


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_postgres_url(value: str) -> str:
    url = str(value or "").strip()
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _build_source_url() -> str:
    explicit = str(os.getenv("MIGRATION_MSSQL_URL") or "").strip()
    if explicit:
        return explicit

    server = str(os.getenv("MIGRATION_MSSQL_SERVER") or os.getenv("DB_SERVER") or "").strip()
    database = str(os.getenv("MIGRATION_MSSQL_DATABASE") or os.getenv("DB_NAME") or "").strip()
    driver = str(
        os.getenv("MIGRATION_MSSQL_DRIVER")
        or os.getenv("DB_DRIVER")
        or "ODBC Driver 17 for SQL Server"
    ).strip()
    username = str(os.getenv("MIGRATION_MSSQL_USERNAME") or os.getenv("DB_USERNAME") or "").strip()
    password = os.getenv("MIGRATION_MSSQL_PASSWORD")
    if password is None:
        password = os.getenv("DB_PASSWORD") or ""

    if not server or not database:
        raise MigrationError(
            "SQL Server source is not configured. Set MIGRATION_MSSQL_SERVER and "
            "MIGRATION_MSSQL_DATABASE (plus credentials when required), or set MIGRATION_MSSQL_URL."
        )

    if username:
        authentication = f"UID={username};PWD={password};"
    else:
        authentication = "Trusted_Connection=yes;"

    encrypt = _env_bool("MIGRATION_MSSQL_ENCRYPT", _env_bool("DB_ENCRYPT", True))
    trust_certificate = _env_bool(
        "MIGRATION_MSSQL_TRUST_SERVER_CERTIFICATE",
        _env_bool("DB_TRUST_SERVER_CERTIFICATE", True),
    )

    connection_string = (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"{authentication}"
        f"Encrypt={'yes' if encrypt else 'no'};"
        f"TrustServerCertificate={'yes' if trust_certificate else 'no'};"
    )
    return "mssql+pyodbc:///?odbc_connect=" + quote_plus(connection_string)


def _build_target_url() -> str:
    raw = str(
        os.getenv("MIGRATION_POSTGRES_URL")
        or os.getenv("DATABASE_DIRECT_URL")
        or ""
    ).strip()
    if not raw:
        raise MigrationError(
            "PostgreSQL target is not configured. Set DATABASE_DIRECT_URL to the direct "
            "Neon connection string (connection pooling OFF), or set MIGRATION_POSTGRES_URL."
        )
    return _normalize_postgres_url(raw)


def _redacted_url(value: str) -> str:
    try:
        url = make_url(value)
        return url.render_as_string(hide_password=True)
    except Exception:
        return "<configured>"


def _validate_engine_urls(source_url: str, target_url: str) -> None:
    source = make_url(source_url)
    target = make_url(target_url)

    if not source.drivername.startswith("mssql"):
        raise MigrationError("Migration source must be SQL Server (mssql+pyodbc).")
    if not target.drivername.startswith("postgresql"):
        raise MigrationError("Migration target must be PostgreSQL/Neon.")

    target_host = str(target.host or "").casefold()
    if "-pooler" in target_host:
        raise MigrationError(
            "Use Neon's direct connection for the migration. DATABASE_DIRECT_URL must be the "
            "connection-pooling-OFF URL, not a -pooler host."
        )

    sslmode = str(target.query.get("sslmode") or "").casefold()
    if sslmode not in {"require", "verify-ca", "verify-full"}:
        raise MigrationError(
            "PostgreSQL migration target must use TLS (sslmode=require, verify-ca, or verify-full)."
        )


def _create_engines() -> tuple[Engine, Engine]:
    source_url = _build_source_url()
    target_url = _build_target_url()
    _validate_engine_urls(source_url, target_url)

    print(f"Source: {_redacted_url(source_url)}")
    print(f"Target: {_redacted_url(target_url)}")

    source_engine = create_engine(source_url, future=True, pool_pre_ping=True)
    target_engine = create_engine(target_url, future=True, pool_pre_ping=True)
    return source_engine, target_engine


def _reflect(connection: Connection, schema: str) -> dict[str, Table]:
    metadata = MetaData()
    metadata.reflect(bind=connection, schema=schema)
    return {table.name: table for table in metadata.tables.values()}


def _count_rows(connection: Connection, table: Table) -> int:
    return int(connection.execute(select(func.count()).select_from(table)).scalar_one())


def _check_alembic_head(target: Connection, target_tables: dict[str, Table]) -> None:
    table = target_tables.get("alembic_version")
    if table is None:
        raise MigrationError(
            "Target alembic_version table is missing. Establish the Neon baseline before migrating data."
        )
    versions = [str(row[0]) for row in target.execute(select(table.c.version_num)).all()]
    if versions != [EXPECTED_ALEMBIC_HEAD]:
        raise MigrationError(
            f"Target Alembic version must be exactly {EXPECTED_ALEMBIC_HEAD}; found {versions or 'empty'}."
        )


def _required_target_only_columns(table: Table, source_column_names: set[str]) -> list[str]:
    required: list[str] = []
    for column in table.columns:
        if column.name in source_column_names:
            continue
        if column.primary_key and bool(column.autoincrement):
            continue
        if column.nullable:
            continue
        if column.server_default is not None or column.default is not None:
            continue
        required.append(column.name)
    return required


def _table_plan(source: Connection, target: Connection, source_table: Table, target_table: Table) -> TablePlan:
    source_names = {column.name for column in source_table.columns}
    target_names = {column.name for column in target_table.columns}
    common = [column.name for column in target_table.columns if column.name in source_names]
    missing_required = _required_target_only_columns(target_table, source_names)
    if missing_required:
        raise MigrationError(
            f"Table {target_table.name} is missing required source columns: {', '.join(missing_required)}"
        )
    return TablePlan(
        name=target_table.name,
        source_rows=_count_rows(source, source_table),
        target_rows_before=_count_rows(target, target_table),
        common_columns=common,
        source_only_columns=sorted(source_names - target_names),
        target_only_columns=sorted(target_names - source_names),
    )


def _topological_order(tables: dict[str, Table], selected_names: Iterable[str]) -> list[str]:
    selected = set(selected_names)
    dependencies: dict[str, set[str]] = {name: set() for name in selected}
    children: dict[str, set[str]] = defaultdict(set)

    for name in selected:
        table = tables[name]
        for fk in table.foreign_key_constraints:
            parent_name = fk.referred_table.name
            if parent_name in selected and parent_name != name:
                dependencies[name].add(parent_name)
                children[parent_name].add(name)

    queue = deque(sorted(name for name, deps in dependencies.items() if not deps))
    result: list[str] = []
    while queue:
        current = queue.popleft()
        result.append(current)
        for child in sorted(children.get(current, ())):
            dependencies[child].discard(current)
            if not dependencies[child]:
                queue.append(child)

    if len(result) != len(selected):
        cyclic = sorted(name for name, deps in dependencies.items() if deps)
        detail = "; ".join(f"{name}->{sorted(dependencies[name])}" for name in cyclic)
        raise MigrationError(
            "Cross-table foreign-key cycle detected; migration will not disable constraints automatically. "
            f"Cycle/dependencies: {detail}"
        )
    return result


def _normalize_value(value: Any, target_column) -> Any:
    if value is None:
        return None
    if isinstance(value, memoryview):
        value = bytes(value)
    if isinstance(target_column.type, Boolean) and isinstance(value, (bool, int)):
        return bool(value)
    return value


def _copy_table(
    source: Connection,
    target: Connection,
    source_table: Table,
    target_table: Table,
    common_columns: list[str],
    *,
    batch_size: int,
) -> int:
    if not common_columns:
        return 0

    source_columns = [source_table.c[name] for name in common_columns]
    target_columns = {name: target_table.c[name] for name in common_columns}
    result = source.execution_options(stream_results=True).execute(select(*source_columns)).mappings()

    inserted = 0
    while True:
        batch = result.fetchmany(batch_size)
        if not batch:
            break
        payload: list[dict[str, Any]] = []
        for row in batch:
            payload.append(
                {
                    name: _normalize_value(row[name], target_columns[name])
                    for name in common_columns
                }
            )
        target.execute(target_table.insert(), payload)
        inserted += len(payload)
    return inserted


def _reset_sequences(target: Connection, target_tables: dict[str, Table], names: Iterable[str]) -> list[dict[str, Any]]:
    reset: list[dict[str, Any]] = []
    for name in names:
        table = target_tables[name]
        pk_columns = list(table.primary_key.columns)
        if len(pk_columns) != 1:
            continue
        pk = pk_columns[0]
        if not isinstance(pk.type, Integer):
            continue

        schema_table = f"{TARGET_SCHEMA}.{table.name}"
        sequence_name = target.execute(
            text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
            {"table_name": schema_table, "column_name": pk.name},
        ).scalar_one_or_none()
        if not sequence_name:
            continue

        max_value = target.execute(select(func.max(pk))).scalar_one_or_none()
        if max_value is None:
            target.execute(
                text("SELECT setval(CAST(:sequence_name AS regclass), 1, false)"),
                {"sequence_name": sequence_name},
            )
            reset.append({"table": name, "column": pk.name, "max": None})
        else:
            target.execute(
                text("SELECT setval(CAST(:sequence_name AS regclass), :value, true)"),
                {"sequence_name": sequence_name, "value": int(max_value)},
            )
            reset.append({"table": name, "column": pk.name, "max": int(max_value)})
    return reset


def _foreign_key_violations(
    target: Connection,
    target_tables: dict[str, Table],
    names: Iterable[str],
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    selected = set(names)

    for name in names:
        child = target_tables[name]
        for fk in child.foreign_key_constraints:
            parent = fk.referred_table
            if parent.name not in selected and parent.name not in target_tables:
                continue

            pairs = list(fk.elements)
            local_columns = [element.parent for element in pairs]
            remote_columns = [element.column for element in pairs]
            if not local_columns:
                continue

            parent_alias = parent.alias(f"fk_parent_{name}_{len(violations)}")
            equality = and_(
                *[
                    parent_alias.c[remote.name] == local
                    for local, remote in zip(local_columns, remote_columns)
                ]
            )
            local_has_value = and_(*[local.is_not(None) for local in local_columns])
            missing_parent = ~exists(select(1).select_from(parent_alias).where(equality))
            count = int(
                target.execute(
                    select(func.count()).select_from(child).where(local_has_value, missing_parent)
                ).scalar_one()
            )
            if count:
                violations.append(
                    {
                        "table": name,
                        "constraint": fk.name,
                        "parent_table": parent.name,
                        "rows": count,
                        "columns": [column.name for column in local_columns],
                    }
                )
    return violations


def _preflight_connections(source: Connection, target: Connection, report: MigrationReport) -> tuple[dict[str, Table], dict[str, Table], list[TablePlan]]:
    source_tables = _reflect(source, SOURCE_SCHEMA)
    target_tables = _reflect(target, TARGET_SCHEMA)
    _check_alembic_head(target, target_tables)

    target_app_names = sorted(set(target_tables) - SKIP_TABLES)
    missing_source = sorted(name for name in target_app_names if name not in source_tables)
    if missing_source:
        raise MigrationError(
            "SQL Server source is missing current LifeOS tables: " + ", ".join(missing_source)
        )

    extra_source = sorted(set(source_tables) - set(target_tables))
    if extra_source:
        report.warnings.append(
            "Source-only tables are not part of the current PostgreSQL schema and will not be copied: "
            + ", ".join(extra_source)
        )

    plans: list[TablePlan] = []
    for name in target_app_names:
        plan = _table_plan(source, target, source_tables[name], target_tables[name])
        if plan.target_rows_before:
            raise MigrationError(
                f"Target is not empty: {name} already contains {plan.target_rows_before} row(s). "
                "This tool intentionally does not merge, overwrite, or delete target data."
            )
        if plan.source_only_columns:
            report.warnings.append(
                f"{name}: source-only columns ignored: {', '.join(plan.source_only_columns)}"
            )
        if plan.target_only_columns:
            report.warnings.append(
                f"{name}: target-only columns use model/default/null behavior: {', '.join(plan.target_only_columns)}"
            )
        plans.append(plan)

    report.table_order = _topological_order(target_tables, target_app_names)
    report.tables = [asdict(plan) for plan in plans]
    return source_tables, target_tables, plans


def _verify_counts(
    source: Connection,
    target: Connection,
    source_tables: dict[str, Table],
    target_tables: dict[str, Table],
    names: Iterable[str],
) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    mismatches: list[str] = []
    for name in names:
        source_count = _count_rows(source, source_tables[name])
        target_count = _count_rows(target, target_tables[name])
        result[name] = {"source": source_count, "target": target_count}
        if source_count != target_count:
            mismatches.append(f"{name}: source={source_count}, target={target_count}")
    if mismatches:
        raise MigrationError("Row-count verification failed: " + "; ".join(mismatches))
    return result


def _write_report(report: MigrationReport, requested_path: str | None) -> Path:
    reports_dir = BACKEND_DIR / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    if requested_path:
        path = Path(requested_path)
        if not path.is_absolute():
            path = BACKEND_DIR / path
    else:
        stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        path = reports_dir / f"mssql_to_postgres_migration_{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(report), indent=2, default=str), encoding="utf-8")
    return path


def run_preflight(source_engine: Engine, target_engine: Engine, report: MigrationReport) -> None:
    with source_engine.connect() as source, target_engine.connect() as target:
        _, _, plans = _preflight_connections(source, target, report)
        source_total = sum(plan.source_rows for plan in plans)
        print(f"Preflight OK: {len(plans)} persistent LifeOS tables, {source_total} source rows.")
        if report.warnings:
            print(f"Warnings: {len(report.warnings)} (see report).")


def run_migration(source_engine: Engine, target_engine: Engine, report: MigrationReport, *, batch_size: int) -> None:
    with source_engine.connect() as source:
        # One PostgreSQL transaction: any copy/integrity failure rolls the target back to empty.
        with target_engine.begin() as target:
            source_tables, target_tables, plans = _preflight_connections(source, target, report)
            plans_by_name = {plan.name: plan for plan in plans}

            print(f"Copying {len(report.table_order)} tables in FK-safe order...")
            for index, name in enumerate(report.table_order, start=1):
                plan = plans_by_name[name]
                inserted = _copy_table(
                    source,
                    target,
                    source_tables[name],
                    target_tables[name],
                    plan.common_columns,
                    batch_size=batch_size,
                )
                report.inserted_rows[name] = inserted
                print(f"[{index:02d}/{len(report.table_order):02d}] {name}: {inserted} row(s)")

            report.sequences_reset = _reset_sequences(target, target_tables, report.table_order)
            report.row_count_verification = _verify_counts(
                source,
                target,
                source_tables,
                target_tables,
                report.table_order,
            )
            report.foreign_key_violations = _foreign_key_violations(
                target,
                target_tables,
                report.table_order,
            )
            if report.foreign_key_violations:
                raise MigrationError(
                    "Foreign-key integrity verification failed; target transaction will be rolled back."
                )

    print("Migration transaction committed successfully.")


def run_verify(source_engine: Engine, target_engine: Engine, report: MigrationReport) -> None:
    with source_engine.connect() as source, target_engine.connect() as target:
        source_tables = _reflect(source, SOURCE_SCHEMA)
        target_tables = _reflect(target, TARGET_SCHEMA)
        _check_alembic_head(target, target_tables)

        names = sorted((set(target_tables) - SKIP_TABLES) & set(source_tables))
        report.table_order = _topological_order(target_tables, names)
        report.row_count_verification = _verify_counts(
            source,
            target,
            source_tables,
            target_tables,
            report.table_order,
        )
        report.foreign_key_violations = _foreign_key_violations(
            target,
            target_tables,
            report.table_order,
        )
        if report.foreign_key_violations:
            raise MigrationError("Foreign-key integrity verification failed.")
        print(f"Verification OK: {len(report.table_order)} tables match source row counts; no orphaned FKs found.")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safely migrate existing LifeOS data from SQL Server to PostgreSQL/Neon."
    )
    parser.add_argument("mode", choices=("preflight", "migrate", "verify"))
    parser.add_argument("--batch-size", type=int, default=500, help="Rows per INSERT batch (default: 500).")
    parser.add_argument("--report", help="Optional report path relative to backend/, or an absolute path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(argv or sys.argv[1:]))
    if args.batch_size < 1 or args.batch_size > 10_000:
        print("ERROR: --batch-size must be between 1 and 10000.", file=sys.stderr)
        return 2

    report = MigrationReport(mode=args.mode, started_at_utc=datetime.utcnow().isoformat() + "Z")
    source_engine: Engine | None = None
    target_engine: Engine | None = None
    exit_code = 0

    try:
        source_engine, target_engine = _create_engines()
        if args.mode == "preflight":
            run_preflight(source_engine, target_engine, report)
        elif args.mode == "migrate":
            run_migration(source_engine, target_engine, report, batch_size=args.batch_size)
        else:
            run_verify(source_engine, target_engine, report)
        report.success = True
    except (MigrationError, SQLAlchemyError) as exc:
        exit_code = 1
        report.warnings.append(f"FAILED: {type(exc).__name__}: {exc}")
        print(f"ERROR: {exc}", file=sys.stderr)
    finally:
        report.finished_at_utc = datetime.utcnow().isoformat() + "Z"
        try:
            report_path = _write_report(report, args.report)
            print(f"Report: {report_path}")
        except Exception as report_error:
            print(f"WARNING: could not write migration report: {report_error}", file=sys.stderr)
        if source_engine is not None:
            source_engine.dispose()
        if target_engine is not None:
            target_engine.dispose()

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
