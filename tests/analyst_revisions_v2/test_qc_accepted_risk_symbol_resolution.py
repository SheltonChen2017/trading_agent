from __future__ import annotations

import dataclasses
import hashlib
from types import MappingProxyType

import pytest

from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2_qc import (
    accepted_risk_qc_symbol_resolution as subject,
)


SHA = "a" * 64


class _Sid:
    def __init__(self, value: str) -> None:
        self.value = value
        self.market = "usa"

    def __str__(self) -> str:
        return self.value


class _Symbol:
    def __init__(self, sid: str, ticker: str | None = None) -> None:
        self.id = _Sid(sid)
        self.value = ticker if ticker is not None else sid.rsplit(" ", 1)[-1]
        self.security_type = "Equity"


def _row(
    security_id: str = "sharadar-composite-figi-BBG000ONE",
    *,
    admitted_mapping_count: int = 1,
) -> dict[str, object]:
    ticker = "ONE" if security_id.endswith("ONE") else "TWO"
    return subject.build_runtime_ticker_binding(
        security_id=security_id,
        issuer_id="sharadar-permaticker-1" + ticker,
        share_class_id="BBG000" + ticker,
        listing_id="sharadar-listing-" + ticker.lower(),
        current_snapshot_ticker=ticker,
        exchange_mic="XNAS",
        candidate_first_session="2021-01-04",
        candidate_last_session="2025-12-31",
        source_snapshot_available_at="2026-09-14T01:02:03.000000Z",
        source_row_sha256=hashlib.sha256(("source-" + ticker).encode()).hexdigest(),
        identity_evidence_sha256=hashlib.sha256(
            ("identity-" + ticker).encode()
        ).hexdigest(),
        security_master_admission_sha256=SHA,
        admitted_mapping_inventory_sha256="b" * 64,
        admitted_mapping_count=admitted_mapping_count,
    )


def test_resolves_each_owner_accepted_ticker_without_claiming_formal_authority():
    rows = [
        _row(admitted_mapping_count=2),
        _row("sharadar-composite-figi-BBG000TWO", admitted_mapping_count=2),
    ]
    made: list[str] = []

    def factory(ticker: str) -> _Symbol:
        made.append(ticker)
        return _Symbol("QC SID " + ticker, ticker)

    value = subject.resolve_owner_accepted_qc_symbols(rows, symbol_factory=factory)

    assert made == ["ONE", "TWO"]
    assert value.resolved_count == 2
    assert value.named_refusal_count == 0
    assert value.every_input_has_one_terminal is True
    assert value.preliminary_evaluation_eligible is True
    assert value.point_in_time is False
    assert value.independently_reviewed is False
    assert value.formal_security_master_authority is False
    assert value.formal_eligibility == subject.FORMAL_ELIGIBILITY
    assert str(value.symbol_for_security(rows[0]["security_id"]).id) == "QC SID ONE"
    assert value.logical_security_for_qc_sid("QC SID TWO") == rows[1]["security_id"]
    assert subject.require_accepted_risk_qc_symbol_resolution(value) is value


def test_unavailable_runtime_symbol_is_one_named_terminal_not_a_drop():
    rows = [_row()]
    value = subject.resolve_owner_accepted_qc_symbols(
        rows, symbol_factory=lambda _ticker: None
    )

    assert value.resolved == ()
    assert value.named_refusal_count == 1
    assert value.named_refusals[0]["reason"] == (
        "qc_runtime_symbol_resolution_unavailable"
    )
    assert value.every_input_has_one_terminal is True
    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="logical security has no accepted runtime QC symbol",
    ):
        value.symbol_for_security(str(rows[0]["security_id"]))


def test_qc_sid_collision_refuses_every_member_of_the_collision_group():
    rows = [
        _row(admitted_mapping_count=2),
        _row("sharadar-composite-figi-BBG000TWO", admitted_mapping_count=2),
    ]
    value = subject.resolve_owner_accepted_qc_symbols(
        rows, symbol_factory=lambda ticker: _Symbol("QC SHARED SID", ticker)
    )

    assert value.resolved_count == 0
    assert value.named_refusal_count == 2
    assert {item["security_id"] for item in value.named_refusals} == {
        row["security_id"] for row in rows
    }
    assert {item["reason"] for item in value.named_refusals} == {
        "qc_runtime_security_identifier_collision"
    }


