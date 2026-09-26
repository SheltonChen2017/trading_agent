"""Offline SI-2B candidate-window eligibility, never market evidence."""
from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from datetime import date
from functools import lru_cache
from pathlib import Path

import pytest

from data.exchange_calendar import trading_sessions
from data.hashing import hash_payload
from research.short_interest_etf.dataset import (
    build_identity,
    build_vintage,
    load_synthetic_fixture,
)
from research.short_interest_etf.pit_eligibility import (
    build_stock_data_readiness,
    load_synthetic_pit_reference,
)
import research.short_interest_etf.stock_investability as investability_module
from research.short_interest_etf.stock_investability import (
    DailyLiquidityObservation,
    MarketCapObservation,
    StockInvestabilityError,
    SyntheticMarketHistory,
    build_stock_investability,
)


FIXTURES = Path(__file__).parent / "fixtures" / "short_interest_etf"
LOOKBACKS = (20, 60, 120, 252)


@lru_cache(maxsize=1)
def _inputs():
    vintage = load_synthetic_fixture(FIXTURES / "official_style_v1.json")
    references = load_synthetic_pit_reference(FIXTURES / "pit_reference_v1.json")
    security = vintage.snapshots[1].security
    identity = hash_payload(security.to_payload())
    sessions = trading_sessions(date(2022, 11, 1), date(2024, 2, 12))
    daily = tuple(
        DailyLiquidityObservation(
            security_id=security.security_id,
            security_identity_sha256=identity,
            session=session.isoformat(),
            close_usd="100",
            volume_shares=100000,
            available_at=f"{session.isoformat()}T23:00:00Z",
            observed_at=f"{session.isoformat()}T23:00:00Z",
            raw_record_sha256=hash_payload({"synthetic_daily": session.isoformat()}),
        )
        for session in sessions
    )
    caps = tuple(
        MarketCapObservation(
            security_id=security.security_id,
            security_identity_sha256=identity,
            session=session,
            market_cap_usd="300000000",
            available_at=f"{session}T23:00:00Z",
            observed_at=f"{session}T23:00:00Z",
            raw_record_sha256=hash_payload({"synthetic_cap": session}),
        )
        for session in ("2024-01-25", "2024-02-12")
    )
    return vintage, references, SyntheticMarketHistory(daily, caps)


def _build(history=None):
    vintage, references, original = _inputs()
    return build_stock_investability(
        vintage, references, original if history is None else history
    )


def _rows(evidence, event=None):
    vintage, _, _ = _inputs()
    event_id = vintage.snapshots[1].event_id if event is None else event
    return {
        row["lookback_sessions"]: row
        for row in evidence.to_payload()["rows"]
        if row["event_id"] == event_id
    }


def _history(*, daily=None, caps=None):
    original = _inputs()[2]
    return SyntheticMarketHistory(
        original.daily if daily is None else tuple(daily),
        original.capitalizations if caps is None else tuple(caps),
    )


def _revisions(rows, *, price, available, tag):
    return tuple(
        replace(
            row,
            close_usd=price,
            available_at=available,
            observed_at=available,
            raw_record_sha256=hash_payload({tag: row.session}),
        )
        for row in rows
    )


def test_all_four_candidates_are_retained_without_selecting_a_winner():
    vintage, references, history = _inputs()
    evidence = _build()
    payload = evidence.to_payload()
    assert len(payload["rows"]) == len(vintage.snapshots) * len(LOOKBACKS)
    assert set(_rows(evidence)) == set(LOOKBACKS)
    assert payload["selected_lookback"] is None
    assert payload["production_authoritative"] is False
    assert payload["outcome_authorized"] is False
    assert payload["seed_authorized"] is False
    assert payload["source_vintage_sha256"] == build_identity(vintage)["content_hash"]
    assert payload["reference_bundle_sha256"] == references.sha256
    assert payload["market_history_sha256"] == history.sha256
    assert payload["policy_sha256"] == hash_payload(payload["policy"])
    assert evidence.sha256 == payload["evidence_sha256"]
    assert evidence.sha256 == hash_payload(
        {key: value for key, value in payload.items() if key != "evidence_sha256"}
    )
    for count, row in _rows(evidence).items():
        assert row["eligible"] is True
        assert row["refusal_reasons"] == []
        assert row["complete_session_count"] == count
        assert row["window_end_session"] == "2024-02-12"
        assert row["evidence_cutoff_at"] == "2024-02-13T14:30:00Z"
        assert row["median_dollar_volume"] == {"numerator": 10000000, "denominator": 1}
        assert row["market_cap_usd"] == "300000000"


