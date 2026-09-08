"""IB-2C point-in-time security mapping tests (synthetic/offline only)."""
from __future__ import annotations

import ast
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from data.hashing import hash_payload
from research.insider_buying import (
    FORM4_PIT_SECURITY_MAPPING_VERSION,
    Form4OwnerAttributionOutcome,
    Form4PitSecurityMapping,
    Form4PitSecurityMappingError,
    Form4PitSecurityMappingIdentity,
    Form4PitSecurityMappingOutcome,
    Form4PitSecurityMappingRow,
    Form4PitSecurityRecord,
    Form4SecurityClass,
    Form4SecurityTitleInterval,
    Form4SecurityTitleMappingKind,
    Form4TickerInterval,
    build_form4_pit_security_mapping,
)
from research.insider_buying import form4_pit_security_mapping as mapping_module
from research.insider_buying import form4_sec_entity_grouping as grouping_module
from tests import test_insider_buying_form4_sec_entity_grouping as ib2b


BUILDER_COMMIT = "b" * 40
REFERENCE_SHA256 = "9" * 64
BASE_AVAILABLE = "2020-01-01T00:00:00+00:00"
_UNSET = object()


def _security(
    *,
    security_id="sec-fixture-common",
    share_class_id="share-class-common",
    issuer_cik=ib2b.ISSUER_CIK,
    security_class=Form4SecurityClass.COMMON_STOCK,
    valid_from=date(2020, 1, 1),
    valid_to=None,
    available_at_utc=BASE_AVAILABLE,
    valid_to_available_at_utc=None,
    valid_to_evidence_id=_UNSET,
    valid_to_evidence_sha256=_UNSET,
    evidence_id="security-evidence-1",
):
    if valid_to_evidence_id is _UNSET:
        valid_to_evidence_id = (
            None if valid_to is None else f"{evidence_id}-closure"
        )
    if valid_to_evidence_sha256 is _UNSET:
        valid_to_evidence_sha256 = (
            None
            if valid_to is None
            else hash_payload({"closure": valid_to_evidence_id})
        )
    return Form4PitSecurityRecord(
        security_id=security_id,
        share_class_id=share_class_id,
        issuer_cik=issuer_cik,
        security_class_normalized=security_class,
        valid_from=valid_from,
        valid_to=valid_to,
        available_at_utc=available_at_utc,
        valid_to_available_at_utc=valid_to_available_at_utc,
        valid_to_evidence_id=valid_to_evidence_id,
        valid_to_evidence_sha256=valid_to_evidence_sha256,
        evidence_id=evidence_id,
        evidence_sha256=hash_payload({"evidence": evidence_id}),
    )


def _title(
    *,
    security_id="sec-fixture-common",
    share_class_id="share-class-common",
    security_title_raw="Common Stock",
    mapping_kind=Form4SecurityTitleMappingKind.DETERMINISTIC_EXACT,
    valid_from=date(2020, 1, 1),
    valid_to=None,
    available_at_utc=BASE_AVAILABLE,
    valid_to_available_at_utc=None,
    valid_to_evidence_id=_UNSET,
    valid_to_evidence_sha256=_UNSET,
    evidence_id="title-evidence-1",
):
    if valid_to_evidence_id is _UNSET:
        valid_to_evidence_id = (
            None if valid_to is None else f"{evidence_id}-closure"
        )
    if valid_to_evidence_sha256 is _UNSET:
        valid_to_evidence_sha256 = (
            None
            if valid_to is None
            else hash_payload({"closure": valid_to_evidence_id})
        )
    return Form4SecurityTitleInterval(
        security_id=security_id,
        share_class_id=share_class_id,
        security_title_raw=security_title_raw,
        mapping_kind=mapping_kind,
        valid_from=valid_from,
        valid_to=valid_to,
        available_at_utc=available_at_utc,
        valid_to_available_at_utc=valid_to_available_at_utc,
        valid_to_evidence_id=valid_to_evidence_id,
        valid_to_evidence_sha256=valid_to_evidence_sha256,
        evidence_id=evidence_id,
        evidence_sha256=hash_payload({"evidence": evidence_id}),
    )


def _ticker(
    *,
    security_id="sec-fixture-common",
    ticker="FIXT",
    exchange="XNYS",
    country="US",
    valid_from=date(2020, 1, 1),
    valid_to=None,
    available_at_utc=BASE_AVAILABLE,
    valid_to_available_at_utc=None,
    valid_to_evidence_id=_UNSET,
    valid_to_evidence_sha256=_UNSET,
    evidence_id="ticker-evidence-1",
):
    if valid_to_evidence_id is _UNSET:
        valid_to_evidence_id = (
            None if valid_to is None else f"{evidence_id}-closure"
        )
    if valid_to_evidence_sha256 is _UNSET:
        valid_to_evidence_sha256 = (
            None
            if valid_to is None
            else hash_payload({"closure": valid_to_evidence_id})
        )
    return Form4TickerInterval(
        security_id=security_id,
        ticker=ticker,
        exchange=exchange,
        country=country,
        valid_from=valid_from,
        valid_to=valid_to,
        available_at_utc=available_at_utc,
        valid_to_available_at_utc=valid_to_available_at_utc,
        valid_to_evidence_id=valid_to_evidence_id,
        valid_to_evidence_sha256=valid_to_evidence_sha256,
        evidence_id=evidence_id,
        evidence_sha256=hash_payload({"evidence": evidence_id}),
    )


def _catalog():
    return (_security(),), (_title(),), (_ticker(),)


def _with_xml(spec, old, new):
    assert old.encode() in spec.xml_bytes
    return replace(spec, xml_bytes=spec.xml_bytes.replace(old.encode(), new.encode()))


def _build(
    monkeypatch,
    specs=None,
    *,
    securities=None,
    titles=None,
    tickers=None,
    reverse=False,
):
    specs = (ib2b._spec(1),) if specs is None else specs
    defaults = _catalog()
    securities = defaults[0] if securities is None else securities
    titles = defaults[1] if titles is None else titles
    tickers = defaults[2] if tickers is None else tickers
    _, grouping = ib2b._group(monkeypatch, specs, reverse=reverse)
    result = build_form4_pit_security_mapping(
        grouping,
        security_records=securities,
        title_intervals=titles,
        ticker_intervals=tickers,
        reference_id="synthetic-offline-reference",
        reference_version="v1",
        reference_sha256=REFERENCE_SHA256,
        builder_git_commit=BUILDER_COMMIT,
    )
    return grouping, result


def _forge(value, **updates):
    forged = object.__new__(type(value))
    for name, item in vars(value).items():
        object.__setattr__(forged, name, item)
    for name, item in updates.items():
        object.__setattr__(forged, name, item)
    return forged


