"""Fixture-only predecision refusal checks; no QC, provider, outcome or order I/O."""

import copy
from datetime import datetime
import gzip
import hashlib
import json
from dataclasses import FrozenInstanceError

import pytest

from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2_qc import fresh_six_universe_snapshot as producer
from research.analyst_revisions_v2_qc import six_universe_forward_predecision as subject
from tests.analyst_revisions_v2 import test_qc_fresh_six_universe_snapshot as producer_tests


SESSION = "2026-09-28"


def _qc_source(*, fundamentals=False):
    common = {
        "qc_source_end_time_ny": "2026-09-25T17:00:00-04:00",
        "qc_callback_time_ny": "2026-09-28T09:00:00-04:00",
        "collection_status": "valid",
        "degenerate_reason": None,
        "diagnostic_raw_end_time_calendar_lag_days": 3,
        "source_row_count": 2,
    }
    if fundamentals:
        return {
            **common,
            "null_market_cap_count": 0,
            "nonpositive_market_cap_count": 0,
            "invalid_market_cap_count": 0,
            "positive_market_caps": [["A-SID", "100"], ["QCOM-SID", "200"]],
        }
    return {
        **common,
        "positive_constituents": [["A-SID", "0.50"], ["QCOM-SID", "0.50"]],
        "display_qcom_sids": ["QCOM-SID"],
    }


def _documents():
    qc = {
        "schema": "arv2-fresh-six-universe-input-snapshot-v1",
        "decision_session": SESSION,
        "qc_decision_time_ny": "2026-09-28T09:20:00-04:00",
        "capture_time_utc": "2026-10-01T00:00:00+00:00",
        "naive_qc_times_interpreted_as": "America/New_York",
        "qc_callback_is_vendor_availability_time": False,
        "point_in_time_vendor_availability_proven": False,
        "decision_ready": False,
        "order_and_outcome_access": False,
        "qcom_exact_sid_status": "joined",
        "superseded_degenerate_callback_count_by_source": {
            source: 0 for source in subject.SOURCES
        },
        "superseded_degenerate_callback_count": 0,
        "sources": {
            "FUNDAMENTALS": _qc_source(fundamentals=True),
            **{etf: _qc_source() for etf in subject.ETFS},
        },
    }
    vendor = {
        "schema": "arv2-forward-vendor-quality-receipt-v1",
        "purpose": "development_data_quality_only_not_arv2_9_confirmation",
        "capture_id": "test-capture",
        "capture_sha256": "a" * 64,
        "capture_manifest_sha256": "b" * 64,
        "capture_started_at": "2026-09-28T13:00:00.000000Z",
        "capture_completed_at": "2026-09-28T13:05:00.000000Z",
        "capture_transport": "massive_https_bearer_default_session",
        "first_event_date": SESSION,
        "last_event_date": SESSION,
        "source_row_count": 0,
        "roles": [
            {"role": role, "events": []} for role in
            ("analyst_ratings", "earnings", "corporate_guidance")
        ],
        "point_in_time_proven": False,
        "outcome_reads": 0,
        "qc_calls": 0,
        "paper_look_committed": False,
    }
    mapping = {
        "schema": subject.MAPPING_SCHEMA,
        "decision_session": SESSION,
        "qc_snapshot_sha256": "",
        "vendor_receipt_sha256": "",
        "qcom_qc_sid": "QCOM-SID",
        "rows": [
            {"vendor_security_id": vendor_id, "qc_sid": sid,
             "valid_from_session": "2020-01-01", "valid_to_session": None,
             "available_at_utc": "2026-09-25T12:00:00Z"}
            for vendor_id, sid in (("V-A", "A-SID"), ("V-Q", "QCOM-SID"))
        ],
    }
    holdings_identity = {
        "schema": subject.HOLDINGS_IDENTITY_SCHEMA,
        "decision_session": SESSION,
        "qc_snapshot_sha256": "",
        "acquired_at_utc": "2026-09-28T13:10:00Z",
        "rows": [
            {"qc_sid": qc_sid, "security_id": security_id,
             "valid_from_session": "2020-01-01", "valid_to_session": None,
             "available_at_utc": "2026-09-25T12:00:00Z"}
            for qc_sid, security_id in (("A-SID", "SEC-A"), ("QCOM-SID", "SEC-QCOM"))
        ],
    }
    prices = {
        "schema": subject.PRICE_SCHEMA,
        "decision_session": SESSION,
        "qc_snapshot_sha256": "",
        "source_time_utc": "2026-09-25T20:00:00Z",
        "positive_reference_prices": [["A-SID", "10"], ["QCOM-SID", "20"]],
    }
    return qc, vendor, mapping, holdings_identity, prices


