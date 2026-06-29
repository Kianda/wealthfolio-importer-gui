"""Directa Trading (Italy) - raw "Movimenti_<account>_<date>.csv" export.

Format quirks handled here:
  - 9 lines of preamble before the header line that starts with
    "Data operazione".
  - `;` field separator.
  - Italian decimal format (`-446,53`).
  - Only `Tipo operazione = Acquisto` (buy) rows are emitted.
    Conferimento con bonifico (deposit), Bollo portafoglio titoli
    (securities tax), Commissioni (fees), etc. are silently dropped;
    the orchestrator injects synthetic deposits
    when AUTO_INJECT_DEPOSITS is true.

Ticker mapping (Directa bare ticker → Yahoo Finance suffix) is the only
broker-specific knowledge baked in here. Adding a new ticker means one
new line in TICKER_MAP; user-level routing (which account each symbol
belongs to) lives in wf-config.yml, not here.
"""

from __future__ import annotations

import csv
from datetime import datetime
from typing import Any


NAME = "directa"
DESCRIPTION = "Directa Trading (Italy) - Movimenti_<account>_<date>.csv export"
AUTO_INJECT_DEPOSITS = True

TICKER_MAP = {
    "SWDA": "SWDA.MI",
    "EM35": "EM35.MI",
    "XEON": "XEON.MI",
    "SGLN": "SGLN.MI",
    "C3M": "C3M.MI",
}

TYPE_MAP = {
    "Acquisto": "BUY",
}


def _parse_it_float(s: str) -> float:
    return float(s.strip().replace(",", "."))


def detect(path: str) -> bool:
    """First line of a Directa raw export starts with 'Conto :'."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            return f.readline().startswith("Conto :")
    except OSError:
        return False


def convert(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path, encoding="utf-8-sig") as f:
        header = None
        for line in f:
            if line.startswith("Data operazione"):
                header = line.rstrip("\r\n").split(";")
                break
        if header is None:
            raise ValueError(f"directa: CSV header not found in {path}")

        reader = csv.DictReader(f, fieldnames=header, delimiter=";")
        for raw in reader:
            tipo = raw["Tipo operazione"].strip()
            if tipo not in TYPE_MAP:
                continue
            ticker = raw["Ticker"].strip()
            if ticker not in TICKER_MAP:
                # Unknown ticker: leave the bare value in the output and
                # let the user notice / extend TICKER_MAP. We don't
                # silently drop, because that hides real trades.
                symbol = ticker
            else:
                symbol = TICKER_MAP[ticker]

            qty = _parse_it_float(raw["Quantità"])
            importo = abs(_parse_it_float(raw["Importo euro"]))
            currency = raw["Divisa"].strip()
            iso_date = datetime.strptime(raw["Data operazione"].strip(), "%d-%m-%Y").strftime(
                "%Y-%m-%d"
            )
            unit_price = round(importo / qty, 4)

            rows.append(
                {
                    "date": iso_date,
                    "symbol": symbol,
                    "instrumentType": "EQUITY",
                    "quantity": qty,
                    "activityType": TYPE_MAP[tipo],
                    "unitPrice": unit_price,
                    "currency": currency,
                    "fee": 0.0,
                    "amount": None,
                }
            )
    return rows