def _rehash_result_with_row(result, row):
    row = _forge(
        row,
        mapping_row_id=hash_payload(mapping_module._mapping_row_payload(row)),
    )
    mapped = row.point_in_time_mapping_structurally_resolved
    identity = _forge(
        result.identity,
        mapping_row_inventory_hash=hash_payload([row.to_payload()]),
        structurally_mapped_count=int(mapped),
        security_mapping_quarantined_count=int(not mapped),
        manual_exception_resolution_count=int(
            row.title_mapping_kind
            is Form4SecurityTitleMappingKind.MANUAL_EXCEPTION
        ),
    )
    identity = _forge(
        identity,
        mapping_id=(
            "form4-pit-security-mapping-"
            f"{hash_payload(mapping_module._mapping_identity_payload(identity))[:16]}"
        ),
    )
    return _forge(result, identity=identity, rows=(row,))


def test_ib2c_contract_version_is_frozen():
    assert FORM4_PIT_SECURITY_MAPPING_VERSION == (
        "INSETF-IB2C-FORM4-PIT-SECURITY-MAPPING-v1"
    )


def test_unique_cik_title_and_intervals_resolve_one_permanent_security(monkeypatch):
    grouping, result = _build(monkeypatch)
    row = result.rows[0]
    upstream = grouping.transaction_attributions[0]

    assert result.identity.mapping_row_count == 1
    assert result.identity.structurally_mapped_count == 1
    assert result.identity.security_mapping_quarantined_count == 0
    assert row.resolution_outcomes == (
        Form4PitSecurityMappingOutcome.MAPPED_STRUCTURALLY,
    )
    assert (row.security_id, row.share_class_id, row.ticker) == (
        "sec-fixture-common",
        "share-class-common",
        "FIXT",
    )
    assert row.transaction_attribution_id == upstream.transaction_attribution_id
    assert row.owner_attribution_outcomes == upstream.owner_attribution_outcomes
    assert result.identity.upstream_grouping_fingerprint == (
        grouping_module._grouping_provenance_fingerprint(grouping)
    )


def test_unrelated_late_same_title_never_poisons_exact_issuer_match(monkeypatch):
    unrelated_security = _security(
        security_id="sec-unrelated",
        share_class_id="class-unrelated",
        issuer_cik=ib2b.OTHER_ISSUER_CIK,
        evidence_id="security-unrelated",
    )
    unrelated_title = _title(
        security_id="sec-unrelated",
        share_class_id="class-unrelated",
        available_at_utc="2030-01-01T00:00:00+00:00",
        evidence_id="title-unrelated-late",
    )
    _, result = _build(
        monkeypatch,
        securities=(_security(), unrelated_security),
        titles=(_title(), unrelated_title),
        tickers=(_ticker(), _ticker(
            security_id="sec-unrelated",
            ticker="OTHR",
            evidence_id="ticker-unrelated",
        )),
    )
    assert result.rows[0].resolution_outcomes == (
        Form4PitSecurityMappingOutcome.MAPPED_STRUCTURALLY,
    )


def test_two_share_classes_under_one_cik_remain_distinct(monkeypatch):
    specs = (
        _with_xml(
            ib2b._spec(1, symbol="FIXA"),
            "Common Stock",
            "Class A Common Stock",
        ),
        _with_xml(
            ib2b._spec(2, symbol="FIXB"),
            "Common Stock",
            "Class B Common Stock",
        ),
    )
    securities = (
        _security(security_id="sec-a", share_class_id="class-a", evidence_id="sec-a"),
        _security(security_id="sec-b", share_class_id="class-b", evidence_id="sec-b"),
    )
    titles = (
        _title(
            security_id="sec-a",
            share_class_id="class-a",
            security_title_raw="Class A Common Stock",
            evidence_id="title-a",
        ),
        _title(
            security_id="sec-b",
            share_class_id="class-b",
            security_title_raw="Class B Common Stock",
            evidence_id="title-b",
        ),
    )
    tickers = (
        _ticker(security_id="sec-a", ticker="FIXA", evidence_id="ticker-a"),
        _ticker(security_id="sec-b", ticker="FIXB", evidence_id="ticker-b"),
    )
    _, result = _build(
        monkeypatch,
        specs,
        securities=securities,
        titles=titles,
        tickers=tickers,
    )
    assert tuple(row.security_id for row in result.rows) == ("sec-a", "sec-b")
    assert tuple(row.share_class_id for row in result.rows) == ("class-a", "class-b")


def test_manual_exception_is_exact_and_never_grants_canonical_status(monkeypatch):
    spec = _with_xml(ib2b._spec(1), "Common Stock", "Ordinary Shares")
    security = _security(security_class=Form4SecurityClass.ORDINARY_SHARES)
    title = _title(
        security_title_raw="Ordinary Shares",
        mapping_kind=Form4SecurityTitleMappingKind.MANUAL_EXCEPTION,
    )
    _, result = _build(
        monkeypatch,
        (spec,),
        securities=(security,),
        titles=(title,),
    )
    row = result.rows[0]
    assert row.title_mapping_kind is Form4SecurityTitleMappingKind.MANUAL_EXCEPTION
    assert result.identity.manual_exception_resolution_count == 1
    assert result.ordinary_equity_classification_verified is False
    assert result.canonical_filter_authorized is False

    near_match = _with_xml(
        ib2b._spec(2),
        "Common Stock",
        "Ordinary Shares, par value $0.01",
    )
    _, quarantined = _build(
        monkeypatch,
        (near_match,),
        securities=(security,),
        titles=(title,),
    )
    assert quarantined.rows[0].resolution_outcomes == (
        Form4PitSecurityMappingOutcome.NO_ACTIVE_SECURITY_TITLE_MAPPING_QUARANTINED,
    )


def test_ticker_change_between_transaction_and_filing_preserves_security(monkeypatch):
    spec = ib2b._spec(1, symbol="NEW")
    tickers = (
        _ticker(
            ticker="OLD",
            valid_to=date(2026, 11, 1),
            valid_to_available_at_utc="2026-10-01T00:00:00+00:00",
            evidence_id="ticker-old",
        ),
        _ticker(ticker="NEW", valid_from=date(2026, 11, 1), evidence_id="ticker-new"),
    )
    _, result = _build(monkeypatch, (spec,), tickers=tickers)
    assert (result.rows[0].security_id, result.rows[0].ticker) == (
        "sec-fixture-common",
        "NEW",
    )


@pytest.mark.parametrize(
    ("accepted_at", "boundary"),
    (
        (datetime(2027, 1, 5, 1, tzinfo=timezone.utc), date(2027, 1, 5)),
        (datetime(2027, 7, 5, 3, 30, tzinfo=timezone.utc), date(2027, 7, 5)),
    ),
)
def test_edgar_acceptance_uses_new_york_calendar_date(
    monkeypatch,
    accepted_at,
    boundary,
):
    del monkeypatch
    accepted_text = accepted_at.isoformat(timespec="seconds")
    assert mapping_module._new_york_filing_date(accepted_text) == (
        boundary - timedelta(days=1)
    )
    local_midnight_utc = (
        datetime(2027, 1, 5, 5, tzinfo=timezone.utc)
        if boundary.month == 1
        else datetime(2027, 7, 5, 4, tzinfo=timezone.utc)
    )
    assert mapping_module._new_york_filing_date(
        local_midnight_utc.isoformat(timespec="seconds")
    ) == boundary


