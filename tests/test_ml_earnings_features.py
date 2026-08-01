"""Tests for ml/earnings_features.py (ML-LR-4 sections 10.1/10.4).

Covers plan 10.6's applicable items: timezone and DST event mapping;
holiday/weekend and missing-session refusal; duplicate event instants count
once; future revisions and transcripts are rejected from pre-event features;
and no event output alters a proposal or blackout rule.
"""
from __future__ import annotations

from types import MappingProxyType

import numpy as np
import pandas as pd
import pytest

from ml.earnings_features import (
    EarningsFeatureError,
    EarningsGapForecast,
    EventFeatureRow,
    EventIdentity,
    assert_pre_event_feature_names,
    build_pre_event_features,
    deduplicate_events,
    event_frame,
    summarize_event_support,
)
from ml.earnings_gap import GapObservation


def _price(n: int = 60, *, start: str = "2026-01-05", seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.bdate_range(start, periods=n)
    close = 100.0 * np.cumprod(1 + rng.normal(0, 0.015, n))
    return pd.DataFrame(
        {
            "open": close * (1 + rng.normal(0, 0.002, n)),
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": rng.integers(1_000_000, 3_000_000, n).astype(float),
        },
        index=index,
    )


def _identity(**overrides) -> EventIdentity:
    payload = dict(
        ticker="NVDA",
        announced_at="2026-02-25T21:30:00+00:00",  # after close ET
        source_id="vendor-a",
        source_event_id="q4-2025",
    )
    payload.update(overrides)
    return EventIdentity.build(**payload)


# --- event identity ---------------------------------------------------------


def test_timezone_equivalent_instants_are_one_event():
    """Plan 10.1: 'Deduplicate timezone-equivalent instants.' Counting the
    same announcement twice inflates the sample the experiment's power rests
    on."""
    utc = _identity(announced_at="2026-02-25T21:30:00+00:00")
    eastern = _identity(announced_at="2026-02-25T16:30:00-05:00")
    assert utc.event_id == eastern.event_id
    assert len(deduplicate_events([utc, eastern])) == 1


def test_different_events_keep_different_identities():
    first = _identity(source_event_id="q4-2025")
    second = _identity(source_event_id="q1-2026")
    assert first.event_id != second.event_id
    assert len(deduplicate_events([first, second])) == 2


def test_a_different_source_is_a_different_event_record():
    a = _identity(source_id="vendor-a")
    b = _identity(source_id="vendor-b")
    assert a.event_id != b.event_id


def test_a_naive_announcement_instant_is_refused_rather_than_guessed():
    """A naive instant cannot be classified before-open vs after-close
    without guessing, and that classification determines the entire gap
    window."""
    with pytest.raises(EarningsFeatureError, match="timezone-naive"):
        _identity(announced_at="2026-02-25T21:30:00")


def test_an_unparseable_instant_is_refused():
    with pytest.raises(EarningsFeatureError, match="not a parseable timestamp"):
        _identity(announced_at="not-a-date")


def test_identity_normalizes_to_utc_and_round_trips():
    identity = _identity(announced_at="2026-02-25T16:30:00-05:00")
    assert identity.announced_at_utc.endswith("+00:00")
    assert identity.to_dict()["event_id"] == identity.event_id


def test_constructing_identity_directly_with_a_non_utc_offset_is_refused():
    with pytest.raises(EarningsFeatureError, match="normalized to UTC"):
        EventIdentity(
            ticker="NVDA", announced_at_utc="2026-02-25T16:30:00-05:00",
            source_id="v", source_event_id="q4",
        )


def test_direct_identity_construction_cannot_bypass_canonical_utc_format():
    with pytest.raises(EarningsFeatureError, match="canonical UTC representation"):
        EventIdentity(
            ticker="NVDA", announced_at_utc="2026-02-25T21:30:00Z",
            source_id="v", source_event_id="q4",
        )


def test_identity_rejects_surrounding_ticker_whitespace():
    with pytest.raises(EarningsFeatureError, match="surrounding whitespace"):
        _identity(ticker=" NVDA ")


def test_lowercase_ticker_is_refused():
    with pytest.raises(EarningsFeatureError, match="canonical uppercase"):
        _identity(ticker="nvda")


# --- prohibited feature names (plan 10.1) -----------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "post_release_close", "postReleaseClose", "post-release-price",
        "transcript_sentiment", "revised_consensus_eps", "later_filing_revenue",
        "actual_gap_pct", "reported_eps_actual", "future_return",
    ],
)
def test_post_release_feature_names_are_rejected(name):
    """Each of these is a plausible-looking feature someone adds BECAUSE it
    is predictive -- which is exactly the problem."""
    with pytest.raises(EarningsFeatureError, match="post-release information"):
        assert_pre_event_feature_names([name])