def test_owner_accepted_risk_flag_cannot_be_promoted_by_a_row():
    row = _row()
    row["point_in_time"] = True
    semantic = dict(row)
    semantic.pop("row_sha256")
    row["row_sha256"] = hashlib.sha256(canonical_json_bytes(semantic)).hexdigest()

    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="runtime ticker binding accepted-risk disclosure changed",
    ):
        subject.resolve_owner_accepted_qc_symbols(
            [row], symbol_factory=lambda _ticker: _Symbol("QC SID")
        )


def test_runtime_binding_hash_is_recomputed_before_symbol_factory_call():
    row = _row()
    row["candidate_last_session"] = "2025-12-30"
    calls = 0

    def factory(_ticker: str) -> _Symbol:
        nonlocal calls
        calls += 1
        return _Symbol("QC SID")

    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="runtime ticker binding content hash changed",
    ):
        subject.resolve_owner_accepted_qc_symbols([row], symbol_factory=factory)
    assert calls == 0


def test_binding_inventory_must_be_logically_ordered_and_unique():
    one = _row(admitted_mapping_count=2)
    two = _row(
        "sharadar-composite-figi-BBG000TWO", admitted_mapping_count=2
    )

    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="runtime ticker binding inventory is not ordered by logical security",
    ):
        subject.resolve_owner_accepted_qc_symbols(
            [two, one], symbol_factory=lambda ticker: _Symbol("QC " + ticker)
        )
    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="runtime ticker binding repeats a logical security",
    ):
        subject.resolve_owner_accepted_qc_symbols(
            [one, one], symbol_factory=lambda ticker: _Symbol("QC " + ticker)
        )
    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="runtime ticker binding inventory contains a non-mapping row",
    ):
        subject.resolve_owner_accepted_qc_symbols(
            [object()], symbol_factory=lambda _ticker: _Symbol("QC SID")
        )


def test_symbol_factory_exception_is_not_misreported_as_market_missingness():
    def broken(_ticker: str) -> object:
        raise RuntimeError("hostile detail must remain chained only")

    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="runtime QC symbol factory raised before a named resolution terminal",
    ) as captured:
        subject.resolve_owner_accepted_qc_symbols([_row()], symbol_factory=broken)
    assert "hostile detail" not in str(captured.value)


def test_invalid_qc_sid_is_a_distinct_hard_refusal():
    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="runtime QC symbol returned an invalid SecurityIdentifier",
    ):
        subject.resolve_owner_accepted_qc_symbols(
            [_row()], symbol_factory=lambda ticker: _Symbol("bad\nSID", ticker)
        )


def test_none_sid_or_wrong_us_equity_ticker_is_a_distinct_hard_refusal():
    broken = _Symbol("QC SID ONE")
    broken.id = None
    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="lacks readable ticker/type/market identity",
    ):
        subject.resolve_owner_accepted_qc_symbols(
            [_row()], symbol_factory=lambda _ticker: broken
        )

    wrong = _Symbol("QC SID SPY", "SPY")
    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="differs from the requested US equity ticker",
    ):
        subject.resolve_owner_accepted_qc_symbols(
            [_row()], symbol_factory=lambda _ticker: wrong
        )


def test_reverse_mapping_refuses_unrequested_history_bars():
    value = subject.resolve_owner_accepted_qc_symbols(
        [_row()], symbol_factory=lambda _ticker: _Symbol("QC SID ONE")
    )
    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="History bar returned an unbound runtime QC SecurityIdentifier",
    ):
        value.logical_security_for_qc_sid("QC SID OTHER")
    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="History bar QC SecurityIdentifier is invalid",
    ):
        value.logical_security_for_qc_sid("bad\nSID")