def _ascii_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _run(
    qc, vendor, mapping, holdings_identity, prices, *,
    holdings_identity_wire=None, holdings_identity_pin=None,
):
    qc_bytes = _ascii_bytes(qc)
    vendor_bytes = canonical_json_bytes(vendor)
    qc_sha = hashlib.sha256(qc_bytes).hexdigest()
    vendor_sha = hashlib.sha256(vendor_bytes).hexdigest()
    mapping = copy.deepcopy(mapping)
    holdings_identity = copy.deepcopy(holdings_identity)
    prices = copy.deepcopy(prices)
    mapping["qc_snapshot_sha256"] = qc_sha
    mapping["vendor_receipt_sha256"] = vendor_sha
    if holdings_identity["qc_snapshot_sha256"] == "":
        holdings_identity["qc_snapshot_sha256"] = qc_sha
    prices["qc_snapshot_sha256"] = qc_sha
    mapping_bytes = _ascii_bytes(mapping)
    holdings_identity_bytes = (
        _ascii_bytes(holdings_identity)
        if holdings_identity_wire is None else holdings_identity_wire
    )
    price_bytes = _ascii_bytes(prices)
    return subject.build_predecision_diagnostic(
        decision_session=SESSION,
        qc_snapshot_bytes=qc_bytes,
        qc_snapshot_sha256=qc_sha,
        vendor_receipt_bytes=vendor_bytes,
        vendor_receipt_sha256=vendor_sha,
        crosswalk_bytes=mapping_bytes,
        crosswalk_sha256=hashlib.sha256(mapping_bytes).hexdigest(),
        holdings_identity_bytes=holdings_identity_bytes,
        holdings_identity_sha256=(
            hashlib.sha256(holdings_identity_bytes).hexdigest()
            if holdings_identity_pin is None else holdings_identity_pin
        ),
        reference_price_bytes=price_bytes,
        reference_price_sha256=hashlib.sha256(price_bytes).hexdigest(),
    )


def test_all_three_arms_share_one_digest_but_never_become_decision_ready():
    report = _run(*_documents())
    assert report.schema == subject.SCHEMA
    assert report.decision_ready is False
    assert report.order_or_outcome_access is False
    assert report.refusal_codes == (
        "VENDOR_PUBLICATION_AVAILABILITY_UNPROVEN",
        "HOLDINGS_SECURITY_IDENTITY_PROVENANCE_UNPROVEN",
        "CROSSWALK_INDEPENDENT_REVIEW_UNPROVEN",
        "REFERENCE_PRICE_PROVENANCE_UNPROVEN",
        "PRICE_FRESHNESS_UNPROVEN",
    )
    assert [arm.candidate_id for arm in report.arms] == [
        "ARV2_FORWARD_AR_OFF", "ARV2_FORWARD_AR_100", "ARV2_FORWARD_AR_200",
    ]
    assert {arm.common_input_sha256 for arm in report.arms} == {report.common_input_sha256}
    assert "QCOM-SID" not in repr(report)
    with pytest.raises(FrozenInstanceError):
        report.decision_ready = True


