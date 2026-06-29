"""Canonical Wealthfolio CSV schema, reader and writer.

The schema mirrors Wealthfolio's "Import Activities" wizard format, plus
an extra `account` column that the orchestrator fills in from
wf-config.yml. The WF UI wizard ignores unknown columns, so the same
file is still usable as a fallback manual import.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

# Required keys returned by every adapter's `convert()` (no `account`).
ADAPTER_REQUIRED_KEYS = (
    "date",
    "symbol",
    "instrumentType",
    "quantity",
    "activityType",
    "unitPrice",
    "currency",
    "fee",
    "amount",
)

# Final WF CSV columns written to disk (adds `account`).
WF_CSV_HEADER = (*ADAPTER_REQUIRED_KEYS, "account")

ALLOWED_ACTIVITY_TYPES = frozenset(
    {"BUY", "SELL", "DEPOSIT", "WITHDRAWAL", "DIVIDEND", "INTEREST", "FEE", "TAX"}
)

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


class AdapterOutputError(ValueError):
    """Raised when an adapter's output does not satisfy the WF schema."""


def validate_adapter_row(row: dict[str, Any], *, line: int, adapter: str) -> None:
    """Check a single row coming out of an adapter. Raise on first error.

    line and adapter are used to build a human-readable error pointing at
    the offending output row.
    """
    where = f"{adapter} row {line}"

    missing = [k for k in ADAPTER_REQUIRED_KEYS if k not in row]
    if missing:
        raise AdapterOutputError(f"{where}: missing keys {missing}")

    date = row["date"]
    if not isinstance(date, str):
        raise AdapterOutputError(f"{where}: date must be str, got {type(date).__name__}")
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError as exc:
        raise AdapterOutputError(f"{where}: date '{date}' is not ISO YYYY-MM-DD") from exc

    activity_type = row["activityType"]
    if activity_type not in ALLOWED_ACTIVITY_TYPES:
        raise AdapterOutputError(
            f"{where}: activityType '{activity_type}' not in {sorted(ALLOWED_ACTIVITY_TYPES)}"
        )

    currency = row["currency"]
    if not isinstance(currency, str) or not _CURRENCY_RE.match(currency):
        raise AdapterOutputError(f"{where}: currency '{currency}' must be 3 uppercase letters")

    for numeric_key in ("quantity", "unitPrice", "fee"):
        value = row[numeric_key]
        if not isinstance(value, (int, float)):
            raise AdapterOutputError(
                f"{where}: {numeric_key} must be a number, got {type(value).__name__}"
            )
        if value != value:  # NaN check
            raise AdapterOutputError(f"{where}: {numeric_key} is NaN")

    amount = row["amount"]
    if amount is not None and not isinstance(amount, (int, float)):
        raise AdapterOutputError(
            f"{where}: amount must be a number or None, got {type(amount).__name__}"
        )

    symbol = row["symbol"]
    if not isinstance(symbol, str):
        raise AdapterOutputError(f"{where}: symbol must be str, got {type(symbol).__name__}")


def validate_adapter_output(rows: list[dict[str, Any]], *, adapter: str) -> None:
    """Validate every row in an adapter's output. Raise on first error."""
    if not isinstance(rows, list):
        raise AdapterOutputError(f"{adapter}: convert() must return a list, got {type(rows).__name__}")
    if not rows:
        raise AdapterOutputError(f"{adapter}: convert() returned an empty list")
    for i, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise AdapterOutputError(f"{adapter} row {i}: not a dict ({type(row).__name__})")
        validate_adapter_row(row, line=i, adapter=adapter)


def _format_cell(value: Any) -> str:
    """Render a value for the CSV. None becomes empty string."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def write(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    """Write rows to a WF CSV file. Every row must already have `account`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(WF_CSV_HEADER)
        for row in rows:
            writer.writerow([_format_cell(row.get(col)) for col in WF_CSV_HEADER])


def read(path: Path) -> list[dict[str, Any]]:
    """Read a WF CSV back into a list of dicts. Numeric fields are coerced."""
    out: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            parsed = dict(row)
            for numeric_key in ("quantity", "unitPrice", "fee"):
                parsed[numeric_key] = float(row[numeric_key]) if row.get(numeric_key) else 0.0
            parsed["amount"] = float(row["amount"]) if row.get("amount") else None
            out.append(parsed)
    return out