def test_post_build_symbol_or_public_record_mutation_is_detected():
    symbol = _Symbol("QC SID ONE")
    value = subject.resolve_owner_accepted_qc_symbols(
        [_row()], symbol_factory=lambda _ticker: symbol
    )
    symbol.id.value = "QC SID CHANGED"
    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="runtime QC SecurityIdentifier changed after resolution",
    ):
        subject.require_accepted_risk_qc_symbol_resolution(value)

    clean = subject.resolve_owner_accepted_qc_symbols(
        [_row()], symbol_factory=lambda _ticker: _Symbol("QC SID ONE")
    )
    object.__setattr__(clean, "formal_security_master_authority", True)
    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="runtime QC symbol resolution public record changed",
    ):
        subject.require_accepted_risk_qc_symbol_resolution(clean)

    rebound = subject.resolve_owner_accepted_qc_symbols(
        [_row()], symbol_factory=lambda _ticker: _Symbol("QC SID ONE")
    )
    changed = dict(rebound.resolved[0])
    changed["source_binding_sha256"] = "b" * 64
    semantic = {
        name: changed[name]
        for name in ("security_id", "source_binding_sha256", "qc_security_id")
    }
    changed["resolution_sha256"] = hashlib.sha256(
        canonical_json_bytes(semantic)
    ).hexdigest()
    object.__setattr__(rebound, "resolved", (changed,))
    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="runtime QC symbol terminals do not bind every admitted input",
    ):
        subject.require_accepted_risk_qc_symbol_resolution(rebound)


def test_post_resolution_hostile_equal_symbol_ticker_is_refused():
    symbol = _Symbol("QC SID ONE")
    value = subject.resolve_owner_accepted_qc_symbols(
        [_row()], symbol_factory=lambda _ticker: symbol
    )

    class EqualToEverything:
        def __eq__(self, _other):
            return True

        def __ne__(self, _other):
            return False

    symbol.value = EqualToEverything()
    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="SecurityIdentifier changed after resolution",
    ):
        subject.require_accepted_risk_qc_symbol_resolution(value)


def test_input_field_inventory_and_ticker_exchange_guards_are_distinct():
    row = _row()
    row["extra"] = False
    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="runtime ticker binding schema or field inventory changed",
    ):
        subject.resolve_owner_accepted_qc_symbols(
            [row], symbol_factory=lambda _ticker: _Symbol("QC SID")
        )

    for field, value, message in (
        (
            "current_snapshot_ticker",
            "one",
            "runtime ticker binding current snapshot ticker is invalid",
        ),
        (
            "exchange_mic",
            "OTCM",
            "runtime ticker binding exchange is outside the admitted US universe",
        ),
    ):
        row = _row()
        row[field] = value
        semantic = dict(row)
        semantic.pop("row_sha256")
        row["row_sha256"] = hashlib.sha256(canonical_json_bytes(semantic)).hexdigest()
        with pytest.raises(subject.AcceptedRiskQcSymbolResolutionError, match=message):
            subject.resolve_owner_accepted_qc_symbols(
                [row], symbol_factory=lambda _ticker: _Symbol("QC SID")
            )


def test_resolution_dataclass_has_no_action_or_order_surface():
    fields = {field.name for field in dataclasses.fields(subject.AcceptedRiskQcSymbolResolution)}
    assert not fields & {
        "order",
        "orders",
        "quantity",
        "allocation",
        "target_weight",
        "trade",
        "deployment",
    }


def _admitted(
    *, ticker: str, figi: str, ordinal: int, cusips: list[str]
) -> dict[str, object]:
    return {
        "schema": subject.ADMISSION_MAPPING_SCHEMA,
        "source_ordinal": ordinal,
        "source_row_sha256": hashlib.sha256(("source-" + ticker).encode()).hexdigest(),
        "security_id": "sharadar-composite-figi-" + figi,
        "issuer_id": "sharadar-permaticker-" + ticker,
        "composite_figi": figi,
        "listing_id": "sharadar-listing-" + ticker.lower(),
        "ticker": ticker,
        "exchange_id": "XNAS",
        "cusip_join_candidates": cusips,
        "sector_id": "sharadar-sector-tech",
        "industry_id": "sharadar-industry-software",
        "candidate_first_session": "2021-01-04",
        "candidate_last_session": "2025-12-31",
        "identity_evidence_sha256": hashlib.sha256(("identity-" + ticker).encode()).hexdigest(),
        "classification_evidence_sha256": hashlib.sha256(
            ("classification-" + ticker).encode()
        ).hexdigest(),
        "source_snapshot_available_at": "2026-09-14T00:00:00+00:00",
        "qc_security_id": None,
        "mapping_status": subject.MAPPING_STATUS,
        "qc_sid_available": False,
        "point_in_time": False,
        "independently_reviewed": False,
        "historical_availability_claimed": False,
        "current_snapshot_identity_basis": True,
        "owner_accepted_current_snapshot_risk": True,
    }


