"""Unit tests for orchestrator pipeline behaviour."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src import orchestrator
from src.config import AccountRule, AccountsConfig


def _accounts(default: str = "cash", rules: tuple[AccountRule, ...] = ()) -> AccountsConfig:
    return AccountsConfig(default=default, rules=rules)


def test_auto_deposit_count_and_amount():
    rows: list[dict[str, Any]] = [
        {
            "date": "2026-01-01",
            "symbol": "AAA",
            "instrumentType": "EQUITY",
            "quantity": 2.0,
            "activityType": "BUY",
            "unitPrice": 50.0,
            "currency": "EUR",
            "fee": 0.0,
            "amount": None,
            "account": "cash",
        },
    ]
    out, injected = orchestrator._inject_synthetic_deposits(rows)
    assert injected == 1
    assert len(out) == 2
    assert out[0]["activityType"] == "DEPOSIT"
    assert out[0]["amount"] == 100.0
    assert out[1]["activityType"] == "BUY"


def test_auto_deposit_order_preserves_pairing():
    rows: list[dict[str, Any]] = [
        {
            "date": "2026-01-01",
            "symbol": "AAA",
            "instrumentType": "EQUITY",
            "quantity": 1,
            "activityType": "BUY",
            "unitPrice": 10,
            "currency": "EUR",
            "fee": 0,
            "amount": None,
            "account": "a",
        },
        {
            "date": "2026-01-02",
            "symbol": "BBB",
            "instrumentType": "EQUITY",
            "quantity": 1,
            "activityType": "BUY",
            "unitPrice": 20,
            "currency": "EUR",
            "fee": 0,
            "amount": None,
            "account": "b",
        },
    ]
    out, injected = orchestrator._inject_synthetic_deposits(rows)
    assert injected == 2
    assert [r["activityType"] for r in out] == ["DEPOSIT", "BUY", "DEPOSIT", "BUY"]
    # Each deposit inherits the account from the BUY that follows it.
    assert out[0]["account"] == "a"
    assert out[2]["account"] == "b"


def test_auto_deposit_inherits_account_from_buy():
    rows: list[dict[str, Any]] = [
        {
            "date": "2026-01-01",
            "symbol": "SWDA.MI",
            "instrumentType": "EQUITY",
            "quantity": 1,
            "activityType": "BUY",
            "unitPrice": 100,
            "currency": "EUR",
            "fee": 0,
            "amount": None,
            "account": "long-term",
        },
    ]
    out, _ = orchestrator._inject_synthetic_deposits(rows)
    assert out[0]["account"] == "long-term"


def test_grouping_default_fallback():
    accounts = _accounts(
        default="cash",
        rules=(AccountRule("long-term", frozenset({"SWDA.MI"})),),
    )
    assert accounts.assign("UNKNOWN") == "cash"
    assert accounts.assign("") == "cash"


def test_stable_sort_keeps_deposit_before_buy_on_same_date():
    rows = [
        {"date": "2026-01-02", "activityType": "BUY"},
        {"date": "2026-01-01", "activityType": "DEPOSIT"},
        {"date": "2026-01-02", "activityType": "DEPOSIT"},
        {"date": "2026-01-02", "activityType": "BUY"},
    ]
    sorted_rows = orchestrator._sort_rows(rows)
    assert [r["activityType"] for r in sorted_rows] == [
        "DEPOSIT",
        "BUY",
        "DEPOSIT",
        "BUY",
    ]




def _sell(**over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "date": "2026-01-01",
        "symbol": "EM35.MI",
        "instrumentType": "EQUITY",
        "quantity": 9.0,
        "activityType": "SELL",
        "unitPrice": 151.41,
        "currency": "EUR",
        "fee": 0.0,
        "amount": None,
        "account": "longterm",
    }
    row.update(over)
    return row


def test_auto_withdrawal_count_and_amount():
    out, injected = orchestrator._inject_synthetic_withdrawals([_sell()])
    assert injected == 1
    assert len(out) == 2
    assert out[0]["activityType"] == "SELL"
    assert out[1]["activityType"] == "WITHDRAWAL"
    assert out[1]["amount"] == 1362.69


def test_auto_withdrawal_follows_its_sell():
    """The WITHDRAWAL must come after the SELL, or it removes cash the
    account has not been credited with yet."""
    out, _ = orchestrator._inject_synthetic_withdrawals(
        [_sell(date="2026-01-01"), _sell(date="2026-01-02", symbol="SWDA.MI")]
    )
    assert [r["activityType"] for r in out] == [
        "SELL",
        "WITHDRAWAL",
        "SELL",
        "WITHDRAWAL",
    ]


def test_auto_withdrawal_inherits_account_from_sell():
    out, _ = orchestrator._inject_synthetic_withdrawals([_sell(account="longterm")])
    assert out[1]["account"] == "longterm"


def test_auto_withdrawal_ignores_non_sell_rows():
    rows = [
        {"activityType": "BUY", "date": "2026-01-01", "quantity": 1,
         "unitPrice": 10, "currency": "EUR", "account": "cash"},
        {"activityType": "DEPOSIT", "date": "2026-01-01", "quantity": 1,
         "unitPrice": 1, "currency": "EUR", "account": "cash"},
    ]
    out, injected = orchestrator._inject_synthetic_withdrawals(rows)
    assert injected == 0
    assert out == rows


def test_withdrawal_row_is_schema_valid():
    """Synthetic rows go through the same writer as adapter rows, so they
    must satisfy the WF schema."""
    from src import wf_csv

    out, _ = orchestrator._inject_synthetic_withdrawals([_sell()])
    wf_csv.validate_adapter_row(out[1], line=1, adapter="synthetic")


def test_stable_sort_keeps_withdrawal_after_sell_on_same_date():
    rows = [
        {"date": "2026-01-02", "activityType": "SELL"},
        {"date": "2026-01-02", "activityType": "WITHDRAWAL"},
        {"date": "2026-01-01", "activityType": "DEPOSIT"},
        {"date": "2026-01-01", "activityType": "BUY"},
    ]
    assert [r["activityType"] for r in orchestrator._sort_rows(rows)] == [
        "DEPOSIT",
        "BUY",
        "SELL",
        "WITHDRAWAL",
    ]


def test_buy_and_sell_together_net_to_zero_cash():
    """A BUY funded by a DEPOSIT and a SELL swept by a WITHDRAWAL must
    leave the account's cash exactly where it started."""
    rows = [
        {
            "date": "2026-01-01", "symbol": "SWDA.MI", "instrumentType": "EQUITY",
            "quantity": 8.0, "activityType": "BUY", "unitPrice": 126.58,
            "currency": "EUR", "fee": 0.0, "amount": None, "account": "longterm",
        },
        _sell(),
    ]
    rows, deposits = orchestrator._inject_synthetic_deposits(rows)
    rows, withdrawals = orchestrator._inject_synthetic_withdrawals(rows)
    assert (deposits, withdrawals) == (1, 1)

    cash = 0.0
    for row in orchestrator._sort_rows(rows):
        t = row["activityType"]
        if t == "DEPOSIT":
            cash += row["amount"]
        elif t == "WITHDRAWAL":
            cash -= row["amount"]
        elif t == "BUY":
            cash -= round(row["quantity"] * row["unitPrice"], 2)
        elif t == "SELL":
            cash += round(row["quantity"] * row["unitPrice"], 2)
        assert cash >= 0, f"cash went negative after {t}"
    assert cash == 0.0