def test_validity_is_half_open_and_cutoff_is_inclusive(monkeypatch):
    spec = ib2b._spec(1)
    cutoff = spec.accepted_at.isoformat(timespec="seconds")
    boundary = date(2026, 8, 18)
    securities = (
        _security(
            valid_to=boundary,
            valid_to_available_at_utc="2026-08-01T00:00:00+00:00",
            evidence_id="security-old",
        ),
        _security(
            valid_from=boundary,
            available_at_utc=cutoff,
            evidence_id="security-new",
        ),
    )
    titles = (_title(valid_from=boundary, available_at_utc=cutoff),)
    _, result = _build(
        monkeypatch,
        (spec,),
        securities=securities,
        titles=titles,
        tickers=(_ticker(valid_from=boundary),),
    )
    assert result.rows[0].security_interval_asof_id == (
        securities[1].security_record_id
    )

    late = replace(
        securities[1],
        available_at_utc=(spec.accepted_at + timedelta(seconds=1)).isoformat(
            timespec="seconds"
        ),
    )
    _, late_result = _build(
        monkeypatch,
        (spec,),
        securities=(late,),
        titles=titles,
        tickers=(_ticker(valid_from=boundary),),
    )
    assert late_result.rows[0].resolution_outcomes == (
        Form4PitSecurityMappingOutcome.NO_ACTIVE_SECURITY_TITLE_MAPPING_QUARANTINED,
    )


def test_hidden_closure_evidence_quarantines_instead_of_first_wins(monkeypatch):
    boundary = date(2026, 8, 1)
    old = _security(
        valid_to=boundary,
        valid_to_available_at_utc="2027-01-01T00:00:00+00:00",
        evidence_id="security-old-hidden-close",
    )
    new = _security(valid_from=boundary, evidence_id="security-new")
    titles = (
        _title(
            valid_to=boundary,
            valid_to_available_at_utc="2027-01-01T00:00:00+00:00",
            evidence_id="title-old-hidden-close",
        ),
        _title(valid_from=boundary, evidence_id="title-new"),
    )
    _, result = _build(
        monkeypatch,
        securities=(old, new),
        titles=titles,
        tickers=(_ticker(valid_from=boundary),),
    )
    assert result.rows[0].resolution_outcomes == (
        Form4PitSecurityMappingOutcome.AMBIGUOUS_SECURITY_TITLE_MAPPING_QUARANTINED,
    )
    assert result.rows[0].security_id is None


def test_future_reference_facts_are_invisible_to_the_asof_row(monkeypatch):
    _, baseline = _build(monkeypatch)
    future_security = _security(
        security_id="sec-future",
        share_class_id="class-future",
        security_class=Form4SecurityClass.PREFERRED_STOCK,
        available_at_utc="2030-01-01T00:00:00+00:00",
        evidence_id="security-future",
    )
    future_same_title = _title(
        security_id="sec-future",
        share_class_id="class-future",
        available_at_utc="2030-01-01T00:00:00+00:00",
        evidence_id="title-future-common",
    )
    future_other_title = _title(
        security_id="sec-future",
        share_class_id="class-future",
        security_title_raw="Preferred Stock",
        available_at_utc="2030-01-01T00:00:00+00:00",
        evidence_id="title-future-preferred",
    )
    _, augmented = _build(
        monkeypatch,
        securities=(_security(), future_security),
        titles=(_title(), future_same_title, future_other_title),
        tickers=(
            _ticker(),
            _ticker(
                security_id="sec-future",
                ticker="FUTR",
                available_at_utc="2030-01-01T00:00:00+00:00",
                evidence_id="ticker-future",
            ),
        ),
    )
    assert augmented.rows[0].to_payload() == baseline.rows[0].to_payload()


def test_future_interval_closures_are_masked_from_asof_row_ids(monkeypatch):
    _, baseline = _build(monkeypatch)
    closure_available = "2030-01-01T00:00:00+00:00"
    securities, titles, tickers = _catalog()
    _, with_future_closures = _build(
        monkeypatch,
        securities=(replace(
            securities[0],
            valid_to=date(2028, 1, 1),
            valid_to_available_at_utc=closure_available,
            valid_to_evidence_id="security-future-closure",
            valid_to_evidence_sha256=hash_payload(
                {"closure": "security-future-closure"}
            ),
        ),),
        titles=(replace(
            titles[0],
            valid_to=date(2028, 1, 1),
            valid_to_available_at_utc=closure_available,
            valid_to_evidence_id="title-future-closure",
            valid_to_evidence_sha256=hash_payload(
                {"closure": "title-future-closure"}
            ),
        ),),
        tickers=(replace(
            tickers[0],
            valid_to=date(2028, 1, 1),
            valid_to_available_at_utc=closure_available,
            valid_to_evidence_id="ticker-future-closure",
            valid_to_evidence_sha256=hash_payload(
                {"closure": "ticker-future-closure"}
            ),
        ),),
    )
    assert with_future_closures.rows[0].to_payload() == (
        baseline.rows[0].to_payload()
    )


def test_transaction_after_eastern_filing_date_is_quarantined(monkeypatch):
    spec = _with_xml(
        ib2b._spec(1),
        "<transactionDate><value>2026-08-18</value></transactionDate>",
        "<transactionDate><value>2026-12-22</value></transactionDate>",
    )
    _, result = _build(monkeypatch, (spec,))
    assert result.rows[0].resolution_outcomes == (
        Form4PitSecurityMappingOutcome.TRANSACTION_AFTER_FILING_DATE_QUARANTINED,
    )


def test_overlapping_security_and_ticker_candidates_never_first_win(monkeypatch):
    securities = (
        _security(evidence_id="security-overlap-a"),
        _security(
            security_id="sec-other",
            share_class_id="class-other",
            evidence_id="security-overlap-b",
        ),
    )
    titles = (
        _title(evidence_id="title-overlap-a"),
        _title(
            security_id="sec-other",
            share_class_id="class-other",
            evidence_id="title-overlap-b",
        ),
    )
    tickers = (
        _ticker(evidence_id="ticker-a"),
        _ticker(
            security_id="sec-other",
            ticker="OTHR",
            evidence_id="ticker-b",
        ),
    )
    _, result = _build(
        monkeypatch,
        securities=securities,
        titles=titles,
        tickers=tickers,
    )
    assert result.rows[0].resolution_outcomes == (
        Form4PitSecurityMappingOutcome.AMBIGUOUS_SECURITY_TITLE_MAPPING_QUARANTINED,
    )

    _, ticker_result = _build(
        monkeypatch,
        tickers=(
            _ticker(evidence_id="ticker-xnys"),
            _ticker(exchange="XNAS", evidence_id="ticker-xnas"),
        ),
    )
    assert ticker_result.rows[0].resolution_outcomes == (
        Form4PitSecurityMappingOutcome.AMBIGUOUS_TICKER_QUARANTINED,
    )


