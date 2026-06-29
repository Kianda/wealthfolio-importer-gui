"""Validation tests for the wf-config.yml loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from src import config


def _write(tmp_path: Path, yaml_text: str) -> Path:
    p = tmp_path / "wf-config.yml"
    p.write_text(yaml_text, encoding="utf-8")
    return p


def test_rejects_symbol_routed_to_multiple_accounts(tmp_path: Path):
    cfg_path = _write(
        tmp_path,
        """
        accounts:
          default: cash
          rules:
            - account: long-term
              symbols: [SWDA.MI]
            - account: speculative
              symbols: [SWDA.MI]
        """,
    )
    with pytest.raises(config.ConfigError, match="multiple accounts"):
        config.load(cfg_path)


def test_allows_same_symbol_listed_under_same_account(tmp_path: Path):
    """Style smell, not a logic error - accept it without complaint."""
    cfg_path = _write(
        tmp_path,
        """
        accounts:
          default: cash
          rules:
            - account: long-term
              symbols: [SWDA.MI]
            - account: long-term
              symbols: [SWDA.MI, EM35.MI]
        """,
    )
    cfg = config.load(cfg_path)
    assert cfg.accounts.assign("SWDA.MI") == "long-term"
    assert cfg.accounts.assign("EM35.MI") == "long-term"


def test_rejects_missing_default(tmp_path: Path):
    cfg_path = _write(
        tmp_path,
        """
        accounts:
          rules:
            - account: long-term
              symbols: [SWDA.MI]
        """,
    )
    with pytest.raises(config.ConfigError, match="default"):
        config.load(cfg_path)


def test_reports_missing_file():
    with pytest.raises(config.ConfigError, match="not found"):
        config.load(Path("/nonexistent/wf-config.yml"))