@pytest.mark.parametrize(("part", "change", "reason"), [
    ("qc", lambda d: d["sources"]["QQQ"].update(qc_callback_time_ny="2026-09-28T09:21:00-04:00"), "QC_SOURCE_NOT_PREDECISION"),
    ("qc", lambda d: d["sources"]["QQQ"].update(qc_source_end_time_ny="2026-09-28T09:10:00-04:00"), "QC_SOURCE_END_FOLLOWS_CALLBACK"),
    ("qc", lambda d: d["sources"]["QQQ"].update(diagnostic_raw_end_time_calendar_lag_days=2), "QC_DIAGNOSTIC_SOURCE_AGE_CHANGED"),
    ("qc", lambda d: d.update(capture_time_utc=None), "QC_CAPTURE_CLOCK_INVALID"),
    ("qc", lambda d: d.update(qcom_exact_sid_status="unmatched_positive_cap"), "QC_QCOM_STATUS_CHANGED"),
    ("qc", lambda d: d["sources"]["FUNDAMENTALS"].update(positive_market_caps=[]), "QC_VALID_FUNDAMENTALS_HAVE_NO_POSITIVE_CAP"),
    ("qc", lambda d: d.update(decision_ready=True), "QC_SNAPSHOT_AUTHORITY_CHANGED"),
    ("qc", lambda d: d["sources"]["QQQ"].update(source_row_count=True), "QC_SOURCE_CENSUS_INVALID"),
    ("qc", lambda d: d["sources"]["QQQ"].update(source_row_count=25_001), "QC_SOURCE_CENSUS_INVALID"),
    ("qc", lambda d: d["sources"]["QQQ"].update(source_row_count=3), "ETF_UNWEIGHTED_CONSTITUENT_ROWS_UNRESOLVED"),
    ("qc", lambda d: d.update(superseded_degenerate_callback_count=True), "QC_SUPERSEDED_CALLBACK_CENSUS_CHANGED"),
    ("qc", lambda d: d["sources"].pop("REMX"), "QC_SOURCE_CENSUS_CHANGED"),
    ("qc", lambda d: d["sources"]["QQQ"].update(positive_constituents=[["A-SID", "0.98"], ["UNKNOWN-SID", "0.02"]]), "ETF_EXACT_IDENTITY_WEIGHT_BELOW_99_PERCENT"),
    ("qc", lambda d: d["sources"]["QQQ"].update(positive_constituents=[["A-SID", "0.50"], ["QCOM-SID", "0.40"]]), "ETF_TOTAL_REPORTED_WEIGHT_INVALID"),
    ("qc", lambda d: d["sources"]["QQQ"].update(positive_constituents=[["A-SID", "1e-1000000000"], ["QCOM-SID", "0.50"]]), "QC_MEMBER_ROWS_INVALID"),
    ("vendor", lambda d: d.update(capture_completed_at="2026-09-28T13:21:00.000000Z"), "VENDOR_CAPTURE_NOT_PREDECISION"),
    ("vendor", lambda d: d.update(capture_started_at="2026-09-27T23:50:00.000000Z"), "VENDOR_CAPTURE_NOT_PREDECISION"),
    ("vendor", lambda d: d.update(first_event_date="2026-09-27"), "VENDOR_RECEIPT_SESSION_OR_TRANSPORT_CHANGED"),
    ("vendor", lambda d: d.update(point_in_time_proven=True), "VENDOR_RECEIPT_INVALID"),
    ("mapping", lambda d: d["rows"][1].update(qc_sid="A-SID"), "CROSSWALK_AMBIGUOUS_EXACT_IDENTITY"),
    ("mapping", lambda d: d["rows"][1].update(available_at_utc="2026-09-28T13:21:00Z"), "CROSSWALK_NOT_AVAILABLE_BY_DECISION"),
    ("mapping", lambda d: d["rows"][1].update(valid_to_session=SESSION), "CROSSWALK_NOT_VALID_AS_OF_DECISION"),
    ("mapping", lambda d: d["rows"][1].update(valid_from_session="not-a-date"), "CROSSWALK_DATE_INVALID"),
    ("mapping", lambda d: d.update(qcom_qc_sid=None), "QCOM_EXACT_IDENTITY_UNRESOLVED"),
    ("mapping", lambda d: d["rows"][1].pop("qc_sid"), "CROSSWALK_ROW_SHAPE_CHANGED"),
    ("holdings_identity", lambda d: d.update(decision_session="2026-09-25"), "HOLDINGS_IDENTITY_INPUT_BINDING_CHANGED"),
    ("holdings_identity", lambda d: d.update(qc_snapshot_sha256="f" * 64), "HOLDINGS_IDENTITY_INPUT_BINDING_CHANGED"),
    ("holdings_identity", lambda d: d.update(acquired_at_utc="2026-09-27T13:10:00Z"), "HOLDINGS_IDENTITY_ACQUISITION_NOT_PREDECISION"),
    ("holdings_identity", lambda d: d.update(acquired_at_utc="2026-09-28T13:20:00Z"), "HOLDINGS_IDENTITY_ACQUISITION_NOT_PREDECISION"),
    ("holdings_identity", lambda d: d["rows"][1].update(available_at_utc="2026-09-28T13:11:00Z"), "HOLDINGS_IDENTITY_NOT_AVAILABLE_BY_ACQUISITION"),
    ("holdings_identity", lambda d: d["rows"][1].update(valid_to_session=SESSION), "HOLDINGS_IDENTITY_NOT_VALID_AS_OF_DECISION"),
    ("holdings_identity", lambda d: d["rows"][1].update(valid_from_session="not-a-date"), "HOLDINGS_IDENTITY_DATE_INVALID"),
    ("holdings_identity", lambda d: d["rows"][1].update(qc_sid="A-SID"), "HOLDINGS_IDENTITY_AMBIGUOUS_EXACT_SECURITY"),
    ("holdings_identity", lambda d: d["rows"][1].update(security_id="SEC-A"), "HOLDINGS_IDENTITY_AMBIGUOUS_EXACT_SECURITY"),
    ("holdings_identity", lambda d: d["rows"][1].update(security_id="SEC\nQCOM"), "HOLDINGS_IDENTITY_SECURITY_ID_INVALID"),
    ("holdings_identity", lambda d: d["rows"][1].pop("security_id"), "HOLDINGS_IDENTITY_ROW_SHAPE_CHANGED"),
    ("holdings_identity", lambda d: d["rows"][1].update(ticker="QCOM"), "HOLDINGS_IDENTITY_ROW_SHAPE_CHANGED"),
    ("holdings_identity", lambda d: d["rows"].pop(), "ETF_EXACT_IDENTITY_WEIGHT_BELOW_99_PERCENT"),
    ("prices", lambda d: d.update(source_time_utc="2026-09-28T13:21:00Z"), "PRICE_NOT_PREDECISION"),
    ("prices", lambda d: d.update(positive_reference_prices=[["A-SID", "10"]]), "QCOM_CAP_WEIGHT_OR_REFERENCE_PRICE_UNAVAILABLE"),
    ("prices", lambda d: d.update(positive_reference_prices=[["A-SID", "10"], ["QCOM-SID", "0"]]), "PRICE_ROWS_INVALID"),
    ("qc", lambda d: (d["sources"]["FUNDAMENTALS"].update(source_row_count=1, positive_market_caps=[["A-SID", "100"]]), d.update(qcom_exact_sid_status="unmatched_positive_cap")), "QCOM_CAP_WEIGHT_OR_REFERENCE_PRICE_UNAVAILABLE"),
])
def test_unsafe_claims_refuse(part, change, reason):
    documents = dict(zip(("qc", "vendor", "mapping", "holdings_identity", "prices"), _documents(), strict=True))
    change(documents[part])
    with pytest.raises(subject.ForwardPredecisionError, match=reason):
        _run(**documents)