def test_upstream_refusal_is_retained_for_every_candidate():
    vintage, references, _ = _inputs()
    upstream = build_stock_data_readiness(vintage, references)
    assert upstream[0].refusal_reasons == ("missing_authenticated_prior_cycle",)
    for row in _rows(_build(), vintage.snapshots[0].event_id).values():
        assert row["eligible"] is False
        assert "missing_authenticated_prior_cycle" in row["refusal_reasons"]


@pytest.mark.parametrize(
    "cap,eligible",
    [("299999999.99", False), ("300000000", True), ("300000000.01", True)],
)
def test_market_cap_minimum_is_inclusive(cap, eligible):
    caps = [replace(row, market_cap_usd=cap) for row in _inputs()[2].capitalizations]
    assert all(
        row["eligible"] is eligible
        for row in _rows(_build(_history(caps=caps))).values()
    )


@pytest.mark.parametrize(
    "close,eligible",
    [("99.99999999", False), ("100", True), ("100.00000001", True)],
)
def test_liquidity_minimum_uses_exact_decimal_arithmetic(close, eligible):
    daily = [replace(row, close_usd=close) for row in _inputs()[2].daily]
    evidence = _build(_history(daily=daily))
    assert all(row["eligible"] is eligible for row in _rows(evidence).values())


def test_even_window_median_averages_both_middle_values_exactly():
    original = _inputs()[2]
    daily = (
        *original.daily[:-20],
        *(
            replace(row, close_usd="99.99999999" if index < 10 else "100")
            for index, row in enumerate(original.daily[-20:])
        ),
    )
    row = _rows(_build(_history(daily=daily)))[20]
    assert row["median_dollar_volume"] == {
        "numerator": 19999999999, "denominator": 2000
    }
    assert row["eligible"] is False


def test_missing_session_does_not_replenish_window_from_older_history():
    daily = _inputs()[2].daily
    missing = daily[-30].session
    rows = _rows(
        _build(_history(daily=[row for row in daily if row.session != missing]))
    )
    assert rows[20]["eligible"] is True
    for lookback in (60, 120, 252):
        assert rows[lookback]["eligible"] is False
        assert rows[lookback]["complete_session_count"] == lookback - 1
        assert rows[lookback]["median_dollar_volume"] is None
        assert rows[lookback]["refusal_reasons"]


def test_observation_available_exactly_at_open_is_not_visible():
    original = _inputs()[2]
    last = replace(
        original.daily[-1], available_at="2024-02-13T14:30:00Z",
        observed_at="2024-02-13T14:30:00Z",
    )
    rows = _rows(_build(_history(daily=(*original.daily[:-1], last))))
    assert all(row["eligible"] is False for row in rows.values())
    assert all(
        row["complete_session_count"] == count - 1 for count, row in rows.items()
    )


def test_future_revision_cannot_change_the_visible_liquidity_value():
    original = _inputs()[2]
    future = replace(
        original.daily[-1], close_usd="1",
        available_at="2024-02-13T14:30:01Z",
        observed_at="2024-02-13T14:30:01Z", raw_record_sha256="17" * 32,
    )
    rows = _rows(_build(_history(daily=(*original.daily, future))))
    assert all(row["eligible"] is True for row in rows.values())
    assert all(
        row["median_dollar_volume"] == {"numerator": 10000000, "denominator": 1}
        for row in rows.values()
    )


def test_latest_visible_revision_replaces_older_value():
    original = _inputs()[2]
    revised = _revisions(
        original.daily[-252:], price="99",
        available="2024-02-13T14:00:00Z", tag="revision",
    )
    rows = _rows(_build(_history(daily=(*original.daily, *revised))))
    assert all(row["eligible"] is False for row in rows.values())
    assert all(
        row["median_dollar_volume"] == {"numerator": 9900000, "denominator": 1}
        for row in rows.values()
    )


