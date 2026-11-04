"""A textbook moving-average crossover, here to show the plug-in interface, not to make money.

Long while the fast simple moving average of closes is above the slow one, short (or flat) while
it is below. The position flips only when the averages cross, so it is always in the market once
enough bars have been seen. Combined with the engine's session-end flattening it becomes an
intraday system that re-enters on the first bar of each day.
"""

from __future__ import annotations

from quant_engine.core.types import Bar
from quant_engine.strategy.base import Strategy, StrategyContext, trade_to


class MovingAverageCrossover(Strategy):
    def __init__(
        self, fast: int = 10, slow: int = 30, quantity: float = 1.0, allow_short: bool = True
    ) -> None:
        if not 0 < fast < slow:
            raise ValueError(f"need 0 < fast < slow, got fast={fast}, slow={slow}")
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        self.fast, self.slow = fast, slow
        self.quantity = quantity
        self.allow_short = allow_short

    def on_bar(self, bar: Bar, ctx: StrategyContext) -> None:
        if ctx.is_session_end or ctx.working_orders:
            return
        closes = ctx.history(self.slow)["close"]
        if len(closes) < self.slow:
            return
        fast_ma, slow_ma = closes.iloc[-self.fast :].mean(), closes.mean()
        if fast_ma > slow_ma:
            trade_to(ctx, self.quantity, tag="fast above slow")
        elif fast_ma < slow_ma:
            trade_to(ctx, -self.quantity if self.allow_short else 0.0, tag="fast below slow")