def test_display_ticker_hint_never_repairs_missing_exact_qcom_sid():
    qc, vendor, mapping, holdings_identity, prices = _documents()
    mapping["rows"] = mapping["rows"][:1]
    with pytest.raises(subject.ForwardPredecisionError, match="QCOM_EXACT_IDENTITY_UNRESOLVED"):
        _run(qc, vendor, mapping, holdings_identity, prices)


def test_sparse_analyst_vendor_crosswalk_does_not_reduce_holdings_identity_coverage():
    qc, vendor, mapping, holdings_identity, prices = _documents()
    mapping["rows"] = mapping["rows"][1:]
    report = _run(qc, vendor, mapping, holdings_identity, prices)
    assert report.decision_ready is False
    assert "CROSSWALK_INDEPENDENT_REVIEW_UNPROVEN" in report.refusal_codes
    assert "HOLDINGS_SECURITY_IDENTITY_PROVENANCE_UNPROVEN" in report.refusal_codes


def test_exact_99_percent_security_identity_floor_accepts_but_subfloor_refuses():
    qc, vendor, mapping, holdings_identity, prices = _documents()
    qc["sources"]["QQQ"].update(
        positive_constituents=[["A-SID", "0.99"], ["UNMAPPED-SID", "0.01"]],
        display_qcom_sids=[],
    )
    assert _run(qc, vendor, mapping, holdings_identity, prices).decision_ready is False
    qc["sources"]["QQQ"]["positive_constituents"] = [
        ["A-SID", "0.98999999999999999999999999999"],
        ["UNMAPPED-SID", "0.01000000000000000000000000001"],
    ]
    with pytest.raises(subject.ForwardPredecisionError, match="ETF_EXACT_IDENTITY_WEIGHT_BELOW_99_PERCENT"):
        _run(qc, vendor, mapping, holdings_identity, prices)