def test_latest_revision_uses_timestamp_order_including_fractional_seconds():
    original = _inputs()[2]
    earlier = _revisions(
        original.daily[-252:], price="100",
        available="2024-02-13T14:00:00Z", tag="earlier",
    )
    later = _revisions(
        original.daily[-252:], price="99",
        available="2024-02-13T14:00:00.500000Z", tag="later",
    )
    rows = _rows(_build(_history(daily=(*original.daily, *earlier, *later))))
    assert all(
        row["median_dollar_volume"] == {"numerator": 9900000, "denominator": 1}
        for row in rows.values()
    )
    assert all(row["eligible"] is False for row in rows.values())


def test_conflicting_equal_availability_revisions_are_ambiguous():
    original = _inputs()[2]
    ambiguous = replace(original.daily[-1], close_usd="101", raw_record_sha256="18" * 32)
    rows = _rows(_build(_history(daily=(*original.daily, ambiguous))))
    assert all(row["eligible"] is False for row in rows.values())
    assert all(row["refusal_reasons"] for row in rows.values())


def test_identity_mismatch_cannot_supply_a_required_session():
    original = _inputs()[2]
    wrong = replace(original.daily[-1], security_identity_sha256="19" * 32)
    rows = _rows(_build(_history(daily=(*original.daily[:-1], wrong))))
    assert all(row["eligible"] is False for row in rows.values())


def test_identity_must_be_valid_for_every_session_not_only_at_execution():
    vintage, references, original = _inputs()
    snapshots = tuple(
        replace(snapshot, security=replace(snapshot.security, valid_from="2024-01-12"))
        for snapshot in vintage.snapshots
    )
    changed_vintage = build_vintage(
        vintage.manifest, vintage.release_calendar, snapshots, vintage.refusals
    )
    identity = hash_payload(snapshots[1].security.to_payload())
    changed_history = _history(
        daily=tuple(
            replace(row, security_identity_sha256=identity)
            for row in original.daily
        ),
        caps=tuple(
            replace(row, security_identity_sha256=identity)
            for row in original.capitalizations
        ),
    )
    evidence = build_stock_investability(changed_vintage, references, changed_history)
    rows = _rows(evidence, snapshots[1].event_id)
    assert rows[20]["eligible"] is True
    assert all(rows[lookback]["eligible"] is False for lookback in (60, 120, 252))


def test_market_cap_must_be_aligned_to_the_last_completed_session():
    original = _inputs()[2]
    caps = tuple(row for row in original.capitalizations if row.session != "2024-02-12")
    rows = _rows(_build(_history(caps=caps)))
    assert all(row["eligible"] is False for row in rows.values())
    assert all(row["market_cap_usd"] is None for row in rows.values())


def test_market_cap_at_execution_open_is_not_visible():
    original = _inputs()[2]
    caps = tuple(
        replace(
            row, available_at="2024-02-13T14:30:00Z",
            observed_at="2024-02-13T14:30:00Z",
        ) if row.session == "2024-02-12" else row
        for row in original.capitalizations
    )
    rows = _rows(_build(_history(caps=caps)))
    assert all(row["eligible"] is False for row in rows.values())


def test_market_cap_conflicting_equal_availability_is_ambiguous():
    original = _inputs()[2]
    ambiguous = replace(
        original.capitalizations[-1], market_cap_usd="299999999",
        raw_record_sha256="20" * 32,
    )
    rows = _rows(_build(_history(caps=(*original.capitalizations, ambiguous))))
    assert all(row["eligible"] is False for row in rows.values())
    assert all(
        "market_cap_ambiguous" in row["refusal_reasons"] for row in rows.values()
    )