def test_atomic_admission_projection_accepts_producer_order_and_empty_cusips():
    # Producer order is ticker/security, not source ordinal order.
    rows = [
        _admitted(ticker="AAA", figi="BBG000000AAA", ordinal=2, cusips=[]),
        _admitted(
            ticker="ZZZ", figi="BBG000000ZZZ", ordinal=1, cusips=["000000001"]
        ),
    ]
    inventory = hashlib.sha256(canonical_json_bytes(rows)).hexdigest()

    value = subject.resolve_admitted_security_master_qc_symbols(
        rows,
        security_master_admission_sha256=SHA,
        admitted_mapping_inventory_sha256=inventory,
        symbol_factory=lambda ticker: _Symbol("QC SID " + ticker),
    )

    assert value.input_row_count == 2
    assert [item["security_id"] for item in value.resolved] == sorted(
        row["security_id"] for row in rows
    )
    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="admitted security mapping inventory escaped its reviewed hash",
    ):
        subject.resolve_admitted_security_master_qc_symbols(
            rows[:1],
            security_master_admission_sha256=SHA,
            admitted_mapping_inventory_sha256=inventory,
            symbol_factory=lambda ticker: _Symbol("QC SID " + ticker),
        )


def test_bulk_history_index_preflights_identity_and_has_o1_reverse_lookup(monkeypatch):
    row = _row()
    resolution = subject.resolve_owner_accepted_qc_symbols(
        [row], symbol_factory=lambda _ticker: _Symbol("QC SID ONE")
    )
    index = subject.build_accepted_risk_qc_history_bindings(resolution)

    symbol = index.symbol_for_history_request(
        security_id=str(row["security_id"]),
        decision_session="2022-06-01",
        historical_ticker="ONE",
        issuer_id=str(row["issuer_id"]),
        share_class_id=str(row["share_class_id"]),
        listing_id=str(row["listing_id"]),
        security_master_row_sha256=str(row["source_row_sha256"]),
        runtime_binding_row_sha256=str(row["row_sha256"]),
    )
    assert str(symbol.id) == "QC SID ONE"
    monkeypatch.setattr(
        subject,
        "require_accepted_risk_qc_symbol_resolution",
        lambda _value: (_ for _ in ()).throw(AssertionError("per-bar reauth")),
    )
    assert index.logical_security_for_history_bar("QC SID ONE") == row["security_id"]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"historical_ticker": "TWO"}, "ticker or external listing identity"),
        ({"share_class_id": "BBG000TWO"}, "ticker or external listing identity"),
        ({"decision_session": "2020-12-31"}, "outside the admitted candidate interval"),
    ],
)
def test_history_request_preflight_refuses_wrong_ticker_external_id_or_interval(
    change: dict[str, str], message: str
):
    row = _row()
    resolution = subject.resolve_owner_accepted_qc_symbols(
        [row], symbol_factory=lambda _ticker: _Symbol("QC SID ONE")
    )
    index = subject.build_accepted_risk_qc_history_bindings(resolution)
    request = {
        "security_id": str(row["security_id"]),
        "decision_session": "2022-06-01",
        "historical_ticker": "ONE",
        "issuer_id": str(row["issuer_id"]),
        "share_class_id": str(row["share_class_id"]),
        "listing_id": str(row["listing_id"]),
        "security_master_row_sha256": str(row["source_row_sha256"]),
        "runtime_binding_row_sha256": str(row["row_sha256"]),
    }
    request.update(change)
    with pytest.raises(subject.AcceptedRiskQcSymbolResolutionError, match=message):
        index.symbol_for_history_request(**request)


def test_history_request_refuses_hostile_equal_external_identity_before_lookup():
    row = _row()
    resolution = subject.resolve_owner_accepted_qc_symbols(
        [row], symbol_factory=lambda _ticker: _Symbol("QC SID ONE")
    )
    index = subject.build_accepted_risk_qc_history_bindings(resolution)

    class EqualToEverything:
        def __eq__(self, _other):
            return True

        def __ne__(self, _other):
            return False

    hostile = EqualToEverything()
    for field in (
        "issuer_id", "share_class_id", "listing_id",
        "security_master_row_sha256", "runtime_binding_row_sha256",
    ):
        request = {
            "security_id": str(row["security_id"]),
            "decision_session": "2022-06-01",
            "historical_ticker": "ONE",
            "issuer_id": str(row["issuer_id"]),
            "share_class_id": str(row["share_class_id"]),
            "listing_id": str(row["listing_id"]),
            "security_master_row_sha256": str(row["source_row_sha256"]),
            "runtime_binding_row_sha256": str(row["row_sha256"]),
        }
        request[field] = hostile
        with pytest.raises(subject.AcceptedRiskQcSymbolResolutionError):
            index.symbol_for_history_request(**request)


