import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from quant_engine.backtest import BpsCost, NoCosts
from quant_engine.backtest.config import ConfigError, RunConfig
from quant_engine.cli import backtest_main
from quant_engine.data import ExchangeCalendar, SyntheticMarket, write_bars

EXAMPLE = Path(__file__).parents[1] / "examples" / "ma_crossover.toml"
SPEC = "quant_engine.strategy.examples:MovingAverageCrossover"


def minimal(**sections: dict[str, object]) -> dict[str, dict[str, object]]:
    raw: dict[str, dict[str, object]] = {
        "data": {"synthetic": {"start": dt.date(2026, 3, 2), "end": dt.date(2026, 3, 6)}},
        "strategy": {"spec": SPEC, "params": {"fast": 3, "slow": 8}},
    }
    raw.update(sections)
    return raw


def test_the_example_config_runs() -> None:
    config = RunConfig.from_toml(EXAMPLE)
    assert config.data.bar_minutes == 15
    assert isinstance(config.backtest.costs, BpsCost)
    result = config.run()
    assert len(result.trades) > 0


def test_defaults_when_sections_are_left_out() -> None:
    config = RunConfig.from_mapping(minimal())
    assert isinstance(config.backtest.costs, NoCosts)
    assert config.backtest.flatten_at_session_end
    assert config.data.bar_minutes == 1


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (minimal(extra={}), "unknown section"),
        (minimal(backtest={"slipage_bps": 1.0}), "unknown key"),
        (minimal(backtest={"costs": {"bps": 1, "schedule": "x"}}), "costs must be"),
        (minimal(backtest={"costs": {"schedule": "nope"}}), "unknown cost schedule"),
        (minimal(strategy={"params": {}}), "needs a spec"),
    ],
)
def test_config_mistakes_are_errors(raw: dict[str, dict[str, object]], message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        RunConfig.from_mapping(raw)


def test_data_needs_exactly_one_source() -> None:
    both = minimal(
        data={"path": "x.csv", "synthetic": {"start": "2026-03-02", "end": "2026-03-06"}}
    )
    with pytest.raises(ConfigError, match="exactly one"):
        RunConfig.from_mapping(both).run()


def test_a_relative_data_path_is_read_from_the_config_folder(tmp_path: Path) -> None:
    calendar = ExchangeCalendar.nse()
    # Wednesday and Thursday (Tuesday 3 March 2026 is Holi)
    write_bars(
        SyntheticMarket(calendar, seed=1).minute_bars(dt.date(2026, 3, 4), dt.date(2026, 3, 5)),
        tmp_path / "bars.csv",
    )
    config_file = tmp_path / "run.toml"
    config_file.write_text(
        f'[data]\npath = "bars.csv"\nbar_minutes = 5\n\n[strategy]\nspec = "{SPEC}"\n'
        "params = { fast = 3, slow = 8 }\n"
    )
    result = RunConfig.from_toml(config_file).run(calendar)
    assert len(result.equity) == 2 * 75


def test_cli_prints_a_report_and_writes_the_trades(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    trades = tmp_path / "trades.csv"
    assert backtest_main([str(EXAMPLE), "--trades", str(trades)]) == 0
    assert "MovingAverageCrossover" in capsys.readouterr().out
    assert len(pd.read_csv(trades)) > 0


def test_cli_reports_a_bad_config_without_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text(
        '[strategy]\nspec = "nowhere:Nothing"\n'
        "[data]\nsynthetic = { start = 2026-03-04, end = 2026-03-05 }\n"
    )
    assert backtest_main([str(bad)]) == 2
    assert "cannot import" in capsys.readouterr().err
