"""Loader and validator for `wf-config.yml`.

The config file maps WF symbols to account names and (optionally) sets
the Wealthfolio server URL. Sensitive values (passwords) MUST come from
environment variables, not from the config file.

Example wf-config.yml:

    wealthfolio:
      base_url: http://localhost:24568

    accounts:
      default: cash
      rules:
        - account: long-term
          symbols: [SWDA.MI, EM35.MI, SGLN.MI]
        - account: cash
          symbols: [XEON.MI, C3M.MI]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


class ConfigError(ValueError):
    """Raised when wf-config.yml is missing required fields or malformed."""


@dataclass(frozen=True)
class AccountRule:
    account: str
    symbols: frozenset[str]


@dataclass(frozen=True)
class AccountsConfig:
    default: str
    rules: tuple[AccountRule, ...] = ()

    def assign(self, symbol: str) -> str:
        """Return the account name a row with this symbol belongs to.

        First rule whose `symbols` list contains the symbol wins; falls
        back to `default` otherwise. Empty/None symbols (cash flows)
        also fall through to default unless explicitly matched.
        """
        for rule in self.rules:
            if symbol in rule.symbols:
                return rule.account
        return self.default


@dataclass(frozen=True)
class WealthfolioConfig:
    base_url: str = "http://localhost:24568"
    external_url: str | None = None


@dataclass(frozen=True)
class Config:
    accounts: AccountsConfig
    wealthfolio: WealthfolioConfig = field(default_factory=WealthfolioConfig)


def load(path: Path) -> Config:
    if not path.exists():
        raise ConfigError(
            f"Config file not found: {path}\n"
            f"Copy wf-config.example.yml to wf-config.yml at the repo root."
        )
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return _from_dict(raw, source=str(path))


def _from_dict(raw: dict, *, source: str) -> Config:
    if not isinstance(raw, dict):
        raise ConfigError(f"{source}: root must be a mapping")

    accounts_raw = raw.get("accounts")
    if not isinstance(accounts_raw, dict):
        raise ConfigError(f"{source}: missing or invalid top-level `accounts:` block")

    default = accounts_raw.get("default")
    if not isinstance(default, str) or not default.strip():
        raise ConfigError(f"{source}: `accounts.default` is required and must be a non-empty string")

    rules_raw = accounts_raw.get("rules", []) or []
    if not isinstance(rules_raw, list):
        raise ConfigError(f"{source}: `accounts.rules` must be a list")

    rules: list[AccountRule] = []
    seen_symbols: dict[str, str] = {}  # symbol -> first account it appears in
    for i, rule_raw in enumerate(rules_raw):
        where = f"{source}: accounts.rules[{i}]"
        if not isinstance(rule_raw, dict):
            raise ConfigError(f"{where}: must be a mapping")
        account = rule_raw.get("account")
        if not isinstance(account, str) or not account.strip():
            raise ConfigError(f"{where}: `account` is required")
        symbols = rule_raw.get("symbols")
        if not isinstance(symbols, list) or not all(isinstance(s, str) for s in symbols):
            raise ConfigError(f"{where}: `symbols` must be a list of strings")
        account = account.strip()
        # Same symbol routed to *different* accounts is ambiguous and we
        # refuse to guess. Same symbol → same account across rules is a
        # style smell but harmless, so we allow it.
        for symbol in symbols:
            previous = seen_symbols.get(symbol)
            if previous is not None and previous != account:
                raise ConfigError(
                    f"{source}: symbol '{symbol}' is routed to multiple accounts "
                    f"('{previous}' and '{account}'). Each symbol must map to exactly "
                    f"one account. See LIMITATIONS.md for the multi-account workaround."
                )
            seen_symbols[symbol] = account
        rules.append(AccountRule(account=account, symbols=frozenset(symbols)))

    wf_raw = raw.get("wealthfolio") or {}
    if not isinstance(wf_raw, dict):
        raise ConfigError(f"{source}: `wealthfolio` must be a mapping if set")
    base_url = wf_raw.get("base_url", "http://localhost:24568")
    if not isinstance(base_url, str):
        raise ConfigError(f"{source}: `wealthfolio.base_url` must be a string")
    external_url = wf_raw.get("external_url")
    if external_url is not None and not isinstance(external_url, str):
        raise ConfigError(f"{source}: `wealthfolio.external_url` must be a string")

    return Config(
        accounts=AccountsConfig(default=default.strip(), rules=tuple(rules)),
        wealthfolio=WealthfolioConfig(
            base_url=base_url.rstrip("/"),
            external_url=external_url.rstrip("/") if external_url else None,
        ),
    )
