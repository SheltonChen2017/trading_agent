"""Offline-only, opt-in host validation for the eight-sleeve order envelope."""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest

from research.analyst_revisions_v2_qc import six_universe_cap90_submission as cap
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as relaxed
from research.analyst_revisions_v2_qc import six_universe_settlement_submission as common
from tests.analyst_revisions_v2.test_qc_relaxed_submission import order_fixture
from tests.analyst_revisions_v2.test_qc_six_universe_settlement_submission import _aggregate


EIGHT = ("SPY", "QQQ", "SOXX", "XLV", "REMX", "XLE", "XLI", "XLF")


def _historical_eight_base():
    aggregate, _ = _aggregate("R195")
    aggregate = {key: copy.deepcopy(aggregate[key]) for key in cap._AGGREGATE_FIELDS}
    sleeves = aggregate["sleeve_diagnostics"]
    sleeves["schema"] = cap._EIGHT_SLEEVE_SCHEMA
    for ticker in EIGHT[6:]:
        row = copy.deepcopy(sleeves["rows"][0])
        row[0] = row[1] = ticker
        sleeves["rows"].append(row)
        aggregate["constituent_collection_unavailable_universe_counts"][ticker] = 0
    aggregate["fallback_counts"] = {"SIX_ETF_BASKET": 8 * 261}
    return aggregate


def _recent_eight_order():
    aggregate, row, meta = order_fixture()
    aggregate["sleeve_diagnostics"]["schema"] = cap._EIGHT_SLEEVE_SCHEMA
    for ticker in EIGHT[6:]:
        sleeve = copy.deepcopy(aggregate["sleeve_diagnostics"]["rows"][0])
        sleeve[0] = sleeve[1] = ticker
        aggregate["sleeve_diagnostics"]["rows"].append(sleeve)
        aggregate["constituent_collection_unavailable_universe_counts"][ticker] = 0
    aggregate["fallback_counts"] = {"PARTIAL_STOCK_EXPOSURE_WITH_ETF_FALLBACK": 8 * 61}
    row["statistic_names"] = ["ARV2_EIGHT_GATE_ORDER_META", "ARV2_EIGHT_GATE_ORDER_AGGREGATES"]
    row["summary_schema"] = aggregate["schema"] = "arv2-eight-universe-order-aggregates-v1"
    meta["aggregate_schema"] = row["summary_schema"]
    return aggregate, row, meta


def test_exact_eight_contract_and_legacy_six_default_are_distinct():
    assert cap._EIGHT_UNIVERSES == EIGHT
    old, _ = _aggregate("R195")
    old = {key: old[key] for key in cap._AGGREGATE_FIELDS}
    assert cap._project_aggregate(old) == cap._project_aggregate(old, eight_universe=False)
    with pytest.raises(cap.Cap90QcSubmissionError, match="nested aggregate"):
        cap._project_aggregate(old, eight_universe=True)
    eight = _historical_eight_base()
    selected = cap._project_aggregate(eight, eight_universe=True)
    assert [row[0] for row in selected["sleeve_diagnostics"]["rows"]] == list(EIGHT)
    assert sum(selected["fallback_counts"].values()) == 8 * 261
    with pytest.raises(cap.Cap90QcSubmissionError, match="nested aggregate"):
        cap._project_aggregate(eight)


@pytest.mark.parametrize("defect", (
    "seventh", "ninth", "order", "old_schema", "fallback_low", "fallback_high",
    "unavailable_missing", "unavailable_ninth", "truthy_opt_in",
))
def test_eight_sleeve_shape_census_and_contract_refuse(defect):
    aggregate = _historical_eight_base()
    if defect == "seventh":
        aggregate["sleeve_diagnostics"]["rows"].pop()
    elif defect == "ninth":
        aggregate["sleeve_diagnostics"]["rows"].append(copy.deepcopy(aggregate["sleeve_diagnostics"]["rows"][-1]))
    elif defect == "order":
        rows = aggregate["sleeve_diagnostics"]["rows"]
        rows[-1], rows[-2] = rows[-2], rows[-1]
    elif defect == "old_schema":
        aggregate["sleeve_diagnostics"]["schema"] = "arv2-six-universe-order-sleeve-summary-table-v1"
    elif defect == "fallback_low":
        aggregate["fallback_counts"]["SIX_ETF_BASKET"] = 8 * 261 - 1
    elif defect == "fallback_high":
        aggregate["fallback_counts"]["SIX_ETF_BASKET"] = 9 * 261
    elif defect == "unavailable_missing":
        del aggregate["constituent_collection_unavailable_universe_counts"]["XLF"]
    elif defect == "unavailable_ninth":
        aggregate["constituent_collection_unavailable_universe_counts"]["KIE"] = 0
    else:
        with pytest.raises(cap.Cap90QcSubmissionError, match="universe contract"):
            cap._project_aggregate(aggregate, eight_universe=8)
        return
    with pytest.raises(cap.Cap90QcSubmissionError):
        cap._project_aggregate(aggregate, eight_universe=True)