def test_qcom_requires_both_holdings_identity_and_separate_vendor_crosswalk():
    qc, vendor, mapping, holdings_identity, prices = _documents()
    for etf in subject.ETFS:
        qc["sources"][etf]["positive_constituents"] = [
            ["A-SID", "0.995"], ["QCOM-SID", "0.005"],
        ]
    holdings_identity["rows"] = holdings_identity["rows"][:1]
    with pytest.raises(subject.ForwardPredecisionError, match="QCOM_EXACT_IDENTITY_UNRESOLVED"):
        _run(qc, vendor, mapping, holdings_identity, prices)


def test_holdings_identity_pin_canonical_bytes_and_common_digest_are_binding():
    qc, vendor, mapping, holdings_identity, prices = _documents()
    original = _run(qc, vendor, mapping, holdings_identity, prices)
    holdings_identity["rows"][0]["security_id"] = "SEC-A2"
    changed = _run(qc, vendor, mapping, holdings_identity, prices)
    assert changed.common_input_sha256 != original.common_input_sha256
    with pytest.raises(subject.ForwardPredecisionError, match="HOLDINGS_IDENTITY_SHA256_MISMATCH"):
        _run(qc, vendor, mapping, holdings_identity, prices, holdings_identity_pin="0" * 64)
    with pytest.raises(subject.ForwardPredecisionError, match="HOLDINGS_IDENTITY_NONCANONICAL"):
        _run(
            qc, vendor, mapping, holdings_identity, prices,
            holdings_identity_wire=_ascii_bytes(holdings_identity) + b" ",
        )


def test_holdings_identity_acquisition_at_session_midnight_is_allowed():
    qc, vendor, mapping, holdings_identity, prices = _documents()
    holdings_identity["acquired_at_utc"] = "2026-09-28T04:00:00Z"
    assert _run(qc, vendor, mapping, holdings_identity, prices).decision_ready is False


def test_exact_fraction_rejects_sub_99_percent_coverage_hidden_by_decimal_rounding():
    qc, vendor, mapping, holdings_identity, prices = _documents()
    qc["sources"]["QQQ"]["source_row_count"] = 3
    qc["sources"]["QQQ"]["positive_constituents"] = [
        ["A-SID", "0.48999999999999999999999999999"],
        ["QCOM-SID", "0.50"],
        ["UNMAPPED-SID", "0.01000000000000000000000000001"],
    ]
    with pytest.raises(subject.ForwardPredecisionError, match="ETF_EXACT_IDENTITY_WEIGHT_BELOW_99_PERCENT"):
        _run(qc, vendor, mapping, holdings_identity, prices)


