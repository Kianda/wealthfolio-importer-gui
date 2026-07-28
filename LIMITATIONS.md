# Known limitations

## Same symbol can't route to multiple accounts

`wealthfolio-importer-config.yml` maps one symbol to one account. The loader rejects collisions. This hurts when one broker account is split across people, tax wrappers, or manual lot tags; the broker export has no signal to tell them apart.

**Workaround:** after converting, download the generated WF CSV from `data/converted/`, hand-edit the `account` column, and re-upload it. Each synthetic `DEPOSIT` row sits right above its `BUY`; flip them together so cash stays balanced.

A sidecar `assignments.yml` keyed by broker order ID would solve it cleanly but is not built. Open an issue if you would use it.

## WF API isn't a public contract

`/api/v1/activities/import*` may shift between Wealthfolio releases. If the push step breaks after a WF update, check the API response in the error message and open an issue.

## CSV inputs only

No XLSX, PDF, or JSON. Pre-process with `libreoffice --convert-to csv` / `pdftotext` / etc., or ship a `preprocess.py` alongside your adapter.

## No SELL in the Directa adapter

The v1 adapter only handles `Acquisto` (buy) rows. One-line addition to `TYPE_MAP` once you have a real `Vendita` (sell) to import. PR welcome with a fixture.
