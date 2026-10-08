"""Invented native-schema rows exercise the separate raw-revision proxy only."""
from dataclasses import FrozenInstanceError
from decimal import Decimal, localcontext

import pytest

from research.target_price_revisions_development import raw_revision as raw


def rating(**changes):
    value = {"benzinga_id": "fixture-event-1", "benzinga_firm_id": 12,
             "ticker": "ZZTEST", "date": "2025-01-02", "last_updated": "2025-01-02T15:00:00Z",
             "currency": "USD", "price_target_action": "raises",
             "price_target": "110", "previous_price_target": "100"}
    value.update(changes)
    return value


def identity(**changes):
    value = {"ticker": "ZZTEST", "security_id": "fixture-security-1", "permaticker": 101,
             "figi": "BBG00TEST001", "category": "Domestic Common Stock", "exchange": "NYSE",
             "isdelisted": False}
    value.update(changes)
    return value


def calendar():
    return ({"session_date": "2025-01-02", "open_utc": "2025-01-02T14:30:00Z"},
            {"session_date": "2025-01-03", "open_utc": "2025-01-03T14:30:00Z"},
            {"session_date": "2025-01-06", "open_utc": "2025-01-06T14:30:00Z"})


def run(rows=None, identities=None, actions=(), sessions=None, **changes):
    args = {"cutoff_utc": "2025-01-06T22:00:00Z", "capture_utc": "2026-10-07T10:00:00Z",
            "view": "censored", "action_inventory_complete": True}
    args.update(changes)
    return raw.normalize_raw_revisions((rating(),) if rows is None else rows,
                                      (identity(),) if identities is None else identities,
                                      actions, calendar() if sessions is None else sessions, **args)


def reason(result):
    assert not result.events
    return result.dispositions[0].reason


def test_native_slash_share_class_is_exact_not_an_alias_or_a_global_action_failure():
    result = run(rows=(rating(ticker="ZZTEST/A"),), identities=(identity(ticker="ZZTEST/A"),),
                 actions=({"ticker": "OTHER/B", "date": "2025-01-03", "action": "split"},))
    assert result.events[0].ticker == "ZZTEST/A"
    mismatched = run(rows=(rating(ticker="ZZTEST/A"),), identities=(identity(ticker="ZZTEST.A"),))
    assert reason(mismatched) == "missing_snapshot_identity"


def test_proxy_preserves_native_ids_exact_ratio_unknown_horizon_and_zero_authority():
    result = run()
    event = result.events[0]
    assert result.schema == "TPR-DEV-RAWREV-v1"
    assert event.benzinga_id == "fixture-event-1" and type(event.benzinga_firm_id) is int
    assert event.benzinga_firm_id == 12 and event.raw_revision_ratio == "1/10"
    assert event.eligible_open_utc == "2025-01-06T14:30:00+00:00"
    assert event.eligible_session_index == 2 and event.horizon_status == "unknown-not-comparable"
    assert event.raw_share_basis_unproven is True
    assert result.non_pristine_current_snapshot is True and result.point_in_time_data is False
    assert result.canonical_admission is False and result.outcome_access is False and result.trading is False
    assert result.view == "censored" and result.dispositions[0].reason == "accepted_proxy_revision"
    with pytest.raises(FrozenInstanceError):
        event.raw_revision_ratio = "9"


@pytest.mark.parametrize("new,prior,action,expected", [
    ("100", "100", "maintains", "0"), ("90", "100", "lowers", "-1/10"),
    (Decimal("110.00"), 100, "raises", "1/10"), ("1", "3", "lowers", "-2/3"),
])
def test_exact_raw_ratios_and_valid_zeros_are_context_independent(new, prior, action, expected):
    rows = (rating(price_target=new, previous_price_target=prior, price_target_action=action),)
    with localcontext() as ctx:
        ctx.prec = 2
        first = run(rows)
    with localcontext() as ctx:
        ctx.prec = 110
        second = run(rows)
    assert first == second and first.events[0].raw_revision_ratio == expected


@pytest.mark.parametrize("field,value,expected", [
    ("price_target", "0", "invalid_positive_target"),
    ("previous_price_target", None, "invalid_positive_target"),
    ("price_target", "NaN", "invalid_positive_target"),
    ("price_target", Decimal("Infinity"), "invalid_positive_target"),
    ("price_target", True, "invalid_positive_target"),
    ("price_target", 110.0, "invalid_positive_target"),
    ("price_target", "-1", "invalid_positive_target"),
    ("price_target", "1e3", "invalid_positive_target"),
    ("price_target", "0." + "0" * 40 + "1", "target_resource_bound"),
    ("currency", "CAD", "unsupported_currency"),
    ("price_target_action", "lowers", "action_direction_conflict"),
    ("price_target_action", "announces", "initiation_not_revision"),
    ("price_target_action", "sets", "initiation_not_revision"),
    ("price_target_action", "withdraws", "withdrawal_not_revision"),
    ("price_target_action", "mystery", "unsupported_target_action"),
    ("benzinga_firm_id", True, "invalid_firm_id"),
])
def test_non_comparable_or_invalid_pairs_keep_named_refusals(field, value, expected):
    assert reason(run((rating(**{field: value}),))) == expected