def test_missing_inputs_each_receive_named_quarantine(monkeypatch):
    missing_date = _with_xml(
        ib2b._spec(1),
        "<transactionDate><value>2026-08-18</value></transactionDate>",
        "<transactionDate></transactionDate>",
    )
    missing_title = _with_xml(
        ib2b._spec(2),
        "<securityTitle><value>Common Stock</value></securityTitle>",
        "<securityTitle></securityTitle>",
    )
    missing_symbol = ib2b._spec(3, symbol="")
    _, result = _build(
        monkeypatch,
        (missing_date, missing_title, missing_symbol),
    )
    assert result.rows[0].resolution_outcomes == (
        Form4PitSecurityMappingOutcome.MISSING_TRANSACTION_DATE_QUARANTINED,
    )
    assert result.rows[1].resolution_outcomes == (
        Form4PitSecurityMappingOutcome.MISSING_SECURITY_TITLE_QUARANTINED,
    )
    assert result.rows[2].resolution_outcomes == (
        Form4PitSecurityMappingOutcome.MISSING_ISSUER_SYMBOL_QUARANTINED,
    )
    assert result.identity.mapping_row_count == 3
    assert result.identity.security_mapping_quarantined_count == 3


def test_missing_ticker_and_symbol_mismatch_are_distinct(monkeypatch):
    _, missing = _build(monkeypatch, tickers=())
    assert missing.rows[0].resolution_outcomes == (
        Form4PitSecurityMappingOutcome.NO_ACTIVE_TICKER_QUARANTINED,
    )

    _, mismatch = _build(monkeypatch, (ib2b._spec(1, symbol="NOPE"),))
    assert mismatch.rows[0].resolution_outcomes == (
        Form4PitSecurityMappingOutcome.ISSUER_SYMBOL_MISMATCH_QUARANTINED,
    )


def test_security_mapping_never_promotes_joint_owner_quarantine(monkeypatch):
    spec = ib2b._spec(
        1,
        owners=(
            ib2b._Owner(),
            ib2b._Owner(cik=ib2b.OTHER_OWNER_CIK, name="Joint Owner"),
        ),
    )
    _, result = _build(monkeypatch, (spec,))
    row = result.rows[0]
    assert row.point_in_time_mapping_structurally_resolved is True
    assert (
        Form4OwnerAttributionOutcome.MULTIPLE_OWNER_SET_QUARANTINED
        in row.owner_attribution_outcomes
    )
    assert row.attributed_owner_cik is None
    assert result.identity.security_mapping_quarantined_count == 0
    assert row.canonical_filter_authorized is False
    assert row.lot_aggregation_authorized is False


def test_original_and_amendment_lineage_remain_distinct_and_complete(monkeypatch):
    original, amendment = ib2b._pair()
    grouping, result = _build(monkeypatch, (original, amendment))
    issuer_by_filing = {
        observation.filing_observation_id: observation
        for candidate in grouping.issuer_candidates
        for observation in candidate.observations
    }
    assert tuple(row.document_type for row in result.rows) == ("4", "4/A")
    for row in result.rows:
        issuer = issuer_by_filing[row.filing_observation_id]
        assert (
            row.original_accession,
            row.amends_accession,
            row.issuer_observation_id,
        ) == (
            issuer.original_accession,
            issuer.amends_accession,
            issuer.issuer_observation_id,
        )


def test_reference_reordering_is_hash_and_result_deterministic(monkeypatch):
    securities = (
        _security(),
        _security(
            security_id="sec-unused",
            share_class_id="class-unused",
            issuer_cik=ib2b.OTHER_ISSUER_CIK,
            evidence_id="security-unused",
        ),
    )
    titles = (
        _title(),
        _title(
            security_id="sec-unused",
            share_class_id="class-unused",
            security_title_raw="Unused Common Stock",
            evidence_id="title-unused",
        ),
    )
    tickers = (
        _ticker(),
        _ticker(
            security_id="sec-unused",
            ticker="UNSD",
            evidence_id="ticker-unused",
        ),
    )
    _, first = _build(
        monkeypatch,
        securities=securities,
        titles=titles,
        tickers=tickers,
    )
    _, second = _build(
        monkeypatch,
        securities=tuple(reversed(securities)),
        titles=tuple(reversed(titles)),
        tickers=tuple(reversed(tickers)),
        reverse=True,
    )
    assert first.to_payload() == second.to_payload()
    assert first.identity.mapping_id == second.identity.mapping_id


def test_reference_is_deeply_detached_from_caller_objects(monkeypatch):
    security, title, ticker = _security(), _title(), _ticker()
    _, result = _build(
        monkeypatch,
        securities=(security,),
        titles=(title,),
        tickers=(ticker,),
    )
    assert result.security_records[0] is not security
    assert result.title_intervals[0] is not title
    assert result.ticker_intervals[0] is not ticker
    object.__setattr__(ticker, "ticker", "EVIL")
    assert result.ticker_intervals[0].ticker == "FIXT"
    assert result.rows[0].ticker == "FIXT"


def test_forged_or_mutated_upstream_grouping_is_refused(monkeypatch):
    _, grouping = ib2b._group(monkeypatch, (ib2b._spec(1),))
    forged = _forge(grouping)
    grouping_module.Form4SecEntityGrouping.__post_init__(
        forged,
        grouping_module._GROUPING_FACTORY_TOKEN,
    )
    securities, titles, tickers = _catalog()

    def invoke(value):
        return build_form4_pit_security_mapping(
            value,
            security_records=securities,
            title_intervals=titles,
            ticker_intervals=tickers,
            reference_id="synthetic-offline-reference",
            reference_version="v1",
            reference_sha256=REFERENCE_SHA256,
            builder_git_commit=BUILDER_COMMIT,
        )

    with pytest.raises(Form4PitSecurityMappingError, match="factory provenance"):
        invoke(forged)
    object.__setattr__(grouping, "transaction_attributions", ())
    with pytest.raises(Form4PitSecurityMappingError, match="factory provenance"):
        invoke(grouping)


def test_captured_grouping_must_match_the_sealed_fingerprint(monkeypatch):
    _, grouping = ib2b._group(monkeypatch, (ib2b._spec(1),))
    securities, titles, tickers = _catalog()
    real_projection = mapping_module._grouping_provenance_payload
    altered = real_projection(grouping)
    altered["transaction_attributions"] = []

    monkeypatch.setattr(
        mapping_module,
        "_grouping_provenance_payload",
        lambda _grouping: altered,
    )
    with pytest.raises(Form4PitSecurityMappingError, match="snapshot"):
        build_form4_pit_security_mapping(
            grouping,
            security_records=securities,
            title_intervals=titles,
            ticker_intervals=tickers,
            reference_id="synthetic-offline-reference",
            reference_version="v1",
            reference_sha256=REFERENCE_SHA256,
            builder_git_commit=BUILDER_COMMIT,
        )