def test_history_index_reauthentication_catches_replaced_symbol_and_input_maps():
    row = _row()
    resolution = subject.resolve_owner_accepted_qc_symbols(
        [row], symbol_factory=lambda _ticker: _Symbol("QC SID ONE")
    )
    index = subject.build_accepted_risk_qc_history_bindings(resolution)
    logical = str(row["security_id"])
    object.__setattr__(
        index,
        "_symbol_by_security",
        MappingProxyType({logical: _Symbol("QC SID ONE")}),
    )
    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="accepted-risk QC History bindings changed during traversal",
    ):
        subject.require_accepted_risk_qc_history_bindings(index)

    clean = subject.build_accepted_risk_qc_history_bindings(resolution)

    class GrabBacking:
        backing = None

        def __eq__(self, other):
            self.backing = other
            return False

    grab = GrabBacking()
    assert (clean._input_by_security[logical] == grab) is False
    assert type(grab.backing) is dict
    grab.backing["admitted_mapping_count"] = True
    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="History input binding changed during traversal",
    ):
        subject.require_accepted_risk_qc_history_bindings(clean)


def test_history_index_reflected_reverse_map_leak_refuses_equal_str_subclass():
    row = _row()
    resolution = subject.resolve_owner_accepted_qc_symbols(
        [row], symbol_factory=lambda _ticker: _Symbol("QC SID ONE")
    )
    index = subject.build_accepted_risk_qc_history_bindings(resolution)

    class GrabBacking:
        backing = None

        def __eq__(self, other):
            self.backing = other
            return False

    class StringSubtype(str):
        pass

    grab = GrabBacking()
    assert (index._logical_by_qc_sid == grab) is False
    assert type(grab.backing) is dict
    grab.backing["QC SID ONE"] = StringSubtype(str(row["security_id"]))
    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="History binding scalar type changed",
    ):
        subject.require_accepted_risk_qc_history_bindings(index)


@pytest.mark.parametrize("field", ["resolution_sha256", "_fingerprint"])
def test_history_index_identity_containers_require_exact_builtin_types(field: str):
    row = _row()
    resolution = subject.resolve_owner_accepted_qc_symbols(
        [row], symbol_factory=lambda _ticker: _Symbol("QC SID ONE")
    )
    index = subject.build_accepted_risk_qc_history_bindings(resolution)

    class StringSubtype(str):
        pass

    class TupleSubtype(tuple):
        pass

    replacement = (
        StringSubtype(index.resolution_sha256)
        if field == "resolution_sha256"
        else TupleSubtype(index._fingerprint)
    )
    object.__setattr__(index, field, replacement)
    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="History binding identity type changed",
    ):
        subject.require_accepted_risk_qc_history_bindings(index)


def test_hostile_input_mapping_and_symbol_property_exceptions_are_normalized():
    class HostileMap(dict):
        def keys(self):
            raise RuntimeError("hostile mapping detail must not escape")

    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="^runtime ticker binding inventory contains a non-mapping row$",
    ) as mapping_error:
        subject.resolve_owner_accepted_qc_symbols(
            [HostileMap()], symbol_factory=lambda _ticker: None
        )
    assert "hostile mapping detail" not in str(mapping_error.value)

    class HostileSymbol:
        @property
        def id(self):
            raise RuntimeError("hostile symbol detail must not escape")

    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="^runtime QC symbol lacks readable ticker/type/market identity$",
    ) as symbol_error:
        subject.resolve_owner_accepted_qc_symbols(
            [_row()], symbol_factory=lambda _ticker: HostileSymbol()
        )
    assert "hostile symbol detail" not in str(symbol_error.value)


