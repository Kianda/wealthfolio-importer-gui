"""HTTP client for the Wealthfolio self-hosted API.

Endpoints (verified against wealthfolio/wealthfolio source as of 3.4.0):
  POST /api/v1/auth/login              -> sets HttpOnly session cookie
  GET  /api/v1/accounts                -> list accounts
  POST /api/v1/activities/import/check -> validate + enrich rows
  POST /api/v1/activities/import       -> commit

The check endpoint enriches each activity with `assetId`, `quoteCcy`,
`instrumentType`. The commit-side validator REQUIRES those for BUY
rows, so we forward the enriched response, not the original payload.

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
