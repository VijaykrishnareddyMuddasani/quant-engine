import datetime as dt

import pytest

from quant_engine.backtest import Backtester
from quant_engine.data import ExchangeCalendar, SyntheticMarket, resample_session
from quant_engine.strategy import StrategyLoadError, load_strategy
from quant_engine.strategy.examples import MovingAverageCrossover

EXAMPLE = "quant_engine.strategy.examples:MovingAverageCrossover"


def test_a_strategy_is_loaded_by_import_path_with_its_parameters() -> None:
    strategy = load_strategy(EXAMPLE, {"fast": 3, "slow": 9})
    assert isinstance(strategy, MovingAverageCrossover)
    assert (strategy.fast, strategy.slow) == (3, 9)
    assert strategy.name == "MovingAverageCrossover"


@pytest.mark.parametrize(
    ("spec", "params", "message"),
    [
        ("no_colon_here", None, "module:ClassName"),
        ("quant_engine.does_not_exist:Thing", None, "cannot import"),
        ("quant_engine.core.types:Order", None, "not a Strategy"),
        (EXAMPLE, {"speed": 3}, "bad parameters"),
    ],
)
def test_bad_specs_are_explained(spec: str, params: dict[str, int] | None, message: str) -> None:
    with pytest.raises(StrategyLoadError, match=message):
        load_strategy(spec, params)


def test_crossover_parameters_are_checked() -> None:
    with pytest.raises(ValueError, match="fast < slow"):
        MovingAverageCrossover(fast=20, slow=10)


def test_crossover_holds_one_unit_size_and_is_flat_each_evening() -> None:
    calendar = ExchangeCalendar.nse()
    minutes = SyntheticMarket(calendar, seed=8).minute_bars(
        dt.date(2026, 2, 2), dt.date(2026, 2, 27)
    )
    bars = resample_session(minutes, 15, calendar)
    result = Backtester(MovingAverageCrossover(4, 12, quantity=25)).run(bars)

    assert len(result.trades) > 0
    assert set(result.position.unique()) <= {-25.0, 0.0, 25.0}
    last_of_day = result.position.groupby(result.position.index.date).last()
    assert (last_of_day == 0).all()