def test_resolved_record_security_type_cannot_be_changed_and_rehashed():
    resolution = subject.resolve_owner_accepted_qc_symbols(
        [_row()], symbol_factory=lambda _ticker: _Symbol("QC SID ONE")
    )
    changed = dict(resolution.resolved[0])
    changed["security_type"] = False
    semantic = dict(changed)
    semantic.pop("resolution_sha256")
    changed["resolution_sha256"] = hashlib.sha256(
        canonical_json_bytes(semantic)
    ).hexdigest()
    resolved = (changed,)
    seed = subject._result_seed(
        rows=resolution._input_rows,
        resolved=resolved,
        refusals=resolution.named_refusals,
    )
    digest = hashlib.sha256(canonical_json_bytes(seed)).hexdigest()
    forged = dataclasses.replace(
        resolution,
        resolved=resolved,
        resolution_id="arv2-owner-accepted-qc-symbols-" + digest[:24],
        resolution_sha256=digest,
    )
    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="resolved symbol record schema changed",
    ):
        subject.require_accepted_risk_qc_symbol_resolution(forged)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("resolved_count", True, "count type changed"),
        ("formal_security_master_authority", 0, "gate type changed"),
        ("preliminary_evaluation_eligible", 1, "gate type changed"),
    ],
)
def test_public_resolution_exact_scalar_guards_are_isolated(
    field: str, value: object, message: str
):
    resolution = subject.resolve_owner_accepted_qc_symbols(
        [_row()], symbol_factory=lambda _ticker: _Symbol("QC SID ONE")
    )
    object.__setattr__(resolution, field, value)
    with pytest.raises(subject.AcceptedRiskQcSymbolResolutionError, match=message):
        subject.require_accepted_risk_qc_symbol_resolution(resolution)


def _figi_row(
    figi: str = "BBG000000001",
    *,
    ticker: str = "OLD",
    admitted_mapping_count: int = 1,
) -> dict[str, object]:
    return subject.build_runtime_ticker_binding(
        security_id="sharadar-composite-figi-" + figi,
        issuer_id="sharadar-permaticker-" + figi[-3:],
        share_class_id=figi,
        listing_id="sharadar-listing-" + figi[-3:].lower(),
        current_snapshot_ticker=ticker,
        exchange_mic="XNYS",
        candidate_first_session="2021-01-04",
        candidate_last_session="2025-12-31",
        source_snapshot_available_at="2026-09-14T01:02:03.000000Z",
        source_row_sha256=hashlib.sha256(("source-" + figi).encode()).hexdigest(),
        identity_evidence_sha256=hashlib.sha256(
            ("identity-" + figi).encode()
        ).hexdigest(),
        security_master_admission_sha256=SHA,
        admitted_mapping_inventory_sha256="c" * 64,
        admitted_mapping_count=admitted_mapping_count,
    )


def test_composite_figi_is_primary_and_ticker_mismatch_is_only_display_evidence():
    row = _figi_row()
    symbol = _Symbol("QC PERMANENT SID", "NEW")
    forward: list[str] = []
    reverse: list[object] = []

    def resolve(figi: str) -> _Symbol:
        forward.append(figi)
        return symbol

    def roundtrip(value: object) -> str:
        reverse.append(value)
        return "BBG000000001"

    value = subject.resolve_owner_accepted_qc_symbols_by_composite_figi(
        [row],
        composite_figi_resolver=resolve,
        composite_figi_roundtrip=roundtrip,
    )

    assert forward == ["BBG000000001"]
    assert reverse == [symbol]
    assert value.authority_mode == subject.COMPOSITE_FIGI_AUTHORITY_MODE
    assert value.resolved[0]["current_snapshot_ticker"] == "NEW"
    assert value.resolved[0]["external_composite_figi"] == "BBG000000001"
    assert value.resolved[0]["resolution_method"] == "composite_figi_exact_roundtrip"
    assert value.point_in_time is False
    assert value.formal_security_master_authority is False


def test_composite_figi_named_forward_reverse_and_identity_refusals_are_distinct():
    rows = [
        _figi_row("BBG000000001", ticker="ONE", admitted_mapping_count=4),
        _figi_row("BBG000000002", ticker="TWO", admitted_mapping_count=4),
        _figi_row("BBG000000003", ticker="THR", admitted_mapping_count=4),
        _figi_row("BBG000000004", ticker="FOR", admitted_mapping_count=4),
    ]

    def resolve(figi: str):
        if figi.endswith("001"):
            return None
        symbol = _Symbol("QC SID " + figi[-3:], figi[-3:])
        if figi.endswith("003"):
            symbol.id.market = "canada"
        return symbol

    def reverse(symbol: _Symbol) -> str:
        if str(symbol.id).endswith("002"):
            return "BBG000000999"
        return "BBG000000004"

    value = subject.resolve_owner_accepted_qc_symbols_by_composite_figi(
        rows,
        composite_figi_resolver=resolve,
        composite_figi_roundtrip=reverse,
    )
    assert value.resolved_count == 1
    assert {item["reason"] for item in value.named_refusals} == {
        "qc_runtime_composite_figi_resolution_unavailable",
        "qc_runtime_composite_figi_roundtrip_mismatch",
        "qc_runtime_composite_figi_not_us_equity",
    }


