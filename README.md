# wf-importer-gui

Browser-based GUI for importing broker CSV exports into [Wealthfolio](https://github.com/wealthfolio/wealthfolio).

## Requirements

- Docker
- A running Wealthfolio instance (managed separately)

## Setup

```bash
cp wf-config.example.yml wf-config.yml
```

Edit `wf-config.yml` and set `wealthfolio.base_url` to the URL of your Wealthfolio instance as reachable from inside the GUI container (see Networking below).

## Start / stop

```bash
bash start.sh   # pulls image, starts container on port 23527
bash stop.sh
```

Open http://localhost:23527.

## Networking

The GUI container needs to reach your Wealthfolio instance over the network. After starting, connect it to whatever Docker network your WF container is on:

```bash
docker network connect <your-wf-network> wf-importer-gui
```

Then set `base_url` in `wf-config.yml` to the WF container's address on that network (e.g. `http://wealthfolio:8088`).

## Configuration (`wf-config.yml`)

```yaml
wealthfolio:
  base_url: http://<wf-hostname>:<port>

accounts:
  default: cash         # catch-all for unmatched symbols
  rules:
    - account: longterm
      symbols: [SWDA.MI, EM35.MI, SGLN.MI]
    - account: cash
      symbols: [XEON.MI, C3M.MI]
```

Account names must match exactly what is configured in your Wealthfolio instance. Symbols use Yahoo Finance format (e.g. `SWDA.MI`).

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `WF_BASE_URL` | from `wf-config.yml` | Override the Wealthfolio internal URL at runtime |
| `WF_PASSWORD` | (none) | Pre-fill the password field in the UI |
| `WF_CONFIG` | `wf-config.yml` | Path to a custom config file |
| `IMAGE` | see `start.sh` | DockerHub image to pull and run |

## Building a new image

Edit `build/app.py`, then from the repo root:

```bash
IMAGE=you/wf-importer-gui:latest PUSH=1 bash build/build.sh
```
