"""Pipeline that turns a broker file into a final WF CSV.

    broker file
       │
       ▼
    [select adapter]      -- explicit --broker or detect() match
       │
       ▼
    [adapter.convert()]   -- returns list[dict], no `account` key yet
       │
       ▼
    [validate schema]     -- wf_csv.validate_adapter_output
       │
       ▼
    [apply grouping]      -- set `account` based on wealthfolio-importer-config.yml
       │
       ▼
    [auto-deposit]        -- if adapter says so and not overridden;
                             each synthetic DEPOSIT inherits its BUY's
                             account so funds land in the right place
       │
       ▼
    [stable sort by date] -- DEPOSITs precede same-date BUYs
       │
       ▼
    [write CSV]
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from . import adapters as adapters_pkg
from . import wf_csv
from .config import AccountsConfig


@dataclass(frozen=True)
class ConvertSummary:
    output_paths: dict[str, Path]   # account name -> file path
    adapter_name: str
    row_count: int
    deposits_injected: int
    by_account: dict[str, int]


_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def _safe_account_filename(account: str) -> str:
    """Sanitise an account name for use in a filename."""
    cleaned = _UNSAFE_FILENAME_CHARS.sub("_", account.strip())
    return cleaned or "unnamed"


def _inject_synthetic_deposits(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Prepend a DEPOSIT row before each BUY row of equal cost.

    Each synthetic DEPOSIT copies the BUY's `account` if present, so
    the cash lands in the right Wealthfolio account. Must run AFTER
    grouping.
    """
    out: list[dict[str, Any]] = []
    injected = 0
    for row in rows:
        if row["activityType"] == "BUY":
            cost = round(row["quantity"] * row["unitPrice"], 2)
            deposit = {
                "date": row["date"],
                "symbol": "",
                "instrumentType": "",
                "quantity": 1,
                "activityType": "DEPOSIT",
                "unitPrice": 1,
                "currency": row["currency"],
                "fee": 0,
                "amount": cost,
            }
            if "account" in row:
                deposit["account"] = row["account"]
            out.append(deposit)
            injected += 1
        out.append(row)
    return out, injected


def _apply_ticker_map(rows: list[dict[str, Any]], ticker_map: dict[str, str]) -> None:
    """Remap broker tickers to their canonical symbols in place."""
    for row in rows:
        row["symbol"] = ticker_map.get(row["symbol"], row["symbol"])


def _apply_grouping(rows: list[dict[str, Any]], accounts: AccountsConfig) -> None:
    """Set the `account` key on each row in place, based on symbol rules."""
    for row in rows:
        row["account"] = accounts.assign(row.get("symbol", ""))


def _sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable sort by date. DEPOSITs precede same-date BUYs because they
    were prepended; Python's sort is stable, so ties preserve order.
    """
    return sorted(rows, key=lambda r: r["date"])


def convert(
    *,
    input_path: Path,
    accounts: AccountsConfig,
    ticker_map: dict[str, str] | None = None,
    broker: str | None = None,
    auto_inject_deposits: bool | None = None,
    output_dir: Path | None = None,
) -> ConvertSummary:
    """Run the full pipeline. Writes one WF CSV per account into
    `output_dir` (default `data/converted/`) and returns a summary.

    Filename pattern: `<ts>-wf-<account>.csv`. Each file is directly
    importable via Wealthfolio's "Import Activities" UI wizard; the
    extra `account` column is ignored by the wizard but used by `push`.
    """
    registry = adapters_pkg.discover()
    adapter = adapters_pkg.select(registry, str(input_path), broker)

    raw_rows = adapter.convert(str(input_path))
    wf_csv.validate_adapter_output(raw_rows, adapter=adapter.name)

    if ticker_map:
        _apply_ticker_map(raw_rows, ticker_map)

    _apply_grouping(raw_rows, accounts)

    should_inject = (
        adapter.auto_inject_deposits if auto_inject_deposits is None else auto_inject_deposits
    )
    if should_inject:
        rows, injected = _inject_synthetic_deposits(raw_rows)
    else:
        rows, injected = list(raw_rows), 0

    rows = _sort_rows(rows)

    out_dir = output_dir if output_dir is not None else Path("data/converted")
    ts = datetime.now().strftime("%Y%m%d%H%M%S")

    # Partition by account, preserving the (stable) global date order
    # within each account.
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["account"], []).append(row)

    output_paths: dict[str, Path] = {}
    for acct, group in grouped.items():
        path = out_dir / f"{ts}-wf-{_safe_account_filename(acct)}.csv"
        wf_csv.write(path, group)
        output_paths[acct] = path

    by_account = {acct: len(group) for acct, group in grouped.items()}

    return ConvertSummary(
        output_paths=output_paths,
        adapter_name=adapter.name,
        row_count=len(rows),
        deposits_injected=injected,
        by_account=by_account,
    )
