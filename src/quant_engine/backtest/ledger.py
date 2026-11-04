"""Cash, position and round-trip bookkeeping for one instrument.

A *trade* runs from flat back to flat. Adds and partial exits in between belong to the same trade,
and its prices are quantity-weighted averages. A fill that reverses the position closes the trade
in full and opens the next one with the remainder; its charges are split between the two in
proportion to quantity.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quant_engine.core.types import Fill, Trade

# Quantities closer to zero than this are zero (floating-point residue of partial exits).
QUANTITY_EPSILON = 1e-9


@dataclass
class _OpenTrade:
    direction: int
    entry_time: pd.Timestamp
    entry_bar: int
    entry_tag: str
    entry_quantity: float = 0.0
    entry_value: float = 0.0
    exit_quantity: float = 0.0
    exit_value: float = 0.0
    costs: float = 0.0


class Ledger:
    def __init__(self, initial_capital: float) -> None:
        self.cash = float(initial_capital)
        self.position = 0.0
        self.trades: list[Trade] = []
        self._open: _OpenTrade | None = None

    def equity(self, mark: float) -> float:
        """Cash plus the position valued at ``mark``."""
        return self.cash + self.position * mark

    def apply(self, fill: Fill, bar_index: int) -> None:
        signed = fill.signed_quantity
        self.cash -= signed * fill.price + fill.cost
        if self.position == 0 or (self.position > 0) == (signed > 0):
            self._add(fill, abs(signed), fill.cost, bar_index)
            self.position += signed
            return

        closing = min(abs(signed), abs(self.position))
        opening = abs(signed) - closing
        closing_cost = fill.cost * closing / abs(signed)
        self._reduce(fill, closing, closing_cost, bar_index)
        self.position += signed
        if abs(self.position) < QUANTITY_EPSILON:
            self.position = 0.0
        if opening > QUANTITY_EPSILON:
            self._add(fill, opening, fill.cost - closing_cost, bar_index)

    def _add(self, fill: Fill, quantity: float, cost: float, bar_index: int) -> None:
        if self._open is None:
            self._open = _OpenTrade(int(fill.side), fill.time, bar_index, fill.tag)
        self._open.entry_quantity += quantity
        self._open.entry_value += quantity * fill.price
        self._open.costs += cost

    def _reduce(self, fill: Fill, quantity: float, cost: float, bar_index: int) -> None:
        trade = self._open
        if trade is None:
            raise RuntimeError("reducing a position that the ledger does not hold")
        trade.exit_quantity += quantity
        trade.exit_value += quantity * fill.price
        trade.costs += cost
        if trade.exit_quantity < trade.entry_quantity - QUANTITY_EPSILON:
            return
        self.trades.append(
            Trade(
                direction=trade.direction,
                quantity=trade.entry_quantity,
                entry_time=trade.entry_time,
                exit_time=fill.time,
                entry_price=trade.entry_value / trade.entry_quantity,
                exit_price=trade.exit_value / trade.exit_quantity,
                gross_pnl=trade.direction * (trade.exit_value - trade.entry_value),
                costs=trade.costs,
                bars_held=bar_index - trade.entry_bar,
                entry_tag=trade.entry_tag,
                exit_tag=fill.tag,
            )
        )
        self._open = None
