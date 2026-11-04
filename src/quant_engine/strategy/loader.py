"""Load a strategy by import path, so strategy code can live in a different package.

A spec looks like ``package.module:ClassName``. The engine never imports a concrete strategy
itself: a private strategy is installed as its own package (``pip install -e path/to/private``)
and named in a config file that also stays private. Nothing about it enters this repository.
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from typing import Any

from quant_engine.strategy.base import Strategy


class StrategyLoadError(ImportError):
    """The spec does not name an importable Strategy subclass."""


def load_strategy(spec: str, params: Mapping[str, Any] | None = None) -> Strategy:
    """Import the class ``spec`` names and construct it with ``params`` as keyword arguments."""
    module_name, sep, class_name = spec.partition(":")
    if not sep or not module_name or not class_name:
        raise StrategyLoadError(f"strategy spec {spec!r} is not of the form 'module:ClassName'")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise StrategyLoadError(f"cannot import {module_name!r} for strategy {spec!r}") from exc
    cls = getattr(module, class_name, None)
    if not (isinstance(cls, type) and issubclass(cls, Strategy)):
        raise StrategyLoadError(f"{spec!r} is not a Strategy subclass")
    try:
        return cls(**dict(params or {}))
    except TypeError as exc:
        raise StrategyLoadError(f"bad parameters for {spec!r}: {exc}") from exc
