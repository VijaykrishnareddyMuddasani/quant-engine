"""Transaction charges: what one fill costs in account currency, on top of slippage.

Slippage (a worse price) belongs to the fill model; this module covers the cash charged by the
broker, the exchange and the state. Rates are inputs, never constants buried in a backtest: they
change with budgets and exchange circulars, and a result should say which schedule it used.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from quant_engine.core.types import Side

CRORE = 10_000_000


class CostModel(Protocol):
    def cost(self, side: Side, quantity: float, price: float) -> float:
        """Charges for one fill of ``quantity`` units at ``price``."""
        ...


@dataclass(frozen=True)
class NoCosts:
    def cost(self, side: Side, quantity: float, price: float) -> float:
        return 0.0


@dataclass(frozen=True)
class BpsCost:
    """A flat cost in basis points of turnover, plus an optional fixed amount per order."""

    bps: float
    per_order: float = 0.0

    def cost(self, side: Side, quantity: float, price: float) -> float:
        return quantity * price * self.bps / 10_000.0 + self.per_order


@dataclass(frozen=True)
class ChargeSchedule:
    """Indian exchange-traded charges on one order, as rates of its turnover.

    Brokerage is ``brokerage_flat`` per order, or ``min(brokerage_flat, brokerage_rate * turnover)``
    when a rate is given. GST applies to brokerage, the exchange charge and the SEBI fee. STT and
    stamp duty depend on the side.
    """

    brokerage_flat: float = 20.0
    brokerage_rate: float | None = None
    stt_buy_rate: float = 0.0
    stt_sell_rate: float = 0.0
    exchange_rate: float = 0.0
    sebi_per_crore: float = 10.0
    stamp_buy_rate: float = 0.0
    gst_rate: float = 0.18

    def breakdown(self, side: Side, quantity: float, price: float) -> dict[str, float]:
        turnover = quantity * price
        brokerage = self.brokerage_flat
        if self.brokerage_rate is not None:
            brokerage = min(brokerage, self.brokerage_rate * turnover)
        exchange = self.exchange_rate * turnover
        sebi = self.sebi_per_crore * turnover / CRORE
        buying = side is Side.BUY
        return {
            "brokerage": brokerage,
            "stt": (self.stt_buy_rate if buying else self.stt_sell_rate) * turnover,
            "exchange": exchange,
            "sebi": sebi,
            "stamp": self.stamp_buy_rate * turnover if buying else 0.0,
            "gst": self.gst_rate * (brokerage + exchange + sebi),
        }

    def cost(self, side: Side, quantity: float, price: float) -> float:
        return sum(self.breakdown(side, quantity, price).values())


# Zerodha's published charges on NSE index options, in force from April 2026: Rs 20 an order,
# STT 0.15% of premium on sells, NSE transaction charge 0.03553%, SEBI Rs 10 a crore, stamp duty
# 0.003% on buys, GST 18%. Check the broker's charges page before relying on it for a later date.
ZERODHA_INDEX_OPTIONS_2026 = ChargeSchedule(
    brokerage_flat=20.0,
    stt_sell_rate=0.0015,
    exchange_rate=0.0003553,
    sebi_per_crore=10.0,
    stamp_buy_rate=0.00003,
    gst_rate=0.18,
)

SCHEDULES: dict[str, ChargeSchedule] = {
    "zerodha_index_options_2026": ZERODHA_INDEX_OPTIONS_2026,
}