def test_mid_build_grouping_and_reference_mutation_are_refused(monkeypatch):
    _, grouping = ib2b._group(monkeypatch, (ib2b._spec(1),))
    securities, titles, tickers = _catalog()
    original = mapping_module._records_from_snapshot

    def mutate_grouping(payload):
        result = original(payload)
        object.__setattr__(grouping, "transaction_attributions", ())
        return result

    monkeypatch.setattr(mapping_module, "_records_from_snapshot", mutate_grouping)
    with pytest.raises(Form4PitSecurityMappingError, match="grouping changed"):
        build_form4_pit_security_mapping(
            grouping,
            security_records=securities,
            title_intervals=titles,
            ticker_intervals=tickers,
            reference_id="synthetic-offline-reference",
            reference_version="v1",
            reference_sha256=REFERENCE_SHA256,
            builder_git_commit=BUILDER_COMMIT,
        )

    monkeypatch.setattr(mapping_module, "_records_from_snapshot", original)
    _, grouping = ib2b._group(monkeypatch, (ib2b._spec(2),))
    security = securities[0]

    def mutate_reference(payload):
        result = original(payload)
        object.__setattr__(security, "issuer_cik", ib2b.OTHER_ISSUER_CIK)
        return result

    monkeypatch.setattr(mapping_module, "_records_from_snapshot", mutate_reference)
    with pytest.raises(Form4PitSecurityMappingError, match="reference input changed"):
        build_form4_pit_security_mapping(
            grouping,
            security_records=(security,),
            title_intervals=titles,
            ticker_intervals=tickers,
            reference_id="synthetic-offline-reference",
            reference_version="v1",
            reference_sha256=REFERENCE_SHA256,
            builder_git_commit=BUILDER_COMMIT,
        )


def test_reference_crosslinks_duplicates_and_caps_fail_closed(monkeypatch):
    duplicate = _security()
    with pytest.raises(Form4PitSecurityMappingError, match="duplicate interval"):
        _build(monkeypatch, securities=(duplicate, duplicate))

    orphan = _title(
        security_id="missing-security",
        share_class_id="missing-class",
    )
    with pytest.raises(Form4PitSecurityMappingError, match="no exact security"):
        _build(monkeypatch, titles=(orphan,))

    conflict = _title(share_class_id="wrong-class")
    with pytest.raises(Form4PitSecurityMappingError, match="no exact security"):
        _build(monkeypatch, titles=(conflict,))

    monkeypatch.setattr(mapping_module, "MAX_FORM4_PIT_SECURITY_RECORDS", 0)
    with pytest.raises(Form4PitSecurityMappingError, match="count exceeds"):
        _build(monkeypatch)


def test_child_intervals_and_share_class_ids_bind_one_security(monkeypatch):
    bounded_security = _security(
        valid_to=date(2027, 1, 1),
        valid_to_available_at_utc="2026-01-01T00:00:00+00:00",
    )
    with pytest.raises(Form4PitSecurityMappingError, match="title interval exceeds"):
        _build(
            monkeypatch,
            securities=(bounded_security,),
            titles=(_title(valid_from=date(2019, 1, 1)),),
            tickers=(),
        )
    with pytest.raises(Form4PitSecurityMappingError, match="ticker interval exceeds"):
        _build(
            monkeypatch,
            securities=(bounded_security,),
            titles=(_title(
                valid_to=date(2027, 1, 1),
                valid_to_available_at_utc="2026-01-01T00:00:00+00:00",
            ),),
            tickers=(_ticker(),),
        )
    reused_share_class = _security(
        security_id="sec-other",
        evidence_id="security-other",
    )
    with pytest.raises(Form4PitSecurityMappingError, match="share-class ID"):
        _build(
            monkeypatch,
            securities=(_security(), reused_share_class),
            titles=(),
            tickers=(),
        )


def test_listing_history_rejects_cross_security_overlap(monkeypatch):
    other_security = _security(
        security_id="sec-other",
        share_class_id="class-other",
        issuer_cik=ib2b.OTHER_ISSUER_CIK,
        evidence_id="security-other",
    )
    overlapping = (
        _ticker(),
        _ticker(security_id="sec-other", evidence_id="ticker-other"),
    )
    with pytest.raises(Form4PitSecurityMappingError, match="listing overlaps"):
        _build(
            monkeypatch,
            securities=(_security(), other_security),
            titles=(_title(),),
            tickers=overlapping,
        )

    with pytest.raises(Form4PitSecurityMappingError, match="listing overlaps"):
        _build(
            monkeypatch,
            securities=(_security(), other_security),
            titles=(_title(),),
            tickers=(
                _ticker(
                    security_id="sec-other",
                    evidence_id="ticker-open-other",
                ),
                _ticker(
                    valid_from=date.max,
                    evidence_id="ticker-date-max",
                ),
            ),
        )



def test_same_ticker_sequential_reuse_is_cik_scoped_and_pit_safe(monkeypatch):
    switch_date = date(2026, 11, 1)
    specs = (
        ib2b._spec(
            1,
            month=10,
            issuer_cik=ib2b.OTHER_ISSUER_CIK,
            symbol="FIXT",
        ),
        ib2b._spec(2, month=12, symbol="FIXT"),
    )
    other_security = _security(
        security_id="sec-old-issuer",
        share_class_id="class-old-issuer",
        issuer_cik=ib2b.OTHER_ISSUER_CIK,
        evidence_id="security-old-issuer",
    )
    other_title = _title(
        security_id="sec-old-issuer",
        share_class_id="class-old-issuer",
        evidence_id="title-old-issuer",
    )
    old_ticker = _ticker(
        security_id="sec-old-issuer",
        valid_to=switch_date,
        valid_to_available_at_utc="2026-10-01T00:00:00+00:00",
        evidence_id="ticker-old-issuer",
    )
    new_ticker = _ticker(
        valid_from=switch_date,
        evidence_id="ticker-new-issuer",
    )
    catalog = {
        "securities": (_security(), other_security),
        "titles": (_title(), other_title),
        "tickers": (old_ticker, new_ticker),
    }

    _, mapped = _build(monkeypatch, specs, **catalog)
    rows_by_cik = {row.issuer_cik: row for row in mapped.rows}
    assert rows_by_cik[ib2b.OTHER_ISSUER_CIK].security_id == "sec-old-issuer"
    assert rows_by_cik[ib2b.ISSUER_CIK].security_id == "sec-fixture-common"
    assert all(
        row.resolution_outcomes
        == (Form4PitSecurityMappingOutcome.MAPPED_STRUCTURALLY,)
        for row in mapped.rows
    )

    late_closure = replace(
        old_ticker,
        valid_to_available_at_utc="2027-01-01T00:00:00+00:00",
    )
    _, hidden = _build(
        monkeypatch,
        specs,
        **{**catalog, "tickers": (late_closure, new_ticker)},
    )
    hidden_rows_by_cik = {row.issuer_cik: row for row in hidden.rows}
    assert hidden_rows_by_cik[ib2b.OTHER_ISSUER_CIK].security_id == (
        "sec-old-issuer"
    )
    assert hidden_rows_by_cik[ib2b.ISSUER_CIK].resolution_outcomes == (
        Form4PitSecurityMappingOutcome.AMBIGUOUS_TICKER_QUARANTINED,
    )