def test_current_and_censored_views_disclose_later_touches_without_old_value_imputation():
    rows = (rating(last_updated="2025-01-07T15:00:00Z"),)
    assert reason(run(rows)) == "later_touch_censored"
    current = run(rows, view="current")
    assert current.events[0].later_touch is True and current.point_in_time_data is False
    assert current.events[0].price_target == "110"
    assert current.events[0].last_updated_utc == "2025-01-07T15:00:00+00:00"


@pytest.mark.parametrize("clock,expected", [
    ("2025-01-01T15:00:00Z", "touch_precedes_issue_date"),
    ("2026-10-08T15:00:00Z", "touch_after_capture"),
    ("2025-01-02T15:00:00", "invalid_touch_clock"),
])
def test_reverse_missing_timezone_and_future_capture_clocks_refuse(clock, expected):
    assert reason(run((rating(last_updated=clock),))) == expected


def test_second_supplied_exchange_open_not_same_or_first_open_controls_eligibility():
    assert reason(run(cutoff_utc="2025-01-03T22:00:00Z")) == "not_yet_eligible"
    assert reason(run(sessions=calendar()[:2])) == "insufficient_calendar"
    assert reason(run((rating(date="2025-01-07"),))) == "issued_after_cutoff"


def test_truncated_axis_cannot_silently_shift_the_second_open():
    partial = ({"session_date": "2025-01-06", "open_utc": "2025-01-06T14:30:00Z"},
               {"session_date": "2025-01-07", "open_utc": "2025-01-07T14:30:00Z"})
    assert reason(run(sessions=partial, cutoff_utc="2025-01-07T22:00:00Z")) == "calendar_anchor_missing"


def test_target_magnitude_bound_is_exact_under_low_decimal_precision():
    with localcontext() as ctx:
        ctx.prec = 2
        assert reason(run((rating(price_target="1000000000000000000000001"),))) == "target_resource_bound"


@pytest.mark.parametrize("value", [Decimal("1E-999999999"), Decimal("1E+999999999")])
def test_extreme_target_exponents_are_refused_before_fraction_construction(value):
    assert reason(run((rating(price_target=value),))) == "target_resource_bound"


def test_false_integer_snapshot_authority_is_not_a_boolean():
    assert reason(run(identities=(identity(isdelisted=0),))) == "invalid_snapshot_identity"


def test_duplicate_native_rows_collapse_but_conflicts_never_fall_back():
    identical = run((rating(), rating()))
    assert len(identical.events) == 1 and identical.duplicate_rows == 1
    assert identical.dispositions[0].occurrences == 2
    conflict = run((rating(), rating(price_target="120")))
    assert reason(conflict) == "conflicting_native_event_id"
    assert conflict == run((rating(price_target="120"), rating()))


def test_native_integer_and_string_ids_are_preserved_not_python_bool_aliases():
    rows = (rating(benzinga_id=42), rating(benzinga_id="42"))
    result = run(rows)
    assert {type(event.benzinga_id) for event in result.events} == {int, str}
    assert len(result.events) == 2


@pytest.mark.parametrize("changes,expected", [
    ({"category": "ADR Common Stock"}, "not_domestic_common_stock"),
    ({"exchange": "OTC"}, "unsupported_exchange"),
    ({"isdelisted": True}, "current_snapshot_delisted"),
    ({"figi": None}, "invalid_snapshot_identity"),
])
def test_snapshot_refusals_do_not_become_historical_master_evidence(changes, expected):
    assert reason(run(identities=(identity(**changes),))) == expected


def test_missing_duplicate_conflicting_and_cross_ticker_identity_are_explicit():
    assert reason(run(identities=())) == "missing_snapshot_identity"
    assert len(run(identities=(identity(), identity())).events) == 1
    assert reason(run(identities=(identity(), identity(figi="BBG00TEST002")))) == "ambiguous_snapshot_identity"
    assert reason(run(identities=(identity(), identity(ticker="OTHER")))) == "ambiguous_snapshot_identity"


def snapshot_identity(**changes):
    return identity(**dict({"security_id": "SHARADAR:101", "permaticker": "101", "figi": None}, **changes))