@pytest.mark.parametrize(
    "name",
    [
        "pre_event_volatility_pct", "prior_absolute_gap_mean_pct",
        "prior_signed_gap_mean_pct", "sessions_since_prior_event",
        "pre_event_residual_momentum_pct", "pre_event_volume_ratio",
    ],
)
def test_legitimate_pre_event_names_are_allowed(name):
    assert_pre_event_feature_names([name])


def test_prior_gap_features_are_allowed_because_they_describe_earlier_events():
    """'gap' is a prohibited token, but a PRIOR gap is a legitimate
    pre-event feature -- the allowlist is explicit rather than accidental."""
    assert_pre_event_feature_names(["prior_absolute_gap_mean_pct"])
    with pytest.raises(EarningsFeatureError):
        assert_pre_event_feature_names(["absolute_gap_pct"])


# --- pre-event feature construction ------------------------------------------


def test_an_after_close_release_builds_features_from_prior_sessions_only():
    price = _price(60, start="2026-01-05")
    identity = _identity(announced_at="2026-02-25T21:30:00+00:00")
    row = build_pre_event_features(identity, price=price)

    assert row.available
    assert row.release_timing == "after_close"
    # The cutoff session is the release day itself for an after-close print.
    assert row.as_of_session == "2026-02-25"
    assert "pre_event_volatility_pct" in row.features


def test_a_before_open_release_uses_the_prior_session_as_its_cutoff():
    price = _price(60, start="2026-01-05")
    identity = _identity(announced_at="2026-02-25T11:00:00+00:00")  # 06:00 ET
    row = build_pre_event_features(identity, price=price)

    assert row.available
    assert row.release_timing == "before_open"
    assert row.as_of_session < "2026-02-25"


def test_an_intraday_release_is_unavailable_not_guessed():
    price = _price(60, start="2026-01-05")
    identity = _identity(announced_at="2026-02-25T16:00:00+00:00")  # 11:00 ET
    row = build_pre_event_features(identity, price=price)

    assert not row.available
    assert row.release_timing == "intraday"
    assert any("intraday" in reason for reason in row.refusal_reasons)


def test_a_weekend_release_day_refuses():
    price = _price(60, start="2026-01-05")
    # 2026-02-28 is a Saturday.
    identity = _identity(announced_at="2026-02-28T21:30:00+00:00")
    row = build_pre_event_features(identity, price=price)
    assert not row.available
    assert any("not a trading session" in r for r in row.refusal_reasons)


def test_insufficient_prior_history_refuses():
    price = _price(60, start="2026-01-05")
    # Announce on the third available session -- far too little history.
    identity = _identity(announced_at="2026-01-07T21:30:00+00:00")
    row = build_pre_event_features(identity, price=price, minimum_prior_sessions=20)
    assert not row.available
    assert any("prior sessions" in r for r in row.refusal_reasons)


def test_features_do_not_change_when_future_prices_are_appended():
    """The decisive leakage test: a pre-event row must be identical whether
    or not the post-release future exists in the price frame."""
    identity = _identity(announced_at="2026-02-25T21:30:00+00:00")
    long = _price(60, start="2026-01-05")
    short = long.iloc[:45]

    row_short = build_pre_event_features(identity, price=short)
    row_long = build_pre_event_features(identity, price=long)
    assert row_short.available and row_long.available
    assert row_short.features == row_long.features


def test_timezone_aware_daily_index_uses_the_same_market_sessions():
    price = _price(60, start="2026-01-05")
    aware = price.copy()
    aware.index = aware.index.tz_localize("America/New_York")
    identity = _identity(announced_at="2026-02-25T21:30:00+00:00")

    naive_row = build_pre_event_features(identity, price=price)
    aware_row = build_pre_event_features(identity, price=aware)

    assert aware_row.available
    assert aware_row.as_of_session == naive_row.as_of_session
    assert aware_row.features == naive_row.features


