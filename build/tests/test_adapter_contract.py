"""Generic contract test: every registered adapter must produce schema-valid output.

For each adapter NAME, this test looks for `tests/fixtures/<NAME>/input.csv`
and feeds it to the adapter's `convert()`. The output must satisfy
wf_csv.validate_adapter_output. Contributors only ship the fixture; the
test runs for free.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src import adapters as adapters_pkg
from src import wf_csv


REGISTRY = adapters_pkg.discover()


@pytest.mark.parametrize("adapter_name", sorted(REGISTRY))
def test_adapter_produces_schema_valid_rows(adapter_name: str, fixtures_dir: Path):
    adapter = REGISTRY[adapter_name]
    input_path = fixtures_dir / adapter_name / "input.csv"
    if not input_path.is_file():
        pytest.skip(f"no fixture for adapter '{adapter_name}', add {input_path} to enable")

    rows = adapter.convert(str(input_path))
    wf_csv.validate_adapter_output(rows, adapter=adapter_name)

    # `account` is the orchestrator's job; adapters must NOT set it.
    for i, row in enumerate(rows, start=1):
        assert "account" not in row, (
            f"{adapter_name} row {i}: adapter must not set `account` "
            f"(orchestrator handles grouping)"
        )


def test_adapter_detect_recognises_its_own_fixture(fixtures_dir: Path):
    """If an adapter exposes detect(), it must recognise its own fixture."""
    for name, adapter in REGISTRY.items():
        if adapter.detect is None:
            continue
        input_path = fixtures_dir / name / "input.csv"
        if not input_path.is_file():
            continue
        assert adapter.detect(str(input_path)), (
            f"adapter '{name}' has detect() but does not match its own fixture"
        )