def test_explicit_permaticker_policy_accepts_missing_figi_without_changing_strict_default():
    supplied = (snapshot_identity(),)
    assert reason(run(identities=supplied)) == "invalid_snapshot_identity"
    result = run(identities=supplied, identity_policy="sharadar_permaticker_snapshot_v1")
    assert len(result.events) == 1
    event = result.events[0]
    assert event.security_id == "SHARADAR:101" and event.permaticker == "101" and event.figi is None
    assert result.identity_policy == "sharadar_permaticker_snapshot_v1"
    assert result.missing_figi_input_rows == 1
    assert result.current_snapshot_survivorship_bias_possible is True
    assert result.historical_symbol_match_verified is result.point_in_time_data is False
    assert result.canonical_admission is result.quantconnect is False


@pytest.mark.parametrize("changes", [
    {"figi": ""}, {"figi": "MISSING_FIGI"}, {"figi": 123}, {"figi": "bbg000000001"},
    {"permaticker": ""}, {"permaticker": "00101"}, {"permaticker": True},
    {"permaticker": "made-up"}, {"permaticker": 0}, {"permaticker": "101.0"},
    {"security_id": "fixture-security"}, {"security_id": "SHARADAR:102"},
    {"security_id": 101}, {"isdelisted": 0},
])
def test_permaticker_policy_refuses_placeholder_ids_invalid_present_figi_and_namespace_mismatch(changes):
    result = run(identities=(snapshot_identity(**changes),), identity_policy="sharadar_permaticker_snapshot_v1")
    assert reason(result) == "invalid_snapshot_identity"


@pytest.mark.parametrize("permaticker", [101, "101"])
def test_permaticker_policy_preserves_native_permaticker_type_and_valid_present_figi(permaticker):
    value = snapshot_identity(permaticker=permaticker, figi="BBG000000001")
    result = run(identities=(value,), identity_policy="sharadar_permaticker_snapshot_v1")
    assert result.events[0].permaticker == permaticker
    assert result.events[0].figi == "BBG000000001" and result.missing_figi_input_rows == 0


@pytest.mark.parametrize("other", [
    snapshot_identity(ticker="OTHER"),
    snapshot_identity(ticker="OTHER", permaticker=101, security_id="invalid-namespace"),
    snapshot_identity(ticker="OTHER", permaticker="102", security_id="SHARADAR:102", figi="BBG000000001"),
])
def test_permaticker_policy_never_bypasses_native_or_present_figi_collisions(other):
    value = snapshot_identity(figi="BBG000000001")
    assert reason(run(identities=(value, other), identity_policy="sharadar_permaticker_snapshot_v1")) == "ambiguous_snapshot_identity"


def test_permaticker_policy_preserves_duplicate_conflict_and_action_gates():
    value = snapshot_identity()
    assert len(run(identities=(value, value), identity_policy="sharadar_permaticker_snapshot_v1").events) == 1
    assert reason(run(identities=(value, snapshot_identity(figi="BBG000000001")),
        identity_policy="sharadar_permaticker_snapshot_v1")) == "ambiguous_snapshot_identity"
    assert reason(run(identities=(value,), actions=({"ticker": "ZZTEST", "date": "2025-01-03", "action": "tickerchange"},),
        identity_policy="sharadar_permaticker_snapshot_v1")) == "corporate_action_ambiguity"
    assert reason(run(identities=(value,), action_inventory_complete=False,
        identity_policy="sharadar_permaticker_snapshot_v1")) == "action_inventory_incomplete"


@pytest.mark.parametrize("policy", [None, True, "auto", "sharadar_permaticker_snapshot_v2"])
def test_unknown_identity_policy_cannot_infer_an_opt_in(policy):
    with pytest.raises(raw.RawRevisionError, match="identity policy"):
        run(identity_policy=policy)


@pytest.mark.parametrize("action", ["split", "reverse_split", "tickerchange", "spinoff", "merger", "delisted", "unknown"])
def test_corporate_action_or_unclassified_basis_ambiguity_refuses(action):
    assert reason(run(actions=({"ticker": "ZZTEST", "date": "2025-01-03", "action": action},))) == "corporate_action_ambiguity"


def test_future_action_cannot_change_prior_cutoff_and_missing_inventory_is_not_no_actions():
    future = ({"ticker": "ZZTEST", "date": "2025-01-07", "action": "split"},)
    assert run(actions=future) == run()
    assert reason(run(action_inventory_complete=False)) == "action_inventory_incomplete"