# ── Full-pipeline tests: convert() wiring, not just the helpers ───────────

_DIRECTA_ACCOUNTS = AccountsConfig(
    default="zzcatchall",
    rules=(AccountRule("longterm", frozenset({"AGGH.MI", "VWCE.MI", "EIMI.MI"})),),
)
_DIRECTA_TICKERS = {"AGGH": "AGGH.MI", "VWCE": "VWCE.MI", "EIMI": "EIMI.MI"}


def _convert_fixture(fixtures_dir: Path, tmp_path: Path, **over: Any):
    kwargs: dict[str, Any] = {
        "input_path": fixtures_dir / "directa" / "input.csv",
        "accounts": _DIRECTA_ACCOUNTS,
        "ticker_map": _DIRECTA_TICKERS,
        "output_dir": tmp_path,
    }
    kwargs.update(over)
    return orchestrator.convert(**kwargs)


def test_convert_reports_both_injection_counts(fixtures_dir: Path, tmp_path: Path):
    summary = _convert_fixture(fixtures_dir, tmp_path)
    assert summary.deposits_injected == 6   # one per BUY
    assert summary.withdrawals_injected == 1  # one per SELL
    # 6 BUY + 1 SELL + 6 DEPOSIT + 1 WITHDRAWAL
    assert summary.row_count == 14