def test_cumulative_text_and_resolution_operation_bounds_fail_closed(monkeypatch):
    securities, titles, tickers = _catalog()
    individual_sizes = []
    for value in (securities, titles, tickers):
        budget = mapping_module._ProjectionBudget()
        mapping_module._project_reference(value, budget=budget)
        individual_sizes.append(budget.text_characters)
    monkeypatch.setattr(
        mapping_module,
        "MAX_FORM4_PIT_SECURITY_MAPPING_TEXT_CHARACTERS",
        max(individual_sizes),
    )
    with pytest.raises(Form4PitSecurityMappingError, match="text bound"):
        _build(monkeypatch)

    monkeypatch.setattr(
        mapping_module,
        "MAX_FORM4_PIT_SECURITY_MAPPING_TEXT_CHARACTERS",
        64_000_000,
    )
    monkeypatch.setattr(
        mapping_module,
        "MAX_FORM4_PIT_SECURITY_MAPPING_RESOLUTION_OPERATIONS",
        0,
    )
    with pytest.raises(
        Form4PitSecurityMappingError,
        match="reference validation exceeds the operation bound",
    ):
        _build(monkeypatch)

    monkeypatch.setattr(
        mapping_module,
        "MAX_FORM4_PIT_SECURITY_MAPPING_RESOLUTION_OPERATIONS",
        1,
    )
    with pytest.raises(
        Form4PitSecurityMappingError,
        match="reference validation exceeds the operation bound",
    ):
        _build(monkeypatch)

    monkeypatch.setattr(
        mapping_module,
        "MAX_FORM4_PIT_SECURITY_MAPPING_RESOLUTION_OPERATIONS",
        0,
    )
    with pytest.raises(
        Form4PitSecurityMappingError,
        match="security mapping exceeds the resolution operation bound",
    ):
        _build(monkeypatch, securities=(_security(),), titles=(), tickers=())

    monkeypatch.setattr(
        mapping_module,
        "MAX_FORM4_PIT_SECURITY_MAPPING_RESOLUTION_OPERATIONS",
        8,
    )
    with pytest.raises(
        Form4PitSecurityMappingError,
        match="security mapping exceeds the resolution operation bound",
    ):
        _build(monkeypatch)


def test_rich_mapping_path_charges_every_resolution_scan(monkeypatch):
    charges = []
    original_charge = mapping_module._ResolutionBudget.charge

    def recording_charge(self, count):
        charges.append(count)
        original_charge(self, count)

    monkeypatch.setattr(
        mapping_module._ResolutionBudget,
        "charge",
        recording_charge,
    )
    _build(monkeypatch)
    assert charges == [2, 2, 2, 1, 1, 1] * 2


def test_reference_shapes_timestamps_and_intervals_fail_closed(monkeypatch):
    with pytest.raises(Form4PitSecurityMappingError, match="half-open"):
        _security(valid_from=date(2026, 1, 2), valid_to=date(2026, 1, 2))
    with pytest.raises(Form4PitSecurityMappingError, match="canonical UTC"):
        _security(available_at_utc="2026-01-01")
    with pytest.raises(Form4PitSecurityMappingError, match="closure evidence"):
        _security(
            valid_to=date(2027, 1, 1),
            valid_to_available_at_utc=None,
        )
    securities, titles, tickers = _catalog()
    _, grouping = ib2b._group(monkeypatch, (ib2b._spec(1),))
    with pytest.raises(Form4PitSecurityMappingError, match="exact tuples"):
        build_form4_pit_security_mapping(
            grouping,
            security_records=list(securities),
            title_intervals=titles,
            ticker_intervals=tickers,
            reference_id="synthetic-offline-reference",
            reference_version="v1",
            reference_sha256=REFERENCE_SHA256,
            builder_git_commit=BUILDER_COMMIT,
        )


def test_public_output_types_are_factory_gated_and_hash_bound(monkeypatch):
    _, result = _build(monkeypatch)
    with pytest.raises(Form4PitSecurityMappingError, match="factory-created"):
        replace(result.rows[0])
    with pytest.raises(Form4PitSecurityMappingError, match="factory-created"):
        replace(result.identity)
    with pytest.raises(Form4PitSecurityMappingError, match="factory-created"):
        replace(result)

    forged_row = _forge(result.rows[0], mapping_row_id="0" * 64)
    with pytest.raises(Form4PitSecurityMappingError, match="row ID"):
        Form4PitSecurityMappingRow.__post_init__(
            forged_row,
            mapping_module._ROW_FACTORY_TOKEN,
        )
    forged_identity = _forge(result.identity, structurally_mapped_count=0)
    with pytest.raises(Form4PitSecurityMappingError, match="counts"):
        Form4PitSecurityMappingIdentity.__post_init__(
            forged_identity,
            mapping_module._IDENTITY_FACTORY_TOKEN,
        )


def test_mapping_result_replay_crosslinks_every_resolved_reference(monkeypatch):
    _, result = _build(monkeypatch)
    bad_row = _forge(result.rows[0], security_interval_asof_id="f" * 64)
    bad_row = _forge(
        bad_row,
        mapping_row_id=hash_payload(mapping_module._mapping_row_payload(bad_row)),
    )
    rows = (bad_row,)
    identity = _forge(
        result.identity,
        mapping_row_inventory_hash=hash_payload([bad_row.to_payload()]),
    )
    identity = _forge(
        identity,
        mapping_id=(
            "form4-pit-security-mapping-"
            f"{hash_payload(mapping_module._mapping_identity_payload(identity))[:16]}"
        ),
    )
    forged = _forge(result, identity=identity, rows=rows)
    with pytest.raises(Form4PitSecurityMappingError, match="resolved reference"):
        Form4PitSecurityMapping.__post_init__(
            forged,
            mapping_module._MAPPING_FACTORY_TOKEN,
        )


def test_mapping_result_replay_refuses_false_quarantine_and_inactive_id(
    monkeypatch,
):
    _, result = _build(monkeypatch)
    false_quarantine = _forge(
        result.rows[0],
        resolution_outcomes=(
            Form4PitSecurityMappingOutcome.NO_ACTIVE_TICKER_QUARANTINED,
        ),
        security_id=None,
        share_class_id=None,
        security_class_normalized=None,
        ticker=None,
        exchange=None,
        country=None,
        security_interval_asof_id=None,
        title_interval_asof_id=None,
        ticker_interval_asof_id=None,
        title_mapping_kind=None,
        point_in_time_mapping_structurally_resolved=False,
    )
    forged = _rehash_result_with_row(result, false_quarantine)
    with pytest.raises(Form4PitSecurityMappingError, match="replay"):
        Form4PitSecurityMapping.__post_init__(
            forged,
            mapping_module._MAPPING_FACTORY_TOKEN,
        )

    old = _security(
        valid_to=date(2026, 8, 1),
        valid_to_available_at_utc="2026-07-01T00:00:00+00:00",
        evidence_id="security-old",
    )
    current = _security(
        valid_from=date(2026, 8, 1),
        evidence_id="security-current",
    )
    _, interval_result = _build(
        monkeypatch,
        securities=(old, current),
        titles=(_title(valid_from=date(2026, 8, 1)),),
        tickers=(_ticker(valid_from=date(2026, 8, 1)),),
    )
    inactive_reference = _forge(
        interval_result.rows[0],
        security_interval_asof_id=old.security_record_id,
    )
    forged = _rehash_result_with_row(interval_result, inactive_reference)
    with pytest.raises(Form4PitSecurityMappingError, match="replay"):
        Form4PitSecurityMapping.__post_init__(
            forged,
            mapping_module._MAPPING_FACTORY_TOKEN,
        )


