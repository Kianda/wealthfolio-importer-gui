"""Adapter discovery and registry.

Each adapter is a single module in this package exposing:
  NAME: str
  DESCRIPTION: str
  AUTO_INJECT_DEPOSITS: bool
  detect(path: str) -> bool   # optional
  convert(path: str) -> list[dict]
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Callable


@dataclass(frozen=True)
class Adapter:
    name: str
    description: str
    auto_inject_deposits: bool
    detect: Callable[[str], bool] | None
    convert: Callable[[str], list[dict[str, Any]]]


class AdapterError(RuntimeError):
    """Raised when an adapter module is missing required attributes."""


def _load(module: ModuleType) -> Adapter:
    for attr in ("NAME", "DESCRIPTION", "AUTO_INJECT_DEPOSITS", "convert"):
        if not hasattr(module, attr):
            raise AdapterError(f"adapter '{module.__name__}' missing required attribute: {attr}")
    if not callable(module.convert):
        raise AdapterError(f"adapter '{module.__name__}': convert must be callable")
    detect = getattr(module, "detect", None)
    if detect is not None and not callable(detect):
        raise AdapterError(f"adapter '{module.__name__}': detect must be callable if defined")
    return Adapter(
        name=module.NAME,
        description=module.DESCRIPTION,
        auto_inject_deposits=bool(module.AUTO_INJECT_DEPOSITS),
        detect=detect,
        convert=module.convert,
    )


def discover() -> dict[str, Adapter]:
    """Scan this package for adapter modules and return {NAME: Adapter}."""
    registry: dict[str, Adapter] = {}
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{__name__}.{info.name}")
        adapter = _load(module)
        if adapter.name in registry:
            raise AdapterError(
                f"duplicate adapter NAME '{adapter.name}' in "
                f"{module.__name__} and {registry[adapter.name].convert.__module__}"
            )
        registry[adapter.name] = adapter
    return registry


def select(registry: dict[str, Adapter], path: str, broker: str | None) -> Adapter:
    """Pick the right adapter for an input file.

    If `broker` is set, look it up by name (fail if unknown).
    Otherwise try each adapter's `detect()`; require exactly one match.
    """
    if broker is not None:
        if broker not in registry:
            raise AdapterError(
                f"unknown broker '{broker}'. Registered: {sorted(registry)}"
            )
        return registry[broker]

    matches = [a for a in registry.values() if a.detect is not None and a.detect(path)]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise AdapterError(
            f"no adapter matched {path}. Pass --broker to force one of: {sorted(registry)}"
        )
    raise AdapterError(
        f"multiple adapters matched {path}: {[a.name for a in matches]}. "
        f"Pass --broker to disambiguate."
    )