def test_convert_writes_withdrawal_after_sell(fixtures_dir: Path, tmp_path: Path):
    """The written CSV, not just the in-memory list, must keep the pairing."""
    from src import wf_csv

    summary = _convert_fixture(fixtures_dir, tmp_path)
    rows = wf_csv.read(summary.output_paths["longterm"])
    types = [r["activityType"] for r in rows]
    sell_at = types.index("SELL")
    assert types[sell_at + 1] == "WITHDRAWAL"
    assert rows[sell_at + 1]["amount"] == 24.9
    assert rows[sell_at + 1]["account"] == "longterm"


def test_convert_with_both_injections_disabled_emits_no_synthetic_rows(
    fixtures_dir: Path, tmp_path: Path
):
    summary = _convert_fixture(
        fixtures_dir, tmp_path,
        auto_inject_deposits=False, auto_inject_withdrawals=False,
    )
    assert (summary.deposits_injected, summary.withdrawals_injected) == (0, 0)
    assert summary.row_count == 7  # 6 BUY + 1 SELL, nothing injected

    from src import wf_csv

    for path in summary.output_paths.values():
        types = {r["activityType"] for r in wf_csv.read(path)}
        assert types <= {"BUY", "SELL"}


def test_convert_toggles_are_independent(fixtures_dir: Path, tmp_path: Path):
    """The GUI exposes one switch per injection; turning off deposits must
    not silently disable withdrawals, or vice versa."""
    only_withdrawals = _convert_fixture(
        fixtures_dir, tmp_path,
        auto_inject_deposits=False, auto_inject_withdrawals=True,
    )
    assert only_withdrawals.deposits_injected == 0
    assert only_withdrawals.withdrawals_injected == 1

    only_deposits = _convert_fixture(
        fixtures_dir, tmp_path,
        auto_inject_deposits=True, auto_inject_withdrawals=False,
    )
    assert only_deposits.deposits_injected == 6
    assert only_deposits.withdrawals_injected == 0


def test_convert_defaults_to_adapter_preference_per_flag(
    fixtures_dir: Path, tmp_path: Path
):
    """Passing None for one flag must fall back to the adapter, not to the
    other flag's value."""
    summary = _convert_fixture(
        fixtures_dir, tmp_path,
        auto_inject_deposits=False, auto_inject_withdrawals=None,
    )
    assert summary.deposits_injected == 0
    assert summary.withdrawals_injected == 1  # directa declares True


def test_convert_sell_lands_in_the_symbols_account(fixtures_dir: Path, tmp_path: Path):
    """A SELL must be grouped by its own symbol, and drag its WITHDRAWAL
    into the same file."""
    from src import wf_csv

    summary = _convert_fixture(fixtures_dir, tmp_path)
    assert "longterm" in summary.output_paths
    rows = wf_csv.read(summary.output_paths["longterm"])
    sells = [r for r in rows if r["activityType"] == "SELL"]
    assert [r["symbol"] for r in sells] == ["AGGH.MI"]
    assert all(r["account"] == "longterm" for r in rows)