def test_latest_visible_market_cap_revision_is_used():
    original = _inputs()[2]
    revision = replace(
        original.capitalizations[-1], market_cap_usd="299999999",
        available_at="2024-02-13T14:00:00Z",
        observed_at="2024-02-13T14:00:00Z", raw_record_sha256="21" * 32,
    )
    rows = _rows(_build(_history(caps=(*original.capitalizations, revision))))
    assert all(row["market_cap_usd"] == "299999999" for row in rows.values())
    assert all(row["eligible"] is False for row in rows.values())


def test_market_cap_identity_mismatch_is_not_admitted():
    original = _inputs()[2]
    wrong = replace(original.capitalizations[-1], security_identity_sha256="22" * 32)
    rows = _rows(_build(_history(caps=(*original.capitalizations[:-1], wrong))))
    assert all(
        "market_cap_identity_mismatch" in row["refusal_reasons"]
        for row in rows.values()
    )
    assert all(row["eligible"] is False for row in rows.values())


def test_market_history_and_evidence_are_order_invariant():
    original = _inputs()[2]
    reversed_history = _history(
        daily=tuple(reversed(original.daily)),
        caps=tuple(reversed(original.capitalizations)),
    )
    assert reversed_history.sha256 == original.sha256
    assert _build(reversed_history).to_payload() == _build().to_payload()


@pytest.mark.parametrize(
    "changes",
    [
        {"close_usd": "NaN"}, {"close_usd": "Infinity"}, {"close_usd": "0"},
        {"close_usd": "-1"}, {"close_usd": 100}, {"close_usd": "1e2"},
        {"volume_shares": True}, {"volume_shares": -1},
        {"volume_shares": 100000.0},
        {"available_at": "2024-02-12T23:00:00"},
        {"observed_at": "2024-02-12T22:00:00Z"},
    ],
)
def test_invalid_daily_contract_values_are_refused(changes):
    with pytest.raises(StockInvestabilityError):
        replace(_inputs()[2].daily[-1], **changes)


@pytest.mark.parametrize("cap", ["NaN", "Infinity", "0", "-1", "3e8", 300000000, True])
def test_invalid_market_cap_values_are_refused(cap):
    with pytest.raises(StockInvestabilityError):
        replace(_inputs()[2].capitalizations[-1], market_cap_usd=cap)


@pytest.mark.parametrize(
    "session,close,before",
    [
        ("2024-11-29", "18:00:00", "17:59:59"),
        ("2024-03-08", "21:00:00", "20:59:59"),
        ("2024-03-11", "20:00:00", "19:59:59"),
    ],
)
def test_observation_availability_uses_actual_half_day_and_dst_close(session, close, before):
    original = _inputs()[2].daily[-1]
    accepted = replace(
        original, session=session, available_at=f"{session}T{close}Z",
        observed_at=f"{session}T{close}Z",
    )
    assert accepted.session == session
    with pytest.raises(StockInvestabilityError):
        replace(
            original, session=session, available_at=f"{session}T{before}Z",
            observed_at=f"{session}T{before}Z",
        )


def test_weekend_cannot_supply_a_trading_session_observation():
    with pytest.raises(StockInvestabilityError):
        replace(
            _inputs()[2].daily[-1], session="2024-02-11",
            available_at="2024-02-11T23:00:00Z",
            observed_at="2024-02-11T23:00:00Z",
        )


def test_zero_volume_is_valid_but_fails_the_liquidity_minimum():
    original = _inputs()[2]
    rows = _rows(_build(_history(
        daily=tuple(replace(row, volume_shares=0) for row in original.daily)
    )))
    assert all(row["eligible"] is False for row in rows.values())
    assert all(
        row["median_dollar_volume"] == {"numerator": 0, "denominator": 1}
        for row in rows.values()
    )


def test_frozen_input_tampering_is_refused_at_build_boundary():
    original = _inputs()[2]
    forged = replace(original.daily[-1])
    object.__setattr__(forged, "close_usd", "NaN")
    with pytest.raises(StockInvestabilityError):
        _build(_history(daily=(*original.daily[:-1], forged)))