def test_composite_figi_collision_refuses_full_group_but_keeps_unique_sid():
    rows = [
        _figi_row("BBG000000001", ticker="ONE", admitted_mapping_count=3),
        _figi_row("BBG000000002", ticker="TWO", admitted_mapping_count=3),
        _figi_row("BBG000000003", ticker="THR", admitted_mapping_count=3),
    ]

    def resolve(figi: str) -> _Symbol:
        sid = "QC SHARED" if not figi.endswith("003") else "QC UNIQUE"
        return _Symbol(sid, figi[-3:])

    by_symbol: dict[int, str] = {}

    def forward(figi: str) -> _Symbol:
        symbol = resolve(figi)
        by_symbol[id(symbol)] = figi
        return symbol

    value = subject.resolve_owner_accepted_qc_symbols_by_composite_figi(
        rows,
        composite_figi_resolver=forward,
        composite_figi_roundtrip=lambda symbol: by_symbol[id(symbol)],
    )
    assert [item["security_id"] for item in value.resolved] == [rows[2]["security_id"]]
    assert [item["reason"] for item in value.named_refusals] == [
        "qc_runtime_security_identifier_collision",
        "qc_runtime_security_identifier_collision",
    ]


@pytest.mark.parametrize("failure", ["forward", "reverse"])
def test_composite_figi_resolver_exceptions_are_hard_errors_not_missingness(failure: str):
    symbol = _Symbol("QC SID ONE", "ONE")

    def forward(_figi: str):
        if failure == "forward":
            raise RuntimeError("secret forward detail")
        return symbol

    def reverse(_symbol: object):
        if failure == "reverse":
            raise RuntimeError("secret reverse detail")
        return "BBG000000001"

    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match=("resolver raised" if failure == "forward" else "reverse resolver raised"),
    ) as captured:
        subject.resolve_owner_accepted_qc_symbols_by_composite_figi(
            [_figi_row()],
            composite_figi_resolver=forward,
            composite_figi_roundtrip=reverse,
        )
    assert "secret" not in str(captured.value)


def test_composite_figi_malformed_input_and_reverse_are_hard_errors():
    calls = 0

    def forward(_figi: str) -> _Symbol:
        nonlocal calls
        calls += 1
        return _Symbol("QC SID ONE", "ONE")

    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="input identity is malformed",
    ):
        subject.resolve_owner_accepted_qc_symbols_by_composite_figi(
            [_row()],
            composite_figi_resolver=forward,
            composite_figi_roundtrip=lambda _symbol: "BBG000000001",
        )
    assert calls == 0

    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="returned malformed identity",
    ):
        subject.resolve_owner_accepted_qc_symbols_by_composite_figi(
            [_figi_row()],
            composite_figi_resolver=forward,
            composite_figi_roundtrip=lambda _symbol: False,
        )


def test_composite_figi_zero_resolved_inventory_is_a_hard_gate():
    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="produced zero usable securities",
    ):
        subject.resolve_owner_accepted_qc_symbols_by_composite_figi(
            [_figi_row()],
            composite_figi_resolver=lambda _figi: None,
            composite_figi_roundtrip=lambda _symbol: "BBG000000001",
        )


def test_composite_figi_private_binding_mutation_is_detected():
    symbol = _Symbol("QC SID ONE", "ONE")
    value = subject.resolve_owner_accepted_qc_symbols_by_composite_figi(
        [_figi_row()],
        composite_figi_resolver=lambda _figi: symbol,
        composite_figi_roundtrip=lambda _symbol: "BBG000000001",
    )
    object.__setattr__(
        value,
        "_roundtrip_figis",
        ((str(value.resolved[0]["security_id"]), "BBG000000999"),),
    )
    with pytest.raises(
        subject.AcceptedRiskQcSymbolResolutionError,
        match="terminal inventory changed",
    ):
        subject.require_accepted_risk_qc_symbol_resolution(value)
