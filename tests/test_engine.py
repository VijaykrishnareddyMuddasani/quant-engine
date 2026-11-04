import numpy as np
import pandas as pd
import pytest

from quant_engine.backtest import BacktestConfig, Backtester, BpsCost, FillModel
from quant_engine.core import Bar, Fill, Order, Side
from quant_engine.data import ExchangeCalendar, SyntheticMarket, resample_session
from quant_engine.strategy import StrategyContext
from quant_engine.strategy.examples import MovingAverageCrossover
from support import MONDAY, TUESDAY, BarAction, Scripted, ohlc_bars

KEEP_OVERNIGHT = BacktestConfig(flatten_at_session_end=False)

FLAT = (100.0, 100.5, 99.5, 100.0)


def buy(qty: float = 1) -> BarAction:
    return lambda bar, ctx: ctx.submit(Order.market(Side.BUY, qty))


def test_a_market_order_fills_at_the_next_bar_open() -> None:
    bars = ohlc_bars([FLAT, (101, 102, 100, 101), FLAT])
    strategy = Scripted(at={0: buy()})
    Backtester(strategy, KEEP_OVERNIGHT).run(bars)
    (fill, *_) = strategy.fills
    assert fill.price == 101.0
    assert fill.time == bars.index[1]


def test_the_strategy_only_ever_sees_completed_bars() -> None:
    bars = ohlc_bars([FLAT] * 5)
    strategy = Scripted()
    Backtester(strategy).run(bars)
    for n, seen in enumerate(strategy.seen):
        assert seen["history_rows"] == n + 1
        assert seen["history_last"] == seen["start"] == bars.index[n]
        assert seen["now"] == bars["available_at"].iloc[n]


def test_an_order_cannot_fill_on_the_bar_that_produced_it() -> None:
    # bar 0's own range would fill a sell stop at 99.6, but the order only exists after bar 0
    bars = ohlc_bars([(100, 101, 99, 100), (100, 100.2, 99.9, 100)])
    stop_now = Scripted(at={0: lambda bar, ctx: ctx.submit(Order.stop(Side.SELL, 1, 99.6))})
    Backtester(stop_now, KEEP_OVERNIGHT).run(bars)
    assert stop_now.fills == []


def test_a_protective_stop_placed_on_entry_can_be_hit_in_the_same_bar() -> None:
    bars = ohlc_bars([FLAT, (100, 100.5, 97, 99.5), FLAT])
    strategy = Scripted(
        at={0: buy(10)},
        on_fill_do=lambda fill, ctx: (
            ctx.submit(Order.stop(Side.SELL, 10, 98.0, tag="stop")) if ctx.position > 0 else None
        ),
    )
    result = Backtester(strategy, KEEP_OVERNIGHT).run(bars)
    (trade,) = result.trades.itertuples()
    assert (trade.entry_price, trade.exit_price, trade.exit_tag) == (100.0, 98.0, "stop")
    assert result.fills["time"].nunique() == 1  # in and out inside bar 1


def test_an_oco_bracket_cancels_the_other_leg() -> None:
    bars = ohlc_bars([FLAT, FLAT, (100, 102.5, 99.8, 102), (102, 102, 90, 90)])

    def bracket(fill: Fill, ctx: StrategyContext) -> None:
        if ctx.position > 0:
            ctx.submit(Order.stop(Side.SELL, 1, 99.0, oco="b", tag="stop"))
            ctx.submit(Order.limit(Side.SELL, 1, 102.0, oco="b", tag="target"))

    strategy = Scripted(at={0: buy()}, on_fill_do=bracket)
    result = Backtester(strategy, KEEP_OVERNIGHT).run(bars)
    assert result.trades["exit_tag"].tolist() == ["target"]
    assert result.position.iloc[-1] == 0  # the stop did not fire on the crash afterwards


def test_intraday_books_are_flat_at_every_session_end() -> None:
    bars = pd.concat([ohlc_bars([FLAT] * 3, MONDAY), ohlc_bars([FLAT] * 3, TUESDAY)])
    strategy = Scripted(at={0: buy(), 3: buy()})
    result = Backtester(strategy).run(bars)
    assert result.trades["exit_tag"].tolist() == ["session end", "session end"]
    assert result.position.iloc[[2, 5]].tolist() == [0, 0]
    assert [s["session_end"] for s in strategy.seen] == [False, False, True] * 2


def test_day_orders_expire_and_good_till_cancelled_orders_carry_over() -> None:
    bars = pd.concat([ohlc_bars([FLAT] * 2, MONDAY), ohlc_bars([(105, 106, 104, 105)], TUESDAY)])

    def place(bar: Bar, ctx: StrategyContext) -> None:
        ctx.submit(Order.market(Side.BUY, 1, tag="day"))
        ctx.submit(Order.market(Side.BUY, 2, tag="gtc", good_till_cancelled=True))

    strategy = Scripted(at={1: place})
    result = Backtester(strategy, KEEP_OVERNIGHT).run(bars)
    # the DAY order died with Monday's session; the GTC order filled at Tuesday's open
    assert [(f.tag, f.quantity, f.price) for f in strategy.fills] == [
        ("gtc", 2, 105.0),
        ("end of data", 2, 105.0),
    ]
    assert result.trades["exit_tag"].tolist() == ["end of data"]


def test_slippage_and_costs_come_off_the_result() -> None:
    bars = ohlc_bars([FLAT, (100, 101, 99, 100), (100, 101, 99, 100)])
    exact = Backtester(Scripted(at={0: buy(10)})).run(bars)
    costly = BacktestConfig(fill_model=FillModel(slippage_bps=10), costs=BpsCost(5))
    paid = Backtester(Scripted(at={0: buy(10)}), costly).run(bars)
    assert exact.trades["net_pnl"].iloc[0] == 0.0
    assert paid.trades["gross_pnl"].iloc[0] == pytest.approx(-10 * 100 * 0.002)
    assert paid.trades["costs"].iloc[0] == pytest.approx(2 * 10 * 100 * 0.0005, rel=1e-3)


def test_blank_bars_are_skipped_and_counted() -> None:
    bars = ohlc_bars([FLAT] * 4)
    bars.iloc[2, :4] = np.nan
    strategy = Scripted()
    result = Backtester(strategy).run(bars)
    assert result.skipped_bars == 1
    assert [s["start"] for s in strategy.seen] == list(bars.index[[0, 1, 3]])


def test_bars_without_a_known_availability_time_are_refused() -> None:
    bars = ohlc_bars([FLAT] * 2)
    with pytest.raises(ValueError, match="available_at"):
        Backtester(Scripted()).run(bars.drop(columns="available_at"))
    bars["available_at"] = bars.index
    with pytest.raises(ValueError, match="after its start"):
        Backtester(Scripted()).run(bars)


def test_final_equity_is_capital_plus_net_pnl() -> None:
    calendar = ExchangeCalendar.nse()
    minutes = SyntheticMarket(calendar, seed=4).minute_bars(MONDAY, MONDAY + pd.Timedelta(days=11))
    bars = resample_session(minutes, 5, calendar)
    config = BacktestConfig(fill_model=FillModel(slippage_bps=1), costs=BpsCost(2))
    result = Backtester(MovingAverageCrossover(5, 20, quantity=10), config).run(bars)
    assert len(result.trades) > 10
    assert result.equity.iloc[-1] == pytest.approx(
        config.initial_capital + result.trades["net_pnl"].sum()
    )
    again = Backtester(MovingAverageCrossover(5, 20, quantity=10), config).run(bars)
    pd.testing.assert_frame_equal(result.trades, again.trades)
