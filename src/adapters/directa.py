"""Directa Trading (Italy) - broker CSV export adapter.

Handles two export formats produced by the Directa platform:

  Movimenti_<account>_<date>.csv  -- movements / statement
    Header line starts with: "Data operazione"
    Columns used: Data operazione, Tipo operazione, Ticker, Quantità,
                  Importo euro, Divisa

  Ordini_<account>_<date>.csv  -- executed orders
    Header line starts with: "Strumento"
    Columns used: Data/Ora immissione, Acquisto/Vendita, Ticker,
                  Quantità eseguita, Prezzo medio, Stato
    Currency is not in the file; EUR is assumed (Borsa Italiana).

Both share the same preamble (first line starts with "Conto :"),
so detect() works for both. convert() sniffs the header to pick
the right parser.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any


NAME = "directa"
DESCRIPTION = "Directa Trading (Italy) - Movimenti or Ordini CSV export"
AUTO_INJECT_DEPOSITS = True

_MOVIMENTI_TYPE_MAP = {
    "Acquisto": "BUY",
}

_ORDINI_TYPE_MAP = {
    "Buy":  "BUY",
    "Sell": "SELL",
}


def _parse_it_float(s: str) -> float:
    return float(s.strip().replace(",", "."))


def detect(path: str) -> bool:
    """First line of any Directa export starts with 'Conto :'."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            return f.readline().startswith("Conto :")
    except OSError:
        return False


def _parse_movimenti(lines: list[str]) -> list[dict[str, Any]]:
    header = lines[0].rstrip("\r\n").split(";")
    reader = csv.DictReader(io.StringIO("".join(lines[1:])), fieldnames=header, delimiter=";")
    rows: list[dict[str, Any]] = []
    for raw in reader:
        tipo = raw["Tipo operazione"].strip()
        if tipo not in _MOVIMENTI_TYPE_MAP:
            continue
        qty = _parse_it_float(raw["Quantità"])
        importo = abs(_parse_it_float(raw["Importo euro"]))
        rows.append({
            "date": datetime.strptime(raw["Data operazione"].strip(), "%d-%m-%Y").strftime("%Y-%m-%d"),
            "symbol": raw["Ticker"].strip(),
            "instrumentType": "EQUITY",
            "quantity": qty,
            "activityType": _MOVIMENTI_TYPE_MAP[tipo],
            "unitPrice": round(importo / qty, 4),
            "currency": raw["Divisa"].strip(),
            "fee": 0.0,
            "amount": None,
        })
    return rows


def _parse_ordini(lines: list[str]) -> list[dict[str, Any]]:
    header = lines[0].rstrip("\r\n").split(";")
    reader = csv.DictReader(io.StringIO("".join(lines[1:])), fieldnames=header, delimiter=";")
    rows: list[dict[str, Any]] = []
    for raw in reader:
        if raw.get("Stato", "").strip() != "Eseguito":
            continue
        tipo = raw["Acquisto/Vendita"].strip()
        if tipo not in _ORDINI_TYPE_MAP:
            continue
        rows.append({
            "date": datetime.strptime(raw["Data/Ora immissione"].strip(), "%d/%m/%Y %H:%M:%S").strftime("%Y-%m-%d"),
            "symbol": raw["Ticker"].strip(),
            "instrumentType": "EQUITY",
            "quantity": _parse_it_float(raw["Quantità eseguita"]),
            "activityType": _ORDINI_TYPE_MAP[tipo],
            "unitPrice": round(_parse_it_float(raw["Prezzo medio"]), 4),
            "currency": "EUR",
            "fee": 0.0,
            "amount": None,
        })
    return rows


def convert(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8-sig") as f:
        lines = f.readlines()

    header_idx = None
    fmt = None
    for i, line in enumerate(lines):
        if line.startswith("Data operazione"):
            header_idx, fmt = i, "movimenti"
            break
        if line.startswith("Strumento"):
            header_idx, fmt = i, "ordini"
            break

    if header_idx is None:
        raise ValueError(
            f"directa: unrecognised CSV format in {path}. "
            f"Expected header 'Data operazione' (Movimenti) or 'Strumento' (Ordini)."
        )

    rows = _parse_movimenti(lines[header_idx:]) if fmt == "movimenti" else _parse_ordini(lines[header_idx:])

    if not rows:
        raise ValueError(f"directa: no processable rows found in {path} (format: {fmt})")

    return rows
