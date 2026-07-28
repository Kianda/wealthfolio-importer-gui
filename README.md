# wealthfolio-importer-gui

Browser-based GUI for importing broker CSV exports into [Wealthfolio](https://github.com/wealthfolio/wealthfolio).

Distributed as a Docker image. To run it, use the [wealthfolio-boilerplate](https://github.com/Kianda/wealthfolio-boilerplate) — it includes this as an optional service.

## Building

```bash
cp .env.example .env   # set IMAGE=you/your-image:tag
bash build.sh          # build only
PUSH=1 bash build.sh   # build + push
```

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest
```
