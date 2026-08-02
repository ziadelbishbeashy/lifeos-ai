"""CSV export helpers with spreadsheet-formula injection protection."""

from __future__ import annotations

import csv
import io
from typing import Iterable, Mapping, Any


DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def safe_csv_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if value.startswith(DANGEROUS_PREFIXES):
        return "'" + value
    return value


def build_csv(
    rows: Iterable[Mapping[str, Any]],
    fieldnames: list[str],
) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=fieldnames,
        extrasaction="ignore",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {key: safe_csv_value(value) for key, value in row.items()}
        )
    return output.getvalue()
