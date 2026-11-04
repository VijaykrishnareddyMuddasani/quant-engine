"""How working orders fill against a bar.

A bar hides the path the price took inside it. Every rule here settles that ambiguity against the
strategy, so a backtest can disappoint in live trading only by luck, not by construction:

* An order fills no earlier than the bar after the one whose close produced it.
* MARKET orders fill at the bar's open, plus slippage.
* A STOP the bar opens through fills at the open, not at its trigger: a gap is not a gift.
  Touched inside the bar, it fills at the trigger plus slippage.
* A LIMIT has to trade *through* its price by a tick to count. Touching it is not enough, because
  the queue ahead of the order may have taken everything at that price. It fills at its price, or
  at the open if the bar opens better.
* When a stop and a limit could both trigger in the same bar, the stop is taken to have hit first.
* A protective stop placed in reaction to a fill inside a bar may trigger in the rest of that bar
  (``stop_after_fill``); a limit placed the same way waits for the next bar.
"""

from __future__ import annotations

from dataclasses import dataclass

from quant_engine.core.types import Bar, Order, OrderType, Side

# Processing order inside one bar: market orders execute at the open, before anything else can
# happen; stops before limits, because the adverse path is assumed.
PRIORITY = {OrderType.MARKET: 0, OrderType.STOP: 1, OrderType.LIMIT: 2}


@dataclass(frozen=True)
class FillModel:
    slippage_bps: float = 0.0
    tick: float = 0.05
    limit_needs_trade_through: bool = True

    def __post_init__(self) -> None:
        if self.slippage_bps < 0 or self.tick <= 0:
            raise ValueError("slippage_bps must be >= 0 and tick > 0")

    def adverse(self, price: float, side: Side) -> float:
        """``price`` moved against an order on ``side`` by the slippage."""
        return price * (1.0 + side * self.slippage_bps / 10_000.0)

    def fill_price(self, order: Order, bar: Bar) -> float | None:
        """The price ``order`` fills at during ``bar``, or None if it does not fill."""
        if order.type is OrderType.MARKET:
            return self.adverse(bar.open, order.side)
        if order.price is None:  # Order already refuses this; the check narrows the type
            raise ValueError(f"a {order.type.value} order needs a price")
        level = order.price
        if order.type is OrderType.STOP:
            if order.side is Side.BUY:
                if bar.open >= level:
                    return self.adverse(bar.open, order.side)
                return self.adverse(level, order.side) if bar.high >= level else None
            if bar.open <= level:
                return self.adverse(bar.open, order.side)
            return self.adverse(level, order.side) if bar.low <= level else None

        through = self.tick if self.limit_needs_trade_through else 0.0
        if order.side is Side.BUY:
            if bar.open <= level:
                return bar.open
            return level if bar.low <= level - through else None
        if bar.open >= level:
            return bar.open
        return level if bar.high >= level + through else None

    def stop_after_fill(self, order: Order, bar: Bar, reference: float) -> float | None:
        """A STOP placed in reaction to a fill at ``reference`` inside ``bar``.

        What the bar did after the fill is unknown, so the worst is assumed: if the bar's range
        reaches the trigger, it was hit after the fill. A trigger already on the wrong side of
        ``reference`` is marketable at once.
        """
        if order.type is not OrderType.STOP or order.price is None:
            raise ValueError("stop_after_fill only handles stop orders")
        level = order.price
        if order.side is Side.BUY:
            if level <= reference:
                return self.adverse(reference, order.side)
            return self.adverse(level, order.side) if bar.high >= level else None
        if level >= reference:
            return self.adverse(reference, order.side)
        return self.adverse(level, order.side) if bar.low <= level else None