def test_appending_future_sessions_cannot_change_a_pre_event_row():
    """The decisive leakage test, done properly: build ONE frame and slice it,
    so the prefix is byte-identical rather than merely similar.

    An earlier version generated two frames of different length from the same
    seed. Close matched, but volume is drawn later in the RNG stream, so the
    overlap genuinely differed -- the test would have failed for a fixture
    reason while appearing to detect leakage. A leakage test that can fail
    for a non-leakage reason is worse than no test: it trains you to explain
    away real failures."""
    full = _price(60, start="2026-01-05")
    prefix = full.iloc[:45]
    identity = _identity(announced_at="2026-02-25T21:30:00+00:00")

    row_prefix = build_pre_event_features(identity, price=prefix)
    row_full = build_pre_event_features(identity, price=full)

    assert row_prefix.available and row_full.available
    assert row_prefix.features == row_full.features
    assert row_prefix.as_of_session == row_full.as_of_session


def test_only_prior_gaps_contribute_to_prior_gap_features():
    """A gap observed AFTER the cutoff is a future event and must not inform
    this row."""
    price = _price(60, start="2026-01-05")
    identity = _identity(announced_at="2026-02-25T21:30:00+00:00")

    def gap(from_session: str, to_session: str, value: float) -> GapObservation:
        return GapObservation(
            ticker="NVDA", announced_at=f"{from_session}T21:30:00+00:00",
            release_timing="after_close",
            from_session=from_session, to_session=to_session,
            from_price=100.0, to_price=100.0 * (1 + value / 100), gap_pct=value,
        )

    past_only = build_pre_event_features(
        identity, price=price, prior_gaps=[gap("2026-01-20", "2026-01-21", 5.0)]
    )
    with_future = build_pre_event_features(
        identity, price=price,
        prior_gaps=[gap("2026-01-20", "2026-01-21", 5.0),
                    gap("2026-03-20", "2026-03-23", 40.0)],
    )
    assert past_only.features["prior_absolute_gap_mean_pct"] == pytest.approx(5.0)
    assert with_future.features == past_only.features


def test_prior_gap_features_never_mix_another_tickers_history():
    price = _price(60, start="2026-01-05")
    identity = _identity(announced_at="2026-02-25T21:30:00+00:00")

    def gap(ticker: str, value: float) -> GapObservation:
        return GapObservation(
            ticker=ticker, announced_at="2026-01-20T21:30:00+00:00",
            release_timing="after_close", from_session="2026-01-20",
            to_session="2026-01-21", from_price=100.0,
            to_price=100.0 * (1 + value / 100), gap_pct=value,
        )

    own_only = build_pre_event_features(
        identity, price=price, prior_gaps=[gap("NVDA", 5.0)]
    )
    mixed_input = build_pre_event_features(
        identity, price=price,
        prior_gaps=[gap("NVDA", 5.0), gap("MSFT", 40.0)],
    )
    assert mixed_input.features == own_only.features


def test_a_stale_benchmark_cannot_create_misaligned_residual_momentum():
    price = _price(60, start="2026-01-05")
    identity = _identity(announced_at="2026-02-25T21:30:00+00:00")
    benchmark = price["close"].drop(pd.Timestamp("2026-02-25"))

    row = build_pre_event_features(
        identity, price=price, benchmark_close=benchmark
    )

    assert not row.available
    assert any("benchmark close history is incomplete" in r for r in row.refusal_reasons)


def test_available_rows_reject_a_prohibited_feature_name():
    identity = _identity()
    with pytest.raises(EarningsFeatureError, match="post-release information"):
        EventFeatureRow(
            identity=identity, release_timing="after_close",
            as_of_session="2026-02-25", cutoff_at=identity.announced_at_utc,
            features={"post_release_close": 1.0}, available=True,
        )


def test_a_non_finite_feature_is_refused():
    identity = _identity()
    with pytest.raises(EarningsFeatureError, match="finite number"):
        EventFeatureRow(
            identity=identity, release_timing="after_close",
            as_of_session="2026-02-25", cutoff_at=identity.announced_at_utc,
            features={"pre_event_volatility_pct": float("nan")}, available=True,
        )


def test_feature_rows_copy_and_freeze_caller_owned_features():
    identity = _identity()
    features = {"pre_event_volatility_pct": 2.0}
    row = EventFeatureRow(
        identity=identity, release_timing="after_close",
        as_of_session="2026-02-25", cutoff_at=identity.announced_at_utc,
        features=features, available=True,
    )
    features["pre_event_volatility_pct"] = 999.0
    assert row.features["pre_event_volatility_pct"] == 2.0
    assert isinstance(row.features, MappingProxyType)
    with pytest.raises(TypeError):
        row.features["pre_event_volatility_pct"] = 3.0


