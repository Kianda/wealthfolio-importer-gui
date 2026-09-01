"""Directa Movimenti: sale (Vendita) handling."""
from __future__ import annotations

from pathlib import Path

from src.adapters import directa


def _rows(fixtures_dir: Path):
    return directa.convert(str(fixtures_dir / "directa" / "input.csv"))


def test_vendita_becomes_sell(fixtures_dir: Path):
    sells = [r for r in _rows(fixtures_dir) if r["activityType"] == "SELL"]
    assert len(sells) == 1
    sell = sells[0]
    assert sell["symbol"] == "AGGH"
    assert sell["date"] == "2024-04-11"
    assert sell["quantity"] == 5.0
    # Importo euro is positive on a sale; unitPrice is gross proceeds / qty.
    assert sell["unitPrice"] == 4.98


def test_acquisto_still_becomes_buy(fixtures_dir: Path):
    buys = [r for r in _rows(fixtures_dir) if r["activityType"] == "BUY"]
    assert len(buys) == 6
    assert all(r["unitPrice"] > 0 for r in buys)


def test_zero_quantity_cash_rows_are_skipped(fixtures_dir: Path):
    """Commissioni / Rit. etf / Bollo carry quantity 0 and would divide by
    zero if they ever reached the unitPrice calculation."""
    rows = _rows(fixtures_dir)
    assert all(r["quantity"] != 0 for r in rows)
    assert {r["activityType"] for r in rows} == {"BUY", "SELL"}


_PREAMBLE = (
    "Conto : X0000 ROSSI MARIO;;;;;;;;;;;\n"
    "Data operazione;Data valuta;Tipo operazione;Ticker;Isin;Protocollo;"
    "Descrizione;Quantità;Importo euro;Importo Divisa;Divisa;Riferimento ordine\n"
)


def test_zero_quantity_trade_row_does_not_crash(tmp_path: Path):
    """A mapped trade type carrying quantity 0 must be skipped, not divided
    by. Guards the unitPrice = importo / qty calculation."""
    csv_path = tmp_path / "movimenti.csv"
    csv_path.write_text(
        _PREAMBLE
        + "11-04-2024;15-04-2024;Vendita;AGGH;IE00BDBRDM35;;DESC;0;24,90;0;EUR;1\n"
        + "11-04-2024;15-04-2024;Vendita;AGGH;IE00BDBRDM35;;DESC;5;24,90;0;EUR;2\n",
        encoding="utf-8",
    )
    rows = directa.convert(str(csv_path))
    assert len(rows) == 1
    assert rows[0]["quantity"] == 5.0