def test_eight_aggregate_uses_only_its_16384_byte_bound():
    overhead = len(common._canonical({"p": ""}))
    exact = common._canonical({"p": "x" * (16_384 - overhead)}).decode("ascii")
    assert len(exact.encode("ascii")) == 16_384
    assert relaxed._statistic(exact, eight_aggregate=True)["p"]
    with pytest.raises(relaxed.RelaxedQcSubmissionError, match="bounded canonical"):
        relaxed._statistic(exact)
    with pytest.raises(relaxed.RelaxedQcSubmissionError, match="bounded canonical"):
        relaxed._statistic(exact[:-2] + "x" + exact[-2:], eight_aggregate=True)
    with pytest.raises(relaxed.RelaxedQcSubmissionError, match="universe contract"):
        relaxed._statistic("{}", eight_aggregate=8)
    # The six-family default remains the original 8192-byte inclusive bound.
    old = common._canonical({"p": "x" * (8192 - overhead)}).decode("ascii")
    assert relaxed._statistic(old) == relaxed._statistic(old, eight_aggregate=False)


def test_eight_relaxed_translation_is_pure_and_keeps_original_named_statuses():
    aggregate, _, _ = _recent_eight_order()
    before = copy.deepcopy(aggregate)
    selected = relaxed._bounded_order_base(aggregate, eight_universe=True)
    assert aggregate == before
    assert len(selected["sleeve_diagnostics"]["rows"]) == 8
    assert selected["fallback_counts"] == {"PARTIAL_STOCK_EXPOSURE_WITH_ETF_FALLBACK": 8 * 61}
    assert selected["sleeve_diagnostics"]["rows"][-1][0] == "XLF"
    with pytest.raises((relaxed.RelaxedQcSubmissionError, cap.Cap90QcSubmissionError)):
        relaxed._bounded_order_base(aggregate)


def test_eight_parser_requires_exact_family_and_keeps_raw_digest(monkeypatch):
    aggregate, row, meta = _recent_eight_order()
    raw = common._canonical(aggregate).decode("ascii")
    meta["aggregate_sha256"] = hashlib.sha256(raw.encode("ascii")).hexdigest()
    meta_raw = common._canonical(meta).decode("ascii")
    statistics = {"ARV2_EIGHT_GATE_ORDER_META": meta_raw,
                  "ARV2_EIGHT_GATE_ORDER_AGGREGATES": raw}
    monkeypatch.setattr(relaxed, "_candidate", lambda plan: row)
    monkeypatch.setattr(relaxed, "_plan_manifest", lambda plan: {
        "package_sha256": "c" * 64, "activation_manifest_sha256": "d" * 64,
    })
    plan = relaxed.RelaxedQcPlan("R999", "a" * 32, Path("/tmp/unused-eight-offline"),
                                 family="eight_universe")
    parsed = relaxed._parse_order_common(plan, statistics, eight_universe=True)
    assert parsed["run_valid"] is True
    assert parsed["meta"]["aggregate_sha256"] == hashlib.sha256(raw.encode("ascii")).hexdigest()
    assert [sleeve[0] for sleeve in parsed["aggregates"]["sleeve_diagnostics"]["rows"]] == list(EIGHT)
    with pytest.raises((relaxed.RelaxedQcSubmissionError, cap.Cap90QcSubmissionError)):
        relaxed._parse_order_common(plan, statistics)
    six = relaxed.RelaxedQcPlan("R999", "a" * 32, Path("/tmp/unused-six-offline"),
                                family="qcom_score_floor1")
    with pytest.raises(relaxed.RelaxedQcSubmissionError, match="not authorized"):
        relaxed._parse_order_common(six, statistics, eight_universe=True)
    bad = copy.deepcopy(meta)
    bad["aggregate_sha256"] = "0" * 64
    statistics["ARV2_EIGHT_GATE_ORDER_META"] = common._canonical(bad).decode("ascii")
    with pytest.raises(relaxed.RelaxedQcSubmissionError, match="digest"):
        relaxed._parse_order_common(plan, statistics, eight_universe=True)