def test_an_unavailable_row_requires_a_reason():
    identity = _identity()
    with pytest.raises(EarningsFeatureError, match="at least one reason"):
        EventFeatureRow(
            identity=identity, release_timing="intraday", as_of_session="",
            cutoff_at="", features={}, available=False,
        )


# --- frames and support -----------------------------------------------------


def _rows(n: int = 5):
    price = _price(90, start="2026-01-05")
    rows = []
    for index, session in enumerate(("02-20", "02-23", "02-24", "02-25", "02-26")[:n]):
        rows.append(
            build_pre_event_features(
                _identity(
                    ticker=f"T{index}",
                    announced_at=f"2026-{session}T21:30:00+00:00",
                    source_event_id=f"q-{index}",
                ),
                price=price,
            )
        )
    return rows


def test_event_frame_keys_by_event_and_groups_by_session():
    frame = event_frame(_rows())
    assert not frame.empty
    assert frame["event_id"].is_unique
    assert "event_date" in frame.columns
    assert "industry" in frame.columns
    # as_of_session remains the point-in-time cutoff, not the event grouping key.
    assert "as_of_session" in frame.columns


def test_before_open_event_date_differs_from_prior_feature_session():
    price = _price(90, start="2026-01-05")
    row = build_pre_event_features(
        _identity(announced_at="2026-02-25T13:00:00+00:00"),
        price=price,
        industry="Semiconductors",
    )
    frame = event_frame([row])
    assert frame.loc[0, "event_date"] == "2026-02-25"
    assert frame.loc[0, "as_of_session"] == "2026-02-24"
    assert frame.loc[0, "industry"] == "Semiconductors"


def test_event_frame_refuses_duplicate_event_ids():
    rows = _rows(2)
    with pytest.raises(EarningsFeatureError, match="duplicate event_id"):
        event_frame(rows + [rows[0]])


def test_event_frame_excludes_unavailable_rows():
    price = _price(90, start="2026-01-05")
    intraday = build_pre_event_features(
        _identity(announced_at="2026-02-25T16:00:00+00:00"), price=price
    )
    frame = event_frame(_rows() + [intraday])
    assert intraday.identity.event_id not in set(frame["event_id"])


def test_support_counts_distinct_events_not_rows():
    """Plan 10.2: repeated rows do not create independent evidence."""
    rows = _rows()
    summary = summarize_event_support(rows)
    assert summary["distinct_events"] == len(rows)
    assert summary["distinct_tickers"] == len(rows)
    assert "not rows" in summary["note"]


def test_support_reports_refusals_and_release_timing():
    price = _price(90, start="2026-01-05")
    intraday = build_pre_event_features(
        _identity(announced_at="2026-02-25T16:00:00+00:00"), price=price
    )
    summary = summarize_event_support(_rows() + [intraday])
    assert summary["refused_event_count"] == 1
    assert summary["refusal_reason_counts"]
    assert summary["release_timing_counts"]["after_close"] == 5


def test_support_notes_the_minimum_is_not_a_promotion_threshold():
    summary = summarize_event_support(_rows())
    assert "not a promotion threshold" in summary["note"]


# --- typed forecast (plan 10.4) ---------------------------------------------


def _forecast(**overrides) -> EarningsGapForecast:
    payload = dict(
        event_id="a" * 64,
        ticker="NVDA",
        announced_at_utc="2026-02-25T21:30:00+00:00",
        release_timing="after_close",
        as_of_session="2026-02-25",
        target_available_at="2026-02-26T14:30:00+00:00",
        absolute_gap_interval_pct=(2.5, 9.0),
        probability_above_absolute_threshold=0.42,
        probability_below_downside_threshold=0.18,
        absolute_threshold_pct=5.0,
        downside_threshold_pct=-5.0,
        baseline_median_absolute_gap_pct=4.1,
        calibration_status="experimental",
        event_support={"distinct_events": 48, "downside_tail_events": 11},
        model_key="earnings-gap:0.1.0",
        artifact_hash="b" * 64,
        feature_snapshot_hash="c" * 64,
        evidence_status="exploratory",
        available=True,
    )
    payload.update(overrides)
    return EarningsGapForecast(**payload)


def test_the_forecast_carries_no_trade_field():
    payload = _forecast().to_dict()
    forbidden = {"side", "shares", "quantity", "order_type", "limit_price",
                 "stop_price", "approved", "execute", "authorization", "target_weight"}
    assert not (forbidden & set(payload))
    assert payload["production_authoritative"] is False


