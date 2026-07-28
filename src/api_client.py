"""HTTP client for the Wealthfolio self-hosted API.

Endpoints (verified against wealthfolio/wealthfolio source as of 3.4.0):
  POST /api/v1/auth/login                         -> sets HttpOnly session cookie
  GET  /api/v1/accounts                           -> list accounts
  POST /api/v1/activities/import/check            -> validate + enrich rows
  POST /api/v1/activities/import/assets/preview   -> preview which assets are new
  POST /api/v1/assets                             -> create a single asset
  POST /api/v1/activities/import                  -> commit

Correct import flow (mirrors the Wealthfolio web UI):
  1. check_import   — enrich activities with symbol metadata
  2. ensure_assets  — preview + create any missing assets, patch activities with assetId
  3. commit_import  — insert activities (now all have assetId)

These endpoints are not a published contract; pin the Wealthfolio
image tag in production.
"""

from __future__ import annotations

import http.cookiejar
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

_CASH_SYMBOLS: frozenset[str] = frozenset({"", "$CASH-EUR", "$CASH-USD", "$CASH-GBP"})


class ApiError(RuntimeError):
    """Raised on non-2xx responses or transport failures."""


@dataclass
class ImportSummary:
    total: int
    imported: int
    skipped: int
    duplicates: int
    assets_created: int
    success: bool
    error_message: str | None


class WealthfolioClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def _call(self, method: str, path: str, payload: Any | None = None) -> Any:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if body else {}
        req = urllib.request.Request(self.base_url + path, data=body, headers=headers, method=method)
        try:
            with self._opener.open(req) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise ApiError(f"HTTP {e.code} on {method} {path}: {detail}") from e
        except urllib.error.URLError as e:
            raise ApiError(f"connection error on {method} {path}: {e.reason}") from e

    def login(self, password: str) -> None:
        self._call("POST", "/api/v1/auth/login", {"password": password})

    def list_accounts(self) -> list[dict[str, Any]]:
        return self._call("GET", "/api/v1/accounts")

    def check_import(self, activities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self._call(
            "POST", "/api/v1/activities/import/check", {"activities": activities}
        )

    def preview_import_assets(
        self, candidates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return self._call(
            "POST",
            "/api/v1/activities/import/assets/preview",
            {"candidates": candidates},
        )

    def create_asset(self, new_asset: dict[str, Any]) -> dict[str, Any]:
        return self._call("POST", "/api/v1/assets", new_asset)

    def ensure_assets(
        self, checked: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Create any missing assets and patch assetId into the enriched activities.

        The Wealthfolio commit endpoint requires every BUY/SELL activity to reference
        an existing asset via assetId.  The check_import endpoint populates assetId only
        when the asset already exists.  For new assets we must:
          1. preview_import_assets  → learn which assets need to be created
          2. POST /api/v1/assets    → create each new asset, get its UUID
          3. patch assetId          → so commit_import can link activities correctly
        """
        # ── 1. Build unique candidates from activities that need asset resolution ──
        def _candidate_key(a: dict[str, Any]) -> str:
            return "::".join([
                (a.get("accountId") or ""),
                (a.get("symbol") or "").strip().upper(),
                (a.get("instrumentType") or "").strip().upper(),
                (a.get("quoteMode") or "").strip().upper(),
                (a.get("quoteCcy") or "").strip().upper(),
                (a.get("exchangeMic") or "").strip().upper(),
                (a.get("isin") or "").strip().upper(),
            ])

        candidates_by_key: dict[str, dict[str, Any]] = {}
        for a in checked:
            symbol = (a.get("symbol") or "").strip()
            if not symbol or symbol in _CASH_SYMBOLS:
                continue
            if (a.get("assetId") or "").strip():
                continue  # already resolved
            key = _candidate_key(a)
            if key not in candidates_by_key:
                candidates_by_key[key] = {
                    "key": key,
                    "accountId": a.get("accountId"),
                    "symbol": symbol,
                    "currency": a.get("currency"),
                    "instrumentType": a.get("instrumentType") or None,
                    "quoteCcy": a.get("quoteCcy") or None,
                    "quoteMode": a.get("quoteMode") or None,
                    "exchangeMic": a.get("exchangeMic") or None,
                    "isin": a.get("isin") or None,
                    "providerId": a.get("providerId") or None,
                    "providerSymbol": a.get("providerSymbol") or None,
                }

        if not candidates_by_key:
            return checked

        # ── 2. Preview → find new vs existing assets ──────────────────────────────
        previews = self.preview_import_assets(list(candidates_by_key.values()))

        # ── 3. Create missing assets ───────────────────────────────────────────────
        key_to_asset_id: dict[str, str] = {}
        for preview in previews:
            key = preview["key"]
            existing_id = (preview.get("assetId") or "").strip()
            if existing_id:
                key_to_asset_id[key] = existing_id
            elif preview.get("status") == "AUTO_RESOLVED_NEW_ASSET" and preview.get("draft"):
                created = self.create_asset(preview["draft"])
                key_to_asset_id[key] = created["id"]
            # NeedsFixing → leave assetId absent; commit will report the validation error

        if not key_to_asset_id:
            return checked

        # ── 4. Patch assetId into activities ──────────────────────────────────────
        patched = []
        for a in checked:
            symbol = (a.get("symbol") or "").strip()
            if symbol and symbol not in _CASH_SYMBOLS and not (a.get("assetId") or "").strip():
                key = _candidate_key(a)
                if key in key_to_asset_id:
                    a = dict(a)
                    a["assetId"] = key_to_asset_id[key]
            patched.append(a)
        return patched

    def commit_import(self, enriched_activities: list[dict[str, Any]]) -> ImportSummary:
        result = self._call(
            "POST", "/api/v1/activities/import", {"activities": enriched_activities}
        )
        s = result["summary"]
        return ImportSummary(
            total=s["total"],
            imported=s["imported"],
            skipped=s["skipped"],
            duplicates=s["duplicates"],
            assets_created=s["assetsCreated"],
            success=s["success"],
            error_message=s.get("errorMessage"),
        )


def rows_to_activities(
    rows: list[dict[str, Any]], account_id: str
) -> list[dict[str, Any]]:
    """Convert WF CSV rows for one account into the API's ActivityImport shape."""
    out: list[dict[str, Any]] = []
    for row in rows:
        symbol = (row.get("symbol") or "").strip() or "$CASH-EUR"
        out.append(
            {
                "date": row["date"],
                "symbol": symbol,
                "activityType": row["activityType"],
                "quantity": float(row["quantity"]),
                "unitPrice": float(row["unitPrice"]),
                "currency": row["currency"],
                "fee": float(row.get("fee") or 0),
                "amount": float(row["amount"]) if row.get("amount") not in (None, "") else None,
                "accountId": account_id,
                "isDraft": False,
                "isValid": True,
            }
        )
    return out