def test_exact_fraction_rejects_sub_95_percent_total_hidden_by_decimal_rounding():
    qc, vendor, mapping, holdings_identity, prices = _documents()
    qc["sources"]["QQQ"]["positive_constituents"] = [
        ["A-SID", "0.50"],
        ["QCOM-SID", "0.44999999999999999999999999999"],
    ]
    with pytest.raises(subject.ForwardPredecisionError, match="ETF_TOTAL_REPORTED_WEIGHT_INVALID"):
        _run(qc, vendor, mapping, holdings_identity, prices)


def test_changed_or_noncanonical_bytes_cannot_be_relabelled_by_a_pin():
    qc, vendor, mapping, holdings_identity, prices = _documents()
    raw = _ascii_bytes(qc)
    with pytest.raises(subject.ForwardPredecisionError, match="QC_SNAPSHOT_SHA256_MISMATCH"):
        subject.build_predecision_diagnostic(
            decision_session=SESSION, qc_snapshot_bytes=raw,
            qc_snapshot_sha256="0" * 64, vendor_receipt_bytes=b"",
            vendor_receipt_sha256="0" * 64, crosswalk_bytes=b"",
            crosswalk_sha256="0" * 64, holdings_identity_bytes=b"",
            holdings_identity_sha256="0" * 64, reference_price_bytes=b"",
            reference_price_sha256="0" * 64,
        )
    # Rehashing changed whitespace does not create another canonical QC input.
    noncanonical = raw + b" "
    with pytest.raises(subject.ForwardPredecisionError, match="QC_SNAPSHOT_NONCANONICAL"):
        subject.build_predecision_diagnostic(
            decision_session=SESSION, qc_snapshot_bytes=noncanonical,
            qc_snapshot_sha256=hashlib.sha256(noncanonical).hexdigest(),
            vendor_receipt_bytes=b"", vendor_receipt_sha256="0" * 64,
            crosswalk_bytes=b"", crosswalk_sha256="0" * 64,
            holdings_identity_bytes=b"", holdings_identity_sha256="0" * 64,
            reference_price_bytes=b"", reference_price_sha256="0" * 64,
        )


def test_actual_producer_snapshot_bytes_pass_the_predecision_validator():
    """Both suites use hand-written snapshots; this binds the producer's real bytes.

    A renamed field or changed canonical form in the producer would otherwise
    leave both suites green while every real snapshot was refused.
    """
    algo = producer_tests._Algorithm()
    algo.time = datetime(2026, 9, 28, 9, 0)
    capture = producer.FreshSixUniverseSnapshot(algo, SESSION)
    end = datetime(2026, 9, 25, 17, 0)
    capture.accept("FUNDAMENTALS", [
        producer_tests._row("A-SID", "A", cap="100", end_time=end),
        producer_tests._row("QCOM-SID", "QCOM", cap="200", end_time=end),
    ])
    for etf in subject.ETFS:
        capture.accept(etf, [
            producer_tests._row("A-SID", "A", weight="0.50", end_time=end),
            producer_tests._row("QCOM-SID", "QCOM", weight="0.50", end_time=end),
        ])
    algo.time = datetime(2026, 9, 28, 9, 20)
    receipt = capture.persist_at_decision()
    qc_bytes = gzip.decompress(algo.object_store.values[receipt["object_store_key"]])
    qc_sha = hashlib.sha256(qc_bytes).hexdigest()
    assert qc_sha == receipt["canonical_sha256"]
    _, vendor, mapping, holdings_identity, prices = _documents()
    vendor_bytes = canonical_json_bytes(vendor)
    vendor_sha = hashlib.sha256(vendor_bytes).hexdigest()
    mapping["qc_snapshot_sha256"] = qc_sha
    mapping["vendor_receipt_sha256"] = vendor_sha
    holdings_identity["qc_snapshot_sha256"] = qc_sha
    prices["qc_snapshot_sha256"] = qc_sha
    mapping_bytes = _ascii_bytes(mapping)
    holdings_identity_bytes = _ascii_bytes(holdings_identity)
    price_bytes = _ascii_bytes(prices)
    report = subject.build_predecision_diagnostic(
        decision_session=SESSION,
        qc_snapshot_bytes=qc_bytes,
        qc_snapshot_sha256=qc_sha,
        vendor_receipt_bytes=vendor_bytes,
        vendor_receipt_sha256=vendor_sha,
        crosswalk_bytes=mapping_bytes,
        crosswalk_sha256=hashlib.sha256(mapping_bytes).hexdigest(),
        holdings_identity_bytes=holdings_identity_bytes,
        holdings_identity_sha256=hashlib.sha256(holdings_identity_bytes).hexdigest(),
        reference_price_bytes=price_bytes,
        reference_price_sha256=hashlib.sha256(price_bytes).hexdigest(),
    )
    assert report.decision_ready is False
    assert report.order_or_outcome_access is False
    assert {arm.common_input_sha256 for arm in report.arms} == {report.common_input_sha256}