def test_an_uncalibrated_probability_is_never_labeled_confidence():
    payload = _forecast().to_dict()
    assert "experimental_probability_above_absolute_threshold" in payload
    assert "confidence" not in str(payload).lower()


def test_a_calibrated_forecast_uses_the_calibrated_label():
    payload = _forecast(calibration_status="calibrated").to_dict()
    assert "calibrated_probability_above_absolute_threshold" in payload


def test_the_forecast_states_it_never_overrides_the_blackout():
    """Plan 10.4: 'It must never override the calendar rule or obstruct risk
    reduction.'"""
    text = _forecast().to_dict()["what_this_does_not_mean"]
    assert "never overrides the deterministic earnings blackout" in text
    assert "never delays a risk-reducing sale" in text


def test_an_absolute_gap_interval_cannot_extend_below_zero():
    with pytest.raises(EarningsFeatureError, match="cannot extend below zero"):
        _forecast(absolute_gap_interval_pct=(-1.0, 5.0))


def test_an_unordered_interval_is_refused():
    with pytest.raises(EarningsFeatureError, match="not ordered"):
        _forecast(absolute_gap_interval_pct=(9.0, 2.0))


def test_a_mutable_or_wrong_sized_interval_is_refused():
    with pytest.raises(EarningsFeatureError, match="two-sided"):
        _forecast(absolute_gap_interval_pct=[2.5, 9.0])
    with pytest.raises(EarningsFeatureError, match="two-sided"):
        _forecast(absolute_gap_interval_pct=(2.5, 5.0, 9.0))


def test_an_out_of_range_probability_is_refused():
    with pytest.raises(EarningsFeatureError, match="within \\[0, 1\\]"):
        _forecast(probability_above_absolute_threshold=1.4)


def test_an_unavailable_forecast_requires_a_reason():
    with pytest.raises(EarningsFeatureError, match="at least one refusal reason"):
        _forecast(available=False)
    refused = _forecast(
        available=False, absolute_gap_interval_pct=None,
        probability_above_absolute_threshold=None,
        probability_below_downside_threshold=None,
        baseline_median_absolute_gap_pct=None,
        evidence_status="unavailable",
        refusal_reasons=("intraday release",),
    )
    assert refused.to_dict()["absolute_gap_interval_pct"] is None


def test_the_forecast_carries_its_event_support_and_hashes():
    payload = _forecast().to_dict()
    assert payload["event_support"]["distinct_events"] == 48
    assert payload["model_key"] and payload["artifact_hash"]
    assert payload["feature_snapshot_hash"]


def test_forecast_rejects_invalid_identity_hashes_and_thresholds():
    with pytest.raises(EarningsFeatureError, match="event_id must be"):
        _forecast(event_id="not-a-hash")
    with pytest.raises(EarningsFeatureError, match="absolute_threshold_pct"):
        _forecast(absolute_threshold_pct=float("nan"))
    with pytest.raises(EarningsFeatureError, match="downside_threshold_pct"):
        _forecast(downside_threshold_pct=5.0)


def test_forecast_rejects_invalid_time_and_evidence_states():
    with pytest.raises(EarningsFeatureError, match="must follow"):
        _forecast(target_available_at="2026-02-25T20:00:00+00:00")
    with pytest.raises(EarningsFeatureError, match="normalized to UTC"):
        _forecast(announced_at_utc="2026-02-25T16:30:00-05:00")
    with pytest.raises(EarningsFeatureError, match="recognized non-authoritative"):
        _forecast(evidence_status="confirmed")


def test_forecast_deep_freezes_event_support():
    support = {"distinct_events": 48, "slices": {"year": [2025, 2026]}}
    forecast = _forecast(event_support=support)
    support["slices"]["year"].append(2027)
    assert forecast.to_dict()["event_support"]["slices"]["year"] == [2025, 2026]
    with pytest.raises(TypeError):
        forecast.event_support["distinct_events"] = 49


def test_forecast_and_row_are_json_serializable():
    import json

    json.dumps(_forecast().to_dict())
    json.dumps(_rows(1)[0].to_dict())


# --- no side effects --------------------------------------------------------


def test_building_events_creates_no_files_or_execution_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _rows()
    _forecast()
    assert list(tmp_path.iterdir()) == []


def test_the_module_imports_nothing_execution_capable():
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path("ml/earnings_features.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    forbidden = ("execution", "risk", "assistant.execution_service",
                 "assistant.proposals", "assistant.policy")
    assert not [m for m in imported if any(m == f or m.startswith(f + ".") for f in forbidden)]