def test_mapping_result_has_process_local_provenance(monkeypatch):
    _, result = _build(monkeypatch)
    assert mapping_module._is_factory_created_form4_pit_security_mapping(result)
    fingerprint = mapping_module._mapping_provenance_fingerprint(result)
    assert mapping_module._matches_factory_created_form4_pit_security_mapping_fingerprint(
        result,
        fingerprint,
    )
    assert not mapping_module._matches_factory_created_form4_pit_security_mapping_fingerprint(
        result,
        "0" * 64,
    )
    clone = _forge(result)
    Form4PitSecurityMapping.__post_init__(
        clone,
        mapping_module._MAPPING_FACTORY_TOKEN,
    )
    assert not mapping_module._is_factory_created_form4_pit_security_mapping(clone)


@pytest.mark.parametrize(
    "field",
    (
        "official_profile_compatibility_verified",
        "official_amendment_link_verified",
        "complete_amendment_coverage_verified",
        "official_security_master_compatibility_verified",
        "point_in_time_issuer_identity_verified",
        "point_in_time_reporting_owner_identity_verified",
        "point_in_time_security_identity_verified",
        "point_in_time_transaction_identity_verified",
        "ordinary_equity_classification_verified",
        "canonical_filter_authorized",
        "lot_aggregation_authorized",
        "sec_access_authorized",
        "provider_access_authorized",
        "outcomes_authorized",
        "qc_execution_authorized",
        "deployment_authorized",
        "trading_authorized",
    ),
)
def test_every_identity_authority_escalation_is_refused(monkeypatch, field):
    _, result = _build(monkeypatch)
    forged = _forge(result.identity, **{field: True})
    with pytest.raises(Form4PitSecurityMappingError, match="claims authority"):
        Form4PitSecurityMappingIdentity.__post_init__(
            forged,
            mapping_module._IDENTITY_FACTORY_TOKEN,
        )


@pytest.mark.parametrize(
    "field",
    (
        "point_in_time_issuer_identity_verified",
        "point_in_time_reporting_owner_identity_verified",
        "point_in_time_security_identity_verified",
        "point_in_time_transaction_identity_verified",
        "ordinary_equity_classification_verified",
        "canonical_filter_authorized",
        "lot_aggregation_authorized",
        "outcomes_authorized",
        "qc_execution_authorized",
        "deployment_authorized",
        "trading_authorized",
    ),
)
def test_every_row_authority_escalation_is_refused(monkeypatch, field):
    _, result = _build(monkeypatch)
    forged = _forge(result.rows[0], **{field: True})
    with pytest.raises(Form4PitSecurityMappingError, match="claims downstream"):
        Form4PitSecurityMappingRow.__post_init__(
            forged,
            mapping_module._ROW_FACTORY_TOKEN,
        )


@pytest.mark.parametrize(
    ("target", "field"),
    (
        ("identity", "authorized_outcome_looks"),
        ("identity", "consumed_outcome_looks"),
        ("row", "authorized_outcome_looks"),
        ("row", "consumed_outcome_looks"),
    ),
)
def test_every_outcome_look_counter_escalation_is_refused(
    monkeypatch,
    target,
    field,
):
    _, result = _build(monkeypatch)
    value = result.identity if target == "identity" else result.rows[0]
    forged = _forge(value, **{field: 1})
    if target == "identity":
        with pytest.raises(Form4PitSecurityMappingError, match="claims authority"):
            Form4PitSecurityMappingIdentity.__post_init__(
                forged,
                mapping_module._IDENTITY_FACTORY_TOKEN,
            )
    else:
        with pytest.raises(
            Form4PitSecurityMappingError,
            match="claims downstream authority",
        ):
            Form4PitSecurityMappingRow.__post_init__(
                forged,
                mapping_module._ROW_FACTORY_TOKEN,
            )


def test_all_authority_properties_and_look_counters_remain_zero(monkeypatch):
    _, result = _build(monkeypatch)
    assert result.official_profile_compatibility_verified is False
    assert result.official_amendment_link_verified is False
    assert result.complete_amendment_coverage_verified is False
    assert result.official_security_master_compatibility_verified is False
    assert result.point_in_time_issuer_identity_verified is False
    assert result.point_in_time_reporting_owner_identity_verified is False
    assert result.point_in_time_security_identity_verified is False
    assert result.point_in_time_transaction_identity_verified is False
    assert result.ordinary_equity_classification_verified is False
    assert result.canonical_filter_authorized is False
    assert result.lot_aggregation_authorized is False
    assert result.sec_access_authorized is False
    assert result.provider_access_authorized is False
    assert result.outcomes_authorized is False
    assert result.qc_execution_authorized is False
    assert result.deployment_authorized is False
    assert result.trading_authorized is False
    assert result.authorized_outcome_looks == 0
    assert result.consumed_outcome_looks == 0


def test_ib2c_module_has_exact_offline_import_surface_and_no_float():
    source = Path(mapping_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert imports == {
        "__future__",
        "re",
        "threading",
        "weakref",
        "dataclasses",
        "datetime",
        "enum",
        "zoneinfo",
        "data.hashing",
        "research.insider_buying.form4_observed_identity_inventory",
        "research.insider_buying.form4_provisional_disposition_report",
        "research.insider_buying.form4_sec_entity_grouping",
    }
    assert not any(
        isinstance(node, ast.Constant) and type(node.value) is float
        for node in ast.walk(tree)
    )
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"eval", "exec", "float", "__import__"}
        for node in ast.walk(tree)
    )


# --- Claude review additions (2026-09-07): guards that survived targeted mutation ---


def _rehash_row(row, **updates):
    row = _forge(row, **updates)
    return _forge(
        row,
        mapping_row_id=hash_payload(mapping_module._mapping_row_payload(row)),
    )


def _rehash_result_with_rows(result, rows):
    rows = tuple(rows)
    mapped = sum(row.point_in_time_mapping_structurally_resolved for row in rows)
    manual = sum(
        row.title_mapping_kind is Form4SecurityTitleMappingKind.MANUAL_EXCEPTION
        for row in rows
    )
    identity = _forge(
        result.identity,
        mapping_row_inventory_hash=hash_payload([row.to_payload() for row in rows]),
        mapping_row_count=len(rows),
        structurally_mapped_count=mapped,
        security_mapping_quarantined_count=len(rows) - mapped,
        manual_exception_resolution_count=manual,
    )
    identity = _forge(
        identity,
        mapping_id=(
            "form4-pit-security-mapping-"
            f"{hash_payload(mapping_module._mapping_identity_payload(identity))[:16]}"
        ),
    )
    return _forge(result, identity=identity, rows=rows)


def _replay_row(row) -> None:
    Form4PitSecurityMappingRow.__post_init__(row, mapping_module._ROW_FACTORY_TOKEN)