@pytest.mark.parametrize("kind", ["dividend", "sicchangefrom", "sicchangeto"])
def test_explicit_nominal_pair_policy_ignores_only_reviewed_nonshare_actions(kind):
    actions = ({"ticker": "ZZTEST", "date": "2025-01-03", "action": kind},)
    assert reason(run(actions=actions)) == "corporate_action_ambiguity"
    result = run(actions=actions, action_policy="nominal_pair_nonshare_actions_v1")
    assert result.events and result.events[0].raw_revision_ratio == "1/10"
    assert result.action_policy == "nominal_pair_nonshare_actions_v1"
    assert result.nonshare_action_counts == ((kind, 1),)
    assert result.nominal_dividend_effects_possible is True
    assert result.target_pair_like_for_like_proven is result.point_in_time_data is result.canonical_admission is False


@pytest.mark.parametrize("kind", ["split", "reverse_split", "stockdividend", "specialdividend", "Dividend",
    "tickerchange", "spinoff", "merger", "delisted", "exchangefrom", "mystery", None])
def test_nominal_pair_policy_does_not_widen_unknown_split_or_identity_treatment(kind):
    assert reason(run(actions=({"ticker": "ZZTEST", "date": "2025-01-03", "action": kind},),
        action_policy="nominal_pair_nonshare_actions_v1")) == "corporate_action_ambiguity"


def test_nominal_pair_policy_is_as_of_not_future_filter_and_inventory_is_still_required():
    policy = {"action_policy": "nominal_pair_nonshare_actions_v1"}
    baseline = run(**policy)
    future = ({"ticker": "ZZTEST", "date": "2025-01-07", "action": "split"},)
    assert run(actions=future, **policy) == baseline
    assert reason(run(actions=future, cutoff_utc="2025-01-07T22:00:00Z", **policy)) == "corporate_action_ambiguity"
    assert reason(run(action_inventory_complete=False, **policy)) == "action_inventory_incomplete"


@pytest.mark.parametrize("policy", [True, None, "ignore-actions", "nominal_pair_nonshare_actions_v2"])
def test_action_policy_requires_exact_explicit_selector(policy):
    with pytest.raises(raw.RawRevisionError, match="action policy"):
        run(action_policy=policy)


def test_result_order_and_detachment_do_not_depend_on_input_permutation():
    rows = [rating(), rating(benzinga_id="fixture-event-2", price_target="90", price_target_action="lowers")]
    mappings = [identity()]
    first = run(rows, mappings)
    assert first == run(tuple(reversed(rows)), tuple(reversed(mappings)))
    rows[0]["price_target"] = "999"
    mappings[0]["figi"] = "modified"
    assert first.events[0].price_target in {"110", "90"}


@pytest.mark.parametrize("changes", [
    {"view": True}, {"view": "pristine"}, {"action_inventory_complete": 0},
    {"cutoff_utc": "2025-01-06T22:00:00"},
    {"capture_utc": "2025-01-01T22:00:00Z"},
])
def test_global_contract_does_not_accept_fake_types_or_clocks(changes):
    with pytest.raises(raw.RawRevisionError):
        run(**changes)


def test_closed_rows_and_calendar_types_refuse_without_callbacks():
    class Evil(str):
        def __eq__(self, other):
            pytest.fail("caller equality executed")
        __hash__ = str.__hash__
    wrong = rating()
    wrong[Evil("extra")] = None
    with pytest.raises(raw.RawRevisionError):
        run((wrong,))
    same_shape = rating()
    original = same_shape.pop("benzinga_id")
    same_shape[Evil("benzinga_id")] = original
    with pytest.raises(raw.RawRevisionError):
        run((same_shape,))
    with pytest.raises(raw.RawRevisionError):
        run((rating(price_target=Evil("110")),))
    with pytest.raises(raw.RawRevisionError):
        run(sessions=tuple(reversed(calendar())))
    with pytest.raises(raw.RawRevisionError):
        run(sessions=({"session_date": "2025-01-02", "open_utc": "2025-01-03T14:30:00Z"},))


def test_inventory_resource_limits_are_refused_before_row_or_calendar_processing():
    with pytest.raises(raw.RawRevisionError, match="bounded"):
        run(rows=(None,) * (raw.MAX_ROWS + 1))
    with pytest.raises(raw.RawRevisionError, match="bounded"):
        run(sessions=(None,) * (raw.MAX_SESSIONS + 1))


def test_native_proxy_has_no_file_network_environment_or_operator_dependency(monkeypatch):
    import builtins
    import io
    import os
    import socket
    def refuse(*args, **kwargs):
        pytest.fail("pure raw proxy attempted I/O")
    for module, name in ((builtins, "open"), (io, "open"), (os, "open"), (os, "getenv"), (socket, "socket")):
        monkeypatch.setattr(module, name, refuse)
    assert run().events
