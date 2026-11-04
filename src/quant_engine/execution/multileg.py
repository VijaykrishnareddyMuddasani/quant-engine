"""Multi-leg orders: several instruments that only make sense together.

The legs run one at a time in a stated order. With the default ``protective_first`` order, the
legs that limit risk (bought options, hedges) go before the legs that add it, so a failure part
way through leaves the book less exposed, not more; buying protection first also lowers the
margin the later legs need.

If a *required* leg does not fill completely, every leg already filled (including the failed leg's
partial fill) is reversed, newest first, and the result says so. An optional leg may fail without
undoing the rest. Rollbacks are reported, never silent: a rollback that itself fails leaves an
unbalanced book that someone must see.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from quant_engine.core.types import Side
from quant_engine.execution.orders import Execution, OrderExecutor


@dataclass(frozen=True)
class Leg:
    symbol: str
    side: Side
    quantity: int
    protective: bool = False
    required: bool = True


@dataclass(frozen=True)
class MultiLegResult:
    executions: tuple[Execution, ...]
    rollbacks: tuple[Execution, ...]
    complete: bool
    reason: str = ""

    @property
    def balanced(self) -> bool:
        """True when every rollback undid its leg in full (or none was needed)."""
        return all(r.complete for r in self.rollbacks)


class MultiLegExecutor:
    ORDERS = ("protective_first", "as_given")

    def __init__(self, executor: OrderExecutor, order: str = "protective_first") -> None:
        if order not in self.ORDERS:
            raise ValueError(f"order must be one of {self.ORDERS}")
        self.executor = executor
        self.order = order

    def sequence(self, legs: Sequence[Leg]) -> list[Leg]:
        if self.order == "as_given":
            return list(legs)
        return sorted(legs, key=lambda leg: not leg.protective)  # stable: keeps the given order

    def execute(self, legs: Sequence[Leg], product: str = "MIS") -> MultiLegResult:
        done: list[Execution] = []
        for leg in self.sequence(legs):
            execution = self.executor.execute(leg.symbol, leg.side, leg.quantity, product)
            done.append(execution)
            if execution.complete or not leg.required:
                continue
            rollbacks = tuple(
                self.executor.execute(e.symbol, e.side.opposite, e.filled, product)
                for e in reversed(done)
                if e.filled > 0
            )
            reason = f"{leg.side.name} {leg.symbol}: {execution.reason or 'not filled'}"
            return MultiLegResult(tuple(done), rollbacks, False, reason)
        return MultiLegResult(tuple(done), (), True)