@pytest.mark.parametrize(("part", "change", "reason"), [
    ("qc", lambda d: d["sources"]["QQQ"].update(qc_callback_time_ny="2026-09-28T09:20:00-04:00"), "QC_SOURCE_NOT_PREDECISION"),
    ("vendor", lambda d: d.update(capture_completed_at="2026-09-28T13:20:00.000000Z"), "VENDOR_CAPTURE_NOT_PREDECISION"),
    ("holdings_identity", lambda d: d.update(acquired_at_utc="2026-09-28T13:20:00Z"), "HOLDINGS_IDENTITY_ACQUISITION_NOT_PREDECISION"),
    ("mapping", lambda d: d["rows"][1].update(available_at_utc="2026-09-28T13:20:00Z"), "CROSSWALK_NOT_AVAILABLE_BY_DECISION"),
    ("mapping", lambda d: d["rows"].append({**d["rows"][0], "qc_sid": "OTHER-SID"}), "CROSSWALK_AMBIGUOUS_EXACT_IDENTITY"),
    ("qc", lambda d: d["sources"]["QQQ"].update(positive_constituents=[["A-SID", "0.5" + "0" * 126], ["QCOM-SID", "0.50"]]), "QC_MEMBER_ROWS_INVALID"),
    ("qc", lambda d: d["sources"]["FUNDAMENTALS"].update(qc_source_end_time_ny="2026-09-23T17:00:00-04:00", diagnostic_raw_end_time_calendar_lag_days=5), "QC_DIAGNOSTIC_SOURCE_AGE_CHANGED"),
])
def test_exact_cutoff_identity_length_and_age_boundaries_refuse(part, change, reason):
    """Each case sits exactly on a boundary that the one-minute-late cases miss:
    a callback, vendor capture, holdings acquisition or crosswalk row at 09:20,
    one vendor ID mapped to two QC SIDs, a 129-character weight, and five-day fundamentals."""
    documents = dict(zip(("qc", "vendor", "mapping", "holdings_identity", "prices"), _documents(), strict=True))
    change(documents[part])
    with pytest.raises(subject.ForwardPredecisionError, match=reason):
        _run(**documents)


def test_values_one_step_inside_each_boundary_are_accepted():
    qc, vendor, mapping, holdings_identity, prices = _documents()
    qc["sources"]["QQQ"]["qc_callback_time_ny"] = "2026-09-28T09:19:59-04:00"
    qc["sources"]["QQQ"]["positive_constituents"] = [["A-SID", "0.5" + "0" * 125], ["QCOM-SID", "0.50"]]
    qc["sources"]["FUNDAMENTALS"].update(
        qc_source_end_time_ny="2026-09-24T17:00:00-04:00",
        diagnostic_raw_end_time_calendar_lag_days=4,
    )
    vendor["capture_completed_at"] = "2026-09-28T13:19:59.999999Z"
    mapping["rows"][1]["available_at_utc"] = "2026-09-28T13:19:59Z"
    holdings_identity["acquired_at_utc"] = "2026-09-28T13:19:59Z"
    holdings_identity["rows"][1]["available_at_utc"] = "2026-09-28T13:19:59Z"
    report = _run(qc, vendor, mapping, holdings_identity, prices)
    assert report.decision_ready is False