def test_evidence_payload_is_detached_and_entitlement_tampering_is_refused():
    evidence = _build()
    payload = evidence.to_payload()
    payload["rows"][0]["eligible"] = True
    payload["policy"]["made_up_field"] = True
    assert evidence.to_payload() != payload
    original = _inputs()[2]
    forged = replace(original)
    object.__setattr__(forged, "entitlement", "licensed_data")
    object.__setattr__(evidence, "history", forged)
    with pytest.raises(StockInvestabilityError):
        evidence.to_payload()


def test_frozen_evidence_rejects_valid_history_mutation_after_build():
    evidence = _build()
    # Evidence owns a detached view, so this changes only its captured source.
    captured = evidence.history.daily[-1]
    object.__setattr__(captured, "volume_shares", 999999)
    with pytest.raises(StockInvestabilityError):
        evidence.to_payload()


def test_mutating_original_input_after_build_cannot_change_evidence():
    original = _inputs()[2]
    caller_history = _history(
        daily=tuple(replace(row) for row in original.daily),
        caps=tuple(replace(row) for row in original.capitalizations),
    )
    evidence = _build(caller_history)
    before = evidence.to_payload()
    object.__setattr__(caller_history.daily[-1], "volume_shares", 999999)
    object.__setattr__(caller_history.capitalizations[-1], "market_cap_usd", "299999999")
    assert evidence.to_payload() == before


def test_security_method_shadow_cannot_dispatch_caller_callbacks():
    vintage, references, history = _inputs()
    snapshots = tuple(
        replace(snapshot, security=replace(snapshot.security))
        for snapshot in vintage.snapshots
    )
    source = build_vintage(
        vintage.manifest, vintage.release_calendar, snapshots, vintage.refusals
    )
    calls = []
    for snapshot in source.snapshots:
        canonical_valid_on = snapshot.security.valid_on

        def shadow(session, delegate=canonical_valid_on):
            calls.append(session)
            return delegate(session)

        object.__setattr__(snapshot.security, "valid_on", shadow)
    try:
        evidence = build_stock_investability(source, references, history)
        evidence.to_payload()
    except StockInvestabilityError:
        pass
    assert calls == []


def test_unknown_nested_value_is_refused_before_metaclass_introspection():
    vintage, references, history = _inputs()
    snapshots = tuple(
        replace(snapshot, security=replace(snapshot.security))
        for snapshot in vintage.snapshots
    )
    source = build_vintage(
        vintage.manifest, vintage.release_calendar, snapshots, vintage.refusals
    )
    calls = []

    class CallerMeta(type):
        def __getattribute__(cls, name):
            if name == "__dataclass_fields__":
                calls.append(name)
            return super().__getattribute__(name)

    class CallerValue(metaclass=CallerMeta):
        pass

    object.__setattr__(source.snapshots[1].security, "ticker", CallerValue())
    with pytest.raises(StockInvestabilityError):
        build_stock_investability(source, references, history)
    assert calls == []


def test_every_candidate_lookback_is_even_so_the_median_stays_exact():
    """The median helper always averages the two middle values.

    `(ordered[mid - 1] + ordered[mid]) / 2` with `mid = lookback // 2` is the
    exact median only for an even window. For an odd window it averages the two
    values straddling the true middle and silently returns a wrong number: for
    five sorted values 1..5 it yields 5/2 instead of 3. Nothing in the evidence
    builder refuses an odd candidate window, and the policy advertises
    `exact_middle_or_mean_of_two_middle_values`, so an odd lookback added to the
    approved grid would change eligibility without any other test noticing.
    This pins the precondition the arithmetic depends on.
    """
    policy = investability_module._policy()
    lookbacks = policy["candidate_lookbacks"]
    assert tuple(lookbacks) == LOOKBACKS
    odd = [value for value in lookbacks if value % 2]
    assert not odd, (
        f"odd candidate lookbacks {odd} need an exact odd-window median before "
        "they can be admitted"
    )
    for lookback in lookbacks:
        values = [Fraction(index + 1) for index in range(lookback)]
        middle = lookback // 2
        as_implemented = (values[middle - 1] + values[middle]) / 2
        true_median = (
            values[lookback // 2]
            if lookback % 2
            else (values[lookback // 2 - 1] + values[lookback // 2]) / 2
        )
        assert as_implemented == true_median
