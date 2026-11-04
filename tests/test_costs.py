import pytest

from quant_engine.backtest import (
    SCHEDULES,
    ZERODHA_INDEX_OPTIONS_2026,
    BpsCost,
    ChargeSchedule,
    NoCosts,
)
from quant_engine.core import Side


def test_option_schedule_matches_a_hand_calculation() -> None:
    # 100 units at a premium of 200: turnover 20,000
    sell = ZERODHA_INDEX_OPTIONS_2026.breakdown(Side.SELL, 100, 200.0)
    assert sell["brokerage"] == 20.0
    assert sell["stt"] == pytest.approx(30.0)  # 0.15% of premium, sells only
    assert sell["exchange"] == pytest.approx(7.106)
    assert sell["sebi"] == pytest.approx(0.02)
    assert sell["stamp"] == 0.0
    assert sell["gst"] == pytest.approx(0.18 * (20 + 7.106 + 0.02))
    assert ZERODHA_INDEX_OPTIONS_2026.cost(Side.SELL, 100, 200.0) == pytest.approx(62.00868)

    buy = ZERODHA_INDEX_OPTIONS_2026.breakdown(Side.BUY, 100, 200.0)
    assert buy["stt"] == 0.0
    assert buy["stamp"] == pytest.approx(0.6)


def test_percentage_brokerage_is_capped_by_the_flat_fee() -> None:
    schedule = ChargeSchedule(brokerage_flat=20.0, brokerage_rate=0.0003, gst_rate=0.0)
    assert schedule.breakdown(Side.BUY, 10, 1_000.0)["brokerage"] == pytest.approx(3.0)
    assert schedule.breakdown(Side.BUY, 1_000, 1_000.0)["brokerage"] == 20.0


def test_simple_cost_models() -> None:
    assert BpsCost(2.0).cost(Side.BUY, 50, 20_000.0) == pytest.approx(200.0)
    assert BpsCost(0.0, per_order=20.0).cost(Side.SELL, 1, 1.0) == 20.0
    assert NoCosts().cost(Side.BUY, 1, 1.0) == 0.0
    assert SCHEDULES["zerodha_index_options_2026"] is ZERODHA_INDEX_OPTIONS_2026
