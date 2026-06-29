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


