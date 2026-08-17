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

    # The complete side flip costs 1.0, plus 0.005 to restore gross
    # exposure after both long and short notionals grew by 1% while NAV
    # stayed flat.
    assert turnover.iloc[1] == pytest.approx(1.005)


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


def test_turnover_charges_for_drift_back_to_target_weights() -> None:
    """ABR-002, drift half.

    Codex's correction closed the long/short side-flip half of this
    finding and left the drift half open: comparing last period's TARGET
    weights to this period's targets charges nothing for restoring equal
    weight, even though restoring it is real trading that costs real
    money. Four equal-weight names where one doubles drift to 40/20/20/20,
    and returning them to 25 each is 15% of the book -- previously counted
    as zero, so every net-of-cost number was optimistic.
    """
    from scripts.run_alpha_battery_20260815 import drift_weights, one_way_turnover

    targets = {"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25}
    flat_returns = {"A": 0.0, "B": 0.0, "C": 0.0, "D": 0.0}
    doubled = {"A": 1.0, "B": 0.0, "C": 0.0, "D": 0.0}

    # No drift: holding the same targets through flat returns is free.
    assert one_way_turnover(drift_weights(targets, flat_returns), targets) == 0.0

    drifted = drift_weights(targets, doubled)
    assert drifted["A"] == pytest.approx(0.40)
    assert drifted["B"] == pytest.approx(0.20)
    assert one_way_turnover(drifted, targets) == pytest.approx(0.15)

    # And the side-flip half stays closed.
    long_then_short = one_way_turnover({"A": 0.5}, {"A": -0.5})
    assert long_then_short == pytest.approx(0.5)


def test_drift_weights_survives_a_total_wipeout_without_dividing_by_zero() -> None:
    """A book whose gross exposure goes to zero must not produce NaN
    turnover, which would silently drop the period from the cost series
    and flatter the strategy."""
    from scripts.run_alpha_battery_20260815 import drift_weights

    result = drift_weights({"A": 0.5, "B": 0.5}, {"A": -1.0, "B": -1.0})
    assert result is None


def test_turnover_uses_previous_period_outcomes_without_lookahead() -> None:
    dates = pd.to_datetime(["2025-01-02", "2025-01-03"])
    names = [f"S{i:02d}" for i in range(20)]
    scores = pd.DataFrame(
        [np.arange(20, dtype=float), np.arange(20, dtype=float)],
        index=dates,
        columns=names,
    )
    forwards = pd.DataFrame(0.0, index=dates, columns=names)
    # The first period's highest-ranked name doubles. At the second
    # rebalance, restoring four equal long-only weights costs 15% turnover.
    forwards.loc[dates[0], "S19"] = 1.0

    _, turnover = battery.long_short_returns(
        scores, forwards, dates, "long_only_20", horizon=1
    )

    assert turnover.iloc[1] == pytest.approx(0.15)


def test_universe_portfolio_charges_drift_not_target_to_target_turnover() -> None:
    dates = pd.to_datetime(["2025-01-02", "2025-01-03"])
    names = [f"S{i:02d}" for i in range(20)]
    rows = []
    for date in dates:
        for index, name in enumerate(names):
            rows.append({
                "as_of_session": date,
                "ticker": name,
                "score": float(index),
                "outcome": 1.0 if date == dates[0] and name == "S19" else 0.0,
            })
    _, turnover, _ = universes._portfolio(
        pd.DataFrame(rows), "long_only_20", 0.20
    )

    assert turnover.iloc[1] == pytest.approx(0.15)