def _replay_result(result) -> None:
    Form4PitSecurityMapping.__post_init__(
        result,
        mapping_module._MAPPING_FACTORY_TOKEN,
    )


@pytest.mark.parametrize(
    "updates",
    (
        {"document_type": "4", "amends_accession": "0000123456-26-000001"},
        {"document_type": "4/A", "amends_accession": None},
        {
            "document_type": "4/A",
            "amends_accession": "0000123456-26-000009",
            "original_accession": "0000123456-26-000008",
        },
    ),
    ids=("original-with-amends", "amendment-without-amends", "amendment-original-mismatch"),
)
def test_row_constructor_refuses_inconsistent_amendment_lineage(monkeypatch, updates):
    """Original/amended lineage: a coherent row cannot carry a contradictory chain."""
    _, result = _build(monkeypatch)
    forged = _rehash_row(result.rows[0], **updates)
    with pytest.raises(Form4PitSecurityMappingError, match="amendment lineage"):
        _replay_row(forged)


def test_row_constructor_refuses_partial_mappings_in_both_directions(monkeypatch):
    """A mapped row must be complete; a quarantined row must carry nothing."""
    _, mapped = _build(monkeypatch)
    incomplete = _rehash_row(mapped.rows[0], ticker=None)
    with pytest.raises(Form4PitSecurityMappingError, match="complete structural mapping"):
        _replay_row(incomplete)
    unresolved_flag = _rehash_row(
        mapped.rows[0],
        point_in_time_mapping_structurally_resolved=False,
    )
    with pytest.raises(Form4PitSecurityMappingError, match="complete structural mapping"):
        _replay_row(unresolved_flag)

    _, quarantined = _build(monkeypatch, tickers=())
    assert quarantined.rows[0].resolution_outcomes == (
        Form4PitSecurityMappingOutcome.NO_ACTIVE_TICKER_QUARANTINED,
    )
    leaked_security = _rehash_row(quarantined.rows[0], security_id="sec-fixture-common")
    with pytest.raises(Form4PitSecurityMappingError, match="partial mapping"):
        _replay_row(leaked_security)
    resolved_flag = _rehash_row(
        quarantined.rows[0],
        point_in_time_mapping_structurally_resolved=True,
    )
    with pytest.raises(Form4PitSecurityMappingError, match="partial mapping"):
        _replay_row(resolved_flag)
    mixed_outcomes = _rehash_row(
        quarantined.rows[0],
        resolution_outcomes=(
            Form4PitSecurityMappingOutcome.NO_ACTIVE_TICKER_QUARANTINED,
            Form4PitSecurityMappingOutcome.MAPPED_STRUCTURALLY,
        ),
    )
    with pytest.raises(Form4PitSecurityMappingError, match="partial mapping"):
        _replay_row(mixed_outcomes)


def test_row_constructor_refuses_owner_quarantine_promotion_shapes(monkeypatch):
    """The row mirrors IB-2B: no owner on a quarantined row, no SINGLE beside a quarantine."""
    joint = ib2b._spec(
        1,
        owners=(
            ib2b._Owner(),
            ib2b._Owner(cik=ib2b.OTHER_OWNER_CIK, name="Joint Owner"),
        ),
    )
    _, result = _build(monkeypatch, (joint,))
    row = result.rows[0]
    assert row.attributed_owner_cik is None
    with_owner = _rehash_row(row, attributed_owner_cik=ib2b.OWNER_CIK)
    with pytest.raises(Form4PitSecurityMappingError, match="quarantine was promoted"):
        _replay_row(with_owner)
    with_candidate = _rehash_row(row, attributed_owner_candidate_id="a" * 64)
    with pytest.raises(Form4PitSecurityMappingError, match="quarantine was promoted"):
        _replay_row(with_candidate)
    single_beside_quarantine = _rehash_row(
        row,
        owner_attribution_outcomes=(
            Form4OwnerAttributionOutcome.SINGLE_COMPLETE_OWNER_CIK_ATTRIBUTED,
            Form4OwnerAttributionOutcome.MULTIPLE_OWNER_SET_QUARANTINED,
        ),
    )
    with pytest.raises(Form4PitSecurityMappingError, match="quarantine was promoted"):
        _replay_row(single_beside_quarantine)


def test_result_constructor_requires_canonical_row_order(monkeypatch):
    _, result = _build(monkeypatch, ib2b._pair())
    assert len(result.rows) == 2
    reversed_rows = _rehash_result_with_rows(result, reversed(result.rows))
    with pytest.raises(Form4PitSecurityMappingError, match="order is not canonical"):
        _replay_result(reversed_rows)


def test_result_constructor_refuses_duplicate_rows(monkeypatch):
    _, result = _build(monkeypatch)
    duplicated = _rehash_result_with_rows(result, (result.rows[0], result.rows[0]))
    with pytest.raises(Form4PitSecurityMappingError, match="not exhaustive"):
        _replay_result(duplicated)


def test_identity_constructor_binds_manual_count_to_mapped_count(monkeypatch):
    _, quarantined = _build(monkeypatch, tickers=())
    assert quarantined.identity.structurally_mapped_count == 0
    forged = _forge(quarantined.identity, manual_exception_resolution_count=1)
    with pytest.raises(Form4PitSecurityMappingError, match="counts are invalid"):
        Form4PitSecurityMappingIdentity.__post_init__(
            forged,
            mapping_module._IDENTITY_FACTORY_TOKEN,
        )


def test_reference_preflight_count_refuses_before_any_projection(monkeypatch):
    """Resource ordering: the count preflight must refuse before projection work starts."""
    monkeypatch.setattr(mapping_module, "MAX_FORM4_PIT_SECURITY_RECORDS", 0)

    def projection_must_not_run(*_args, **_kwargs):
        raise AssertionError("projection ran before the count preflight")

    monkeypatch.setattr(mapping_module, "_capture_reference", projection_must_not_run)
    with pytest.raises(Form4PitSecurityMappingError, match="preflight count exceeds"):
        _build(monkeypatch)


@pytest.mark.parametrize(
    ("constant_name", "value", "expected_message"),
    (
        (
            "MAX_FORM4_PIT_SECURITY_MAPPING_PROJECTION_NODES",
            1,
            "reference input exceeds the node bound",
        ),
        (
            "MAX_FORM4_PIT_SECURITY_MAPPING_PROJECTION_DEPTH",
            0,
            "reference input exceeds the depth bound",
        ),
    ),
)
def test_reference_projection_node_and_depth_bounds_fail_closed(
    monkeypatch,
    constant_name,
    value,
    expected_message,
):
    monkeypatch.setattr(mapping_module, constant_name, value)
    with pytest.raises(Form4PitSecurityMappingError, match=expected_message):
        _build(monkeypatch)


def test_closure_availability_cannot_precede_base_availability():
    with pytest.raises(Form4PitSecurityMappingError, match="closure predates base"):
        _security(
            valid_to=date(2027, 1, 1),
            available_at_utc="2020-01-01T00:00:00+00:00",
            valid_to_available_at_utc="2019-06-01T00:00:00+00:00",
        )
