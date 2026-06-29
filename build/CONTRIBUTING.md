# Contributing a broker adapter

Adding a new broker (Fineco, IBKR, Degiro, ...) is one PR:

1. Add `build/src/adapters/<name>.py` with the four required exports.
2. Add `build/tests/fixtures/<name>/{input.csv,expected.csv,wf-config.yml}`.
3. Open the PR. The generic contract test runs against your fixture automatically.

## The contract

```python
# build/src/adapters/fineco.py

NAME = "fineco"
DESCRIPTION = "Fineco Bank - Account statement CSV export"
AUTO_INJECT_DEPOSITS = True

def detect(path: str) -> bool:          # optional
    with open(path, encoding="utf-8-sig") as f:
        return "FINECO" in f.readline().upper()

def convert(path: str) -> list[dict]:   # required
    ...
```

Each returned row MUST have these keys:

| key              | type          | notes                                                                             |
| ---------------- | ------------- | --------------------------------------------------------------------------------- |
| `date`           | str           | ISO 8601 (`YYYY-MM-DD`)                                                           |
| `symbol`         | str           | WF-format (e.g. `SWDA.MI`); `""` for cash flows                                  |
| `instrumentType` | str           | `"EQUITY"` or `""`                                                                |
| `quantity`       | float / int   |                                                                                   |
| `activityType`   | str           | `BUY` / `SELL` / `DEPOSIT` / `WITHDRAWAL` / `DIVIDEND` / `INTEREST` / `FEE` / `TAX` |
| `unitPrice`      | float / int   |                                                                                   |
| `currency`       | str           | ISO-4217 (`EUR`, `USD`, ...)                                                      |
| `fee`            | float / int   | `0` if none                                                                       |
| `amount`         | float \| None | `None` lets Wealthfolio compute it                                                |

The `account` key is set by the orchestrator. **Adapters must not set it.** The contract test fails if you do.

## Don'ts

- No network access. No filesystem writes. No global state.
- No account routing logic - that is `wf-config.yml`'s job. Broker-quirk maps (e.g. ticker to Yahoo suffix) are fine; personal ticker-to-account maps are not.

## Fixtures

`build/tests/fixtures/<NAME>/input.csv`: tiny, **anonymised** broker export (5-15 lines). Include at least one row per activity type your adapter emits, plus one row your adapter is expected to skip.

`build/tests/fixtures/<NAME>/expected-<account>.csv`: one golden file per account the orchestrator emits, after the full pipeline (grouping, auto-deposit, sort). The test diffs each generated file against its expected counterpart. Include `wf-config.yml` next to them with the routing rules your goldens assume.

Optional: `build/tests/test_<NAME>.py` that runs the pipeline against your fixture and diffs against the expected CSV.

## Running tests

From the repo root:

```bash
IMAGE=wf-importer-gui:latest bash build/build.sh
docker run --rm --entrypoint pytest wf-importer-gui:latest -v
```

## Style

Format with `ruff format` (line length 100). Type hints encouraged. User-facing strings (errors, UI labels) must be English; non-English is OK in adapter docstrings when it makes broker-specific terms clearer.

For weird inputs (XLSX, PDF, multi-sheet exports) ship a `preprocess.py` next to the adapter; the adapter itself stays a pure CSV reader.
