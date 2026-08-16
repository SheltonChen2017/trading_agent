from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import pytest

from data import pit_universe
from scripts import run_alpha_battery_20260815 as battery
from scripts import run_alpha_universes_20260816 as universes


def _classification_cell(sharpe: float) -> dict:
    return {
        "usable": True,
        "constructions": {
            "long_short": {"net": {"10bps": {"sharpe": sharpe}}}
        },
    }


def test_default_bootstrap_can_resolve_declared_bonferroni_threshold() -> None:
    draws = inspect.signature(battery.stationary_bootstrap_p).parameters["draws"].default

    assert 1.0 / (draws + 1) < 0.05 / battery.DECLARED_LOOKS


@pytest.mark.parametrize("draws", [0, -1, True, 1.5])
def test_bootstrap_refuses_invalid_draw_counts(draws) -> None:
    with pytest.raises(battery.BatteryError, match="positive integer"):
        battery.stationary_bootstrap_p(pd.Series(np.arange(30.0)), draws=draws)


def test_long_short_turnover_counts_a_long_short_side_flip() -> None:
    dates = pd.to_datetime(["2025-01-02", "2025-01-03"])
    names = [f"S{i:02d}" for i in range(20)]
    first = np.arange(20, dtype=float)
    scores = pd.DataFrame([first, -first], index=dates, columns=names)
    forwards = pd.DataFrame(0.01, index=dates, columns=names)

    _, turnover = battery.long_short_returns(
        scores, forwards, dates, "long_short", horizon=1
    )

    assert turnover.iloc[1] == 1.0


def test_edgar_fact_is_not_usable_before_its_actual_filing_date(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(pit_universe, "quarter_labels", lambda *_: ["2020Q1I"])
    monkeypatch.setattr(
        pit_universe,
        "_get_json",
        lambda *_args, **_kwargs: {
            "data": [
                {
                    "cik": 1,
                    "entityName": "Example",
                    "loc": "US-CA",
                    "end": "2020-03-31",
                    "filed": "2020-05-15",
                    "accn": "0001",
                    "val": 100,
                }
            ]
        },
    )

    facts = pit_universe.fetch_shares_outstanding(tmp_path, 2020, 2020)

    assert facts.loc[0, "known_from"] == pd.Timestamp("2020-05-15")
    assert pit_universe.shares_as_of(facts, pd.Timestamp("2020-05-14")).empty


def test_snapshot_uses_unadjusted_price_for_market_cap() -> None:
    date = pd.Timestamp("2025-01-31")
    shares = pd.DataFrame(
        {
            "cik": [1],
            "period_end": [pd.Timestamp("2024-12-31")],
            "known_from": [pd.Timestamp("2025-01-01")],
            "accession": ["0001"],
            "shares": [1_000_000_000],
        }
    )
    ticker_map = pd.DataFrame({"cik": [1], "ticker": ["ABC"]})
    adjusted = pd.DataFrame({"ABC": [4.0]}, index=[date])
    unadjusted = pd.DataFrame({"ABC": [40.0]}, index=[date])
    adv = pd.DataFrame({"ABC": [30_000_000.0]}, index=[date])

    snapshot = pit_universe.build_snapshot(
        as_of=date,
        universe="A_large",
        shares=shares,
        ticker_map=ticker_map,
        closes=adjusted,
        screen_closes=unadjusted,
        dollar_volume_20=adv,
        min_history_days=0,
    )

    assert snapshot.tickers == ("ABC",)
    assert snapshot.market_caps["ABC"] == 40_000_000_000.0


def test_classifier_does_not_call_near_zero_broad_results_robust() -> None:
    cells = {
        "A_large": _classification_cell(0.27),
        "B_core": _classification_cell(0.02),
        "C_broad": _classification_cell(0.001),
    }

    assert universes.classify(cells) == "LARGE-CAP DEPENDENT"


def test_universe_runner_refuses_a_pre_correction_membership_cache(
    monkeypatch, tmp_path
) -> None:
    index = pd.to_datetime(["2025-01-02"])
    frames = iter(
        [
            pd.DataFrame({"ABC": [10.0]}, index=index),
            pd.DataFrame({"ABC": [100.0]}, index=index),
            pd.DataFrame(
                {"as_of": index, "universe": ["B_core"], "ticker": ["ABC"]}
            ),
        ]
    )
    monkeypatch.setattr(universes.pd, "read_parquet", lambda *_: next(frames))

    with pytest.raises(SystemExit, match="predates the reviewed universe schema"):
        universes.load_panels(tmp_path)
