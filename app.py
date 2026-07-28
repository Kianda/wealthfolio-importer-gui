"""Streamlit GUI for wf-importer, browser-based alternative to the CLI."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from src import adapters as adapters_pkg
from src import api_client, orchestrator, wf_csv
from src.adapters import AdapterError
from src.config import ConfigError, load as load_config

# -- paths

CONFIG_PATH   = Path(os.environ.get("WF_CONFIG", "wealthfolio-importer-config.yml"))
DATA_DIR      = Path("data")
INPUT_DIR     = DATA_DIR / "input"
CONVERTED_DIR = DATA_DIR / "converted"
PUSHED_DIR    = DATA_DIR / "pushed"

# -- page setup

st.set_page_config(page_title="WF Importer", page_icon="📈", layout="centered")
st.title("📈 Wealthfolio Importer")

# -- config

try:
    cfg = load_config(CONFIG_PATH)
except ConfigError as e:
    st.error(f"**Config error:** {e}")
    st.stop()

base_url = os.environ.get("WF_BASE_URL") or cfg.wealthfolio.base_url

st.divider()

# -- step 1: upload

st.subheader("1 · Upload broker CSV")

uploaded = st.file_uploader(
    "Drop your broker export here",
    type=["csv"],
    label_visibility="collapsed",
)

# Clear convert result and save a copy to data/input/ whenever a new file is uploaded.
if uploaded and uploaded.name != st.session_state.get("last_file"):
    st.session_state.pop("summary", None)
    st.session_state.pop("converted_rows", None)
    st.session_state["last_file"] = uploaded.name
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    (INPUT_DIR / uploaded.name).write_bytes(uploaded.getvalue())

if not uploaded:
    st.stop()

# -- step 2: convert

st.subheader("2 · Convert")

auto_deposit = st.toggle(
    "Auto-inject deposits",
    value=True,
    help=(
        "Insert a synthetic DEPOSIT before each BUY so Wealthfolio's "
        "cash balance never goes negative. Disable only if you record "
        "deposits yourself."
    ),
)

convert_clicked = st.button("Convert", type="primary")

# Run on first upload (no summary yet) or when the button is clicked.
if convert_clicked or "summary" not in st.session_state:
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp.write(uploaded.getvalue())
        tmp_path = Path(tmp.name)
    try:
        with st.spinner("Converting…"):
            summary = orchestrator.convert(
                input_path=tmp_path,
                accounts=cfg.accounts,
                ticker_map=cfg.ticker_map,
                auto_inject_deposits=auto_deposit,
                output_dir=CONVERTED_DIR,
            )
        st.session_state["summary"] = summary
        st.session_state["converted_rows"] = {
            acct: wf_csv.read(path)
            for acct, path in summary.output_paths.items()
        }
    except (AdapterError, wf_csv.AdapterOutputError) as e:
        st.error(f"**Conversion failed:** {e}")
        st.stop()
    finally:
        tmp_path.unlink(missing_ok=True)

summary      = st.session_state["summary"]
converted_rows: dict[str, list] = st.session_state["converted_rows"]

st.success(
    f"Converted **{summary.row_count} rows** · "
    f"adapter `{summary.adapter_name}` · "
    f"{summary.deposits_injected} deposits injected"
)

for acct, rows in converted_rows.items():
    with st.expander(f"**{acct}** ({summary.by_account[acct]} rows)", expanded=True):
        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
            column_config={
                "date":         st.column_config.DateColumn("Date",       format="YYYY-MM-DD"),
                "activityType": st.column_config.TextColumn("Type"),
                "symbol":       st.column_config.TextColumn("Symbol"),
                "quantity":     st.column_config.NumberColumn("Qty",       format="%.0f"),
                "unitPrice":    st.column_config.NumberColumn("Unit price",format="%.4f"),
                "amount":       st.column_config.NumberColumn("Amount",    format="%.2f"),
                "currency":     st.column_config.TextColumn("CCY"),
                "fee":          st.column_config.NumberColumn("Fee",       format="%.2f"),
                "account":      st.column_config.TextColumn("Account"),
            },
        )

st.caption(
    f"CSVs written to `{CONVERTED_DIR}/`. Also importable manually via the Wealthfolio UI wizard."
)
st.divider()

# -- step 3: push

st.subheader("3 · Push to Wealthfolio")

with st.form("push_form"):
    password = st.text_input(
        "Password (leave empty if auth is disabled)",
        type="password",
        value=os.environ.get("WF_PASSWORD", ""),
    )
    force = st.checkbox(
        "Force re-push duplicates",
        help="Re-insert rows already in Wealthfolio. Creates duplicates - use with care.",
    )
    push_clicked = st.form_submit_button("Push", type="primary")

if not push_clicked:
    st.stop()

client = api_client.WealthfolioClient(base_url)

if password:
    with st.spinner("Logging in…"):
        try:
            client.login(password)
        except api_client.ApiError as e:
            st.error(f"**Login failed:** {e}")
            st.stop()

with st.spinner("Fetching accounts…"):
    try:
        wf_accounts = client.list_accounts()
    except api_client.ApiError as e:
        st.error(f"**Could not list accounts:** {e}")
        if "connection error" in str(e).lower():
            st.info(
                "**Network troubleshooting:** the importer container cannot reach "
                "your Wealthfolio instance. Make sure both containers are on the "
                "same Docker network and that `base_url` in `wealthfolio-importer-config.yml` uses "
                "the Wealthfolio container name as the hostname — not `localhost`."
            )
        st.stop()

name_to_id = {a["name"]: a["id"] for a in wf_accounts}
missing = [a for a in converted_rows if a not in name_to_id]
if missing:
    st.error(
        f"Account(s) not found in Wealthfolio: `{missing}`  \n"
        f"Existing accounts: `{sorted(name_to_id)}`"
    )
    st.stop()

all_ok = True

for acct, rows in converted_rows.items():
    activities = api_client.rows_to_activities(rows, name_to_id[acct])

    with st.spinner(f"Checking `{acct}`…"):
        try:
            checked = client.check_import(activities)
        except api_client.ApiError as e:
            st.error(f"`{acct}`: check failed: {e}")
            all_ok = False
            continue

    with st.spinner(f"Preparing assets for `{acct}`…"):
        try:
            checked = client.ensure_assets(checked)
        except api_client.ApiError as e:
            st.warning(f"`{acct}`: asset preparation warning: {e}")

    bad = [a for a in checked if a.get("errors")]
    if bad:
        st.error(f"`{acct}`: {len(bad)} invalid row(s)")
        for r in bad[:5]:
            st.code(f"{r['date']} {r.get('symbol','')} {r['activityType']}: {r['errors']}")
        all_ok = False
        continue

    new   = [a for a in checked if not a.get("duplicateOfId")]
    dupes = [a for a in checked if a.get("duplicateOfId")]

    if dupes:
        st.warning(f"`{acct}`: {len(dupes)} duplicate(s), {'will re-push' if force else 'skipped'}.")

    if force:
        for a in dupes:
            a["forceImport"] = True

    to_push = (new + dupes) if force else new
    if not to_push:
        st.info(f"`{acct}`: nothing new to push.")
        continue

    with st.spinner(f"Pushing {len(to_push)} rows → `{acct}`…"):
        try:
            result = client.commit_import(to_push)
        except api_client.ApiError as e:
            st.error(f"`{acct}`: commit failed: {e}")
            all_ok = False
            continue

    if result.success:
        st.success(
            f"`{acct}` - imported: {result.imported}, "
            f"skipped: {result.skipped}, duplicates: {result.duplicates}"
        )
    else:
        st.error(f"`{acct}` failed: {result.error_message}")
        all_ok = False

if all_ok:
    PUSHED_DIR.mkdir(parents=True, exist_ok=True)
    for path in summary.output_paths.values():
        if path.exists():
            path.replace(PUSHED_DIR / path.name)

    st.balloons()
    st.success("All done! Files archived to `data/pushed/`.")

    for key in ("summary", "converted_rows", "last_file"):
        st.session_state.pop(key, None)
