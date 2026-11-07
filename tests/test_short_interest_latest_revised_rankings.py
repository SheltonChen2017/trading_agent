"""Fabricated external transport files test arithmetic, never market edge."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

import pytest

from data.exchange_calendar import trading_sessions
from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf.latest_revised_protocol import PROTOCOL_SHA256
from research.short_interest_etf.latest_revised_rankings import (
    LatestRevisedRankingError,
    rank_latest_revised_bundle,
)
from research.short_interest_etf.latest_revised_source import (
    load_latest_revised_bundle,
)


CURRENT = "2024-01-31"
FINAL = "2024-02-15"


def _security(index: int) -> str:
    return f"figi:ZZG{index:09d}"


@lru_cache(maxsize=1)
def _sessions() -> tuple[str, ...]:
    return tuple(day.isoformat() for day in trading_sessions(date(2022, 12, 1), date(2024, 2, 28)))


def _contents(count: int = 20) -> dict:
    calendar = [
        {"settlement_date": "2024-01-12", "publication_date": "2024-01-24"},
        {"settlement_date": CURRENT, "publication_date": "2024-02-12"},
        {"settlement_date": FINAL, "publication_date": "2024-02-27"},
    ]
    observations, references, bars = [], [], []
    for index in range(count):
        security = _security(index)
        ticker = f"FAB{index:03d}"
        for release_index, release in enumerate(calendar):
            observations.append({
                "ticker": ticker, "settlement_date": release["settlement_date"],
                "short_interest": 100 + release_index * index,
                "avg_daily_volume": 100000, "days_to_cover": "0",
            })
        for session in ("2024-01-12", "2024-01-24", CURRENT, "2024-02-12", FINAL, "2024-02-27"):
            references.append({
                "security_id": security, "share_class_figi": security[5:], "ticker": ticker,
                "effective_from": "2020-01-01", "effective_to": None,
                "observation_session": session, "available_date": session,
                "shares_outstanding": 10000, "sector": "FABRICATED_TECH",
                "taxonomy_id": "FABRICATED_TEST_V1", "country": "US",
                "security_type": "COMMON_STOCK", "market_cap": "300000000",
            })
        bars.extend({
            "security_id": security, "session": session, "open": "100",
            "close": "100", "volume": 100000, "prices_adjusted": False,
        } for session in _sessions())
    return {"calendar": calendar, "observations": observations,
            "references": references, "bars": bars, "events": []}


def _write_inputs(path: Path, contents: dict) -> Path:
    """Produce hash-bound arbitrary files; there is no approved fixed-ID runner."""
    path.mkdir(parents=True, exist_ok=True)
    descriptors = {}
    for kind in ("calendar", "references", "bars", "events"):
        blob = canonical_json({"schema": f"si-exploratory-{kind}-v1", "rows": contents[kind]}).encode()
        filename = f"fabricated-{kind}.json"
        (path / filename).write_bytes(blob)
        descriptors[kind] = {"path": filename, "sha256": hash_bytes(blob)}
    blob = canonical_json({"status": "OK", "results": contents["observations"]}).encode()
    (path / "fabricated-si.json").write_bytes(blob)
    manifest = {
        "schema": "si-latest-revised-files-v1", "source_id": "massive-short-interest",
        "retrieved_at": "2026-10-07T12:00:00Z", "universe_scope": "supplied_records_only",
        "short_interest_pages": [{"path": "fabricated-si.json", "sha256": hash_bytes(blob),
                                  "request_url": "https://api.massive.com/stocks/v1/short-interest"}],
        **descriptors,
    }
    manifest_path = path / "fabricated-manifest.json"
    manifest_path.write_text(canonical_json(manifest), encoding="utf-8")
    return manifest_path


def _rank(path: Path, contents: dict | None = None):
    return rank_latest_revised_bundle(load_latest_revised_bundle(
        _write_inputs(path, _contents() if contents is None else contents)
    ))


def _release(payload: dict, settlement: str = CURRENT) -> dict:
    return next(row for row in payload["releases"] if row["settlement_date"] == settlement)


def _lookbacks(release: dict) -> dict[int, dict]:
    return {row["lookback_sessions"]: row for row in release["lookbacks"]}


def _fraction(value: dict) -> Fraction:
    return Fraction(value["numerator"], value["denominator"])


def test_file_fed_exact_normalization_rank_tails_and_closed_authority(tmp_path):
    receipt = _rank(tmp_path)
    payload = receipt.to_payload()
    release = _release(payload)
    assert payload["protocol_sha256"] == PROTOCOL_SHA256
    assert payload["source_bundle_sha256"] == receipt.bundle.sha256
    assert payload["rankings_sha256"] == hash_payload({
        key: value for key, value in payload.items() if key != "rankings_sha256"
    })
    assert payload["selected_lookback"] is None
    assert payload["authority"]["latest_revised"] is True
    assert all(value is False for key, value in payload["authority"].items() if key != "latest_revised")
    assert payload["actual_outcome_access_authority"] is False
    assert payload["look_accounting"] == "runner_managed"
    assert "empirical_looks_consumed" not in payload
    assert release["entry_session"] == "2024-02-13"
    assert release["last_completed_session"] == "2024-02-12"
    assert release["status"] == "ready"
    structural = release["structural_rows"]
    assert len(structural) == 20
    for index, row in enumerate(structural):
        assert _fraction(row["raw_s1_delta"]) == Fraction(index, 10000)
        assert _fraction(row["winsor_lower"]) == Fraction(19, 1000000)
        assert _fraction(row["winsor_upper"]) == Fraction(1881, 1000000)
        assert _fraction(row["sector_median"]) == Fraction(19, 20000)
        assert _fraction(row["sector_mad"]) == Fraction(1, 2000)
        assert _fraction(row["scaled_mad"]) == Fraction(7413, 10000000)
    for lookback, ranking in _lookbacks(release).items():
        assert ranking["ranked_security_ids"] == sorted(_security(i) for i in range(20))
        assert ranking["low_tail_security_ids"] == [_security(0), _security(1)]
        assert ranking["high_tail_security_ids"] == [_security(18), _security(19)]
        for index, row in enumerate(ranking["rows"]):
            assert _fraction(row["pressure_percentile"]) == Fraction(2 * index + 1, 40)
            assert _fraction(row["covering_percentile"]) == 1 - _fraction(row["pressure_percentile"])
        assert all(row["complete_session_count"] == lookback for row in ranking["eligibility_rows"])
        assert all(_fraction(row["median_dollar_volume"]) == 10000000 for row in ranking["eligibility_rows"])
    assert payload["releases"][0]["status"] == "warmup"
    assert payload["releases"][-1]["status"] == "final_no_successor"
    assert payload["releases"][-1]["next_entry_session"] is None


def test_receipt_is_detached_immutable_and_revalidates_both_bindings(tmp_path):
    receipt = _rank(tmp_path)
    original = receipt.sha256
    detached = receipt.to_payload()
    detached["releases"][1]["lookbacks"][0]["rows"].clear()
    assert receipt.sha256 == original
    with pytest.raises(FrozenInstanceError):
        receipt._payload_json = "{}"
    object.__setattr__(receipt, "_payload_json", "{}")
    with pytest.raises(LatestRevisedRankingError, match="deterministic source"):
        receipt.to_payload()
    receipt = _rank(tmp_path)
    object.__setattr__(receipt, "_source_bundle_sha256", "0" * 64)
    with pytest.raises(LatestRevisedRankingError, match="binding changed"):
        receipt.to_payload()
    receipt = _rank(tmp_path)
    object.__setattr__(receipt, "_protocol_sha256", "0" * 64)
    with pytest.raises(LatestRevisedRankingError, match="binding changed"):
        receipt.to_payload()
    with pytest.raises(LatestRevisedRankingError, match="exact"):
        rank_latest_revised_bundle({})


def test_missing_immediate_predecessor_never_leapfrogs_older_same_security(tmp_path):
    contents = _contents(21)
    contents["observations"] = [row for row in contents["observations"]
                                if (row["ticker"], row["settlement_date"]) != ("FAB020", CURRENT)]
    release = _release(_rank(tmp_path, contents).to_payload(), FINAL)
    row = next(row for row in release["structural_rows"] if row["ticker"] == "FAB020")
    assert row["raw_s1_delta"] is None
    assert row["prior_short_interest"] is None
    assert row["refusal_reasons"] == ["missing_same_security_immediate_previous_short_interest"]
    assert _security(20) not in release["common_security_ids"]
    assert len(release["common_security_ids"]) == 20


def test_structural_population_not_recomputed_after_market_cap_filter(tmp_path):
    baseline = _release(_rank(tmp_path / "base").to_payload())
    contents = _contents()
    for row in contents["references"]:
        if row["security_id"] == _security(19) and row["observation_session"] == "2024-02-12":
            row["market_cap"] = "299999999.99"
    filtered = _release(_rank(tmp_path / "filtered", contents).to_payload())
    assert baseline["structural_rows"] == filtered["structural_rows"]
    assert len(filtered["common_security_ids"]) == 19
    for ranking in filtered["lookbacks"]:
        assert _security(19) not in ranking["ranked_security_ids"]
        refusal = next(row for row in ranking["refusals"] if row["security_id"] == _security(19))
        assert "below_market_cap_floor" in refusal["reasons"]


@pytest.mark.parametrize("count,zero_mad,reason", [
    (19, False, "insufficient_sector_peers"),
    (20, True, "zero_sector_mad"),
])
def test_whole_structural_sector_refused_without_peer_or_mad_substitute(tmp_path, count, zero_mad, reason):
    contents = _contents(count)
    if zero_mad:
        for row in contents["observations"]:
            row["short_interest"] = 100
    release = _release(_rank(tmp_path, contents).to_payload())
    assert all(row["score"] is None for row in release["structural_rows"])
    assert all(row["refusal_reasons"] == [reason] for row in release["structural_rows"])
    assert all(ranking["ranked_security_ids"] == [] for ranking in release["lookbacks"])
    assert release["common_security_ids"] == []


def test_nine_eligible_names_have_order_statistics_but_no_tail(tmp_path):
    contents = _contents()
    for row in contents["references"]:
        if int(row["security_id"][-4:]) >= 9 and row["observation_session"] == "2024-02-12":
            row["market_cap"] = "299999999"
    release = _release(_rank(tmp_path, contents).to_payload())
    for ranking in release["lookbacks"]:
        assert len(ranking["rows"]) == 9
        assert ranking["original_high_tail_security_ids"] == []
        assert ranking["original_low_tail_security_ids"] == []
        assert all(not row["high_tail"] and not row["low_tail"] for row in ranking["rows"])
        assert "insufficient_ranked_population_for_tails" in ranking["refusal_reasons"]


def test_inclusive_boundary_keeps_all_indivisible_ties(tmp_path):
    contents = _contents()
    for row in contents["observations"]:
        index = int(row["ticker"][-3:])
        if row["settlement_date"] == CURRENT:
            row["short_interest"] = 100 + (0 if index < 4 else 16 if index >= 16 else index)
    release = _release(_rank(tmp_path, contents).to_payload())
    for ranking in release["lookbacks"]:
        assert ranking["low_tail_security_ids"] == [_security(i) for i in range(4)]
        assert ranking["high_tail_security_ids"] == [_security(i) for i in range(16, 20)]
        assert all(_fraction(row["pressure_percentile"]) == Fraction(1, 10) for row in ranking["rows"][:4])
        assert all(_fraction(row["pressure_percentile"]) == Fraction(9, 10) for row in ranking["rows"][-4:])


@pytest.mark.parametrize("missing_indices", [(19,), (18, 19)])
def test_common_intersection_preserves_original_ranks_and_reports_tail_loss(tmp_path, missing_indices):
    contents = _contents()
    past = [session for session in _sessions() if session < "2024-02-13"]
    missing = past[-30]
    contents["bars"] = [row for row in contents["bars"]
                        if not (row["security_id"] in {_security(i) for i in missing_indices} and row["session"] == missing)]
    release = _release(_rank(tmp_path, contents).to_payload())
    rankings = _lookbacks(release)
    short = rankings[20]
    assert len(short["rows"]) == 20
    assert len(short["common_security_ids"]) == 20 - len(missing_indices)
    assert short["original_high_tail_security_ids"] == [_security(18), _security(19)]
    assert short["high_tail_security_ids"] == ([] if 18 in missing_indices else [_security(18)])
    assert short["lost_high_tail_security_ids"] == [_security(i) for i in missing_indices]
    assert "original_high_tail_lost_at_common_intersection" in short["refusal_reasons"]
    original = next(row for row in short["rows"] if row["security_id"] == _security(17))
    assert original["high_tail"] is False
    assert _fraction(original["pressure_percentile"]) == Fraction(35, 40)
    assert all(_security(i) not in rankings[n]["ranked_security_ids"] for n in (60, 120, 252) for i in missing_indices)


def test_future_bars_never_replace_missing_completed_session(tmp_path):
    contents = _contents()
    contents["bars"] = [row for row in contents["bars"]
                        if not (row["security_id"] == _security(19) and row["session"] == "2024-02-12")]
    for row in contents["bars"]:
        if row["security_id"] == _security(19) and row["session"] >= "2024-02-13":
            row["close"], row["volume"] = "999999", 99999999
    release = _release(_rank(tmp_path, contents).to_payload())
    for ranking in release["lookbacks"]:
        evidence = next(row for row in ranking["eligibility_rows"] if row["security_id"] == _security(19))
        assert evidence["missing_sessions"] == ["2024-02-12"]
        assert evidence["complete_session_count"] == ranking["lookback_sessions"] - 1
        assert evidence["median_dollar_volume"] is None
        assert _security(19) not in ranking["ranked_security_ids"]


def test_late_and_future_reference_cannot_backdate_current_denominator_or_cap(tmp_path):
    contents = _contents(21)
    for row in contents["references"]:
        if row["security_id"] == _security(20):
            if row["observation_session"] in {"2024-01-12", "2024-01-24", CURRENT}:
                row["available_date"] = "2024-02-13"
            if row["observation_session"] == "2024-02-12":
                row["shares_outstanding"] = 1
                row["available_date"] = "2024-02-13"
    release = _release(_rank(tmp_path, contents).to_payload())
    structural = next(row for row in release["structural_rows"] if row["ticker"] == "FAB020")
    assert structural["raw_s1_delta"] is None
    assert "late_dated_reference" in structural["refusal_reasons"]
    assert structural["current_shares_outstanding"] is None
    assert len(release["common_security_ids"]) == 20


def test_empty_calendar_release_preserved_and_does_not_leapfrog(tmp_path):
    contents = _contents()
    contents["observations"] = [row for row in contents["observations"] if row["settlement_date"] != CURRENT]
    payload = _rank(tmp_path, contents).to_payload()
    assert len(payload["releases"]) == 3
    empty = _release(payload)
    assert empty["status"] == "empty"
    assert empty["structural_rows"] == []
    assert len(empty["lookbacks"]) == 4
    final = _release(payload, FINAL)
    assert all("missing_same_security_immediate_previous_short_interest" in row["refusal_reasons"]
               for row in final["structural_rows"])


def test_each_denominator_is_dated_to_its_own_settlement_and_future_reference_ignored(tmp_path):
    contents = _contents()
    for row in contents["references"]:
        if row["security_id"] == _security(0) and row["observation_session"] == CURRENT:
            row["shares_outstanding"] = 20000
        if row["security_id"] == _security(1) and row["observation_session"] == "2024-02-12":
            row["shares_outstanding"] = 1
    release = _release(_rank(tmp_path, contents).to_payload())
    rows = {row["security_id"]: row for row in release["structural_rows"]}
    assert rows[_security(0)]["current_shares_outstanding"] == 20000
    assert rows[_security(0)]["prior_shares_outstanding"] == 10000
    assert _fraction(rows[_security(0)]["raw_s1_delta"]) == Fraction(100, 20000) - Fraction(100, 10000)
    assert rows[_security(1)]["current_shares_outstanding"] == 10000
    assert _fraction(rows[_security(1)]["raw_s1_delta"]) == Fraction(1, 10000)


@pytest.mark.parametrize("same_share_class", [True, False])
def test_ticker_rename_uses_same_share_class_and_ticker_reuse_cannot_join_prior(tmp_path, same_share_class):
    contents = _contents(21)
    for row in contents["references"]:
        if row["security_id"] != _security(20):
            continue
        if row["observation_session"] <= "2024-01-20":
            row["effective_to"] = "2024-01-20"
            if not same_share_class:
                row["security_id"] = _security(999)
                row["share_class_figi"] = _security(999)[5:]
        else:
            row["effective_from"] = "2024-01-21"
            if same_share_class:
                row["ticker"] = "REN020"
    if same_share_class:
        for row in contents["observations"]:
            if row["ticker"] == "FAB020" and row["settlement_date"] >= CURRENT:
                row["ticker"] = "REN020"
    release = _release(_rank(tmp_path, contents).to_payload())
    target = next(row for row in release["structural_rows"] if row["security_id"] == _security(20))
    if same_share_class:
        assert _fraction(target["raw_s1_delta"]) == Fraction(20, 10000)
        assert target["prior_short_interest"] == 100
        assert _security(20) in release["common_security_ids"]
    else:
        assert target["raw_s1_delta"] is None
        assert target["prior_short_interest"] is None
        assert "missing_same_security_immediate_previous_short_interest" in target["refusal_reasons"]
        assert _security(20) not in release["common_security_ids"]


def test_late_cap_refuses_even_when_structural_denominators_are_available(tmp_path):
    contents = _contents()
    for row in contents["references"]:
        if row["security_id"] == _security(19) and row["observation_session"] == "2024-02-12":
            row["available_date"] = "2024-02-13"
    release = _release(_rank(tmp_path, contents).to_payload())
    assert release["structural_rows"][-1]["score"] is not None
    for ranking in release["lookbacks"]:
        evidence = next(row for row in ranking["eligibility_rows"] if row["security_id"] == _security(19))
        assert evidence["refusal_reasons"] == ["market_cap_late"]
        assert evidence["market_cap"] is None
        assert _security(19) not in ranking["ranked_security_ids"]


@pytest.mark.parametrize("group_field", ["sector", "taxonomy_id"])
def test_peer_floor_never_pools_small_sectors_or_different_taxonomies(tmp_path, group_field):
    contents = _contents()
    for row in contents["references"]:
        if int(row["security_id"][-4:]) >= 10:
            row[group_field] = "FABRICATED_OTHER"
    release = _release(_rank(tmp_path, contents).to_payload())
    reason = "mixed_taxonomy_lineage" if group_field == "taxonomy_id" else "insufficient_sector_peers"
    assert all(row["sector_peer_count"] == (0 if group_field == "taxonomy_id" else 10)
               for row in release["structural_rows"])
    assert all(row["refusal_reasons"] == [reason] for row in release["structural_rows"])
    assert release["common_security_ids"] == []


def test_exact_liquidity_floor_refusal_does_not_change_structural_normalization(tmp_path):
    contents = _contents()
    for row in contents["bars"]:
        row["volume"] = 99999
    release = _release(_rank(tmp_path, contents).to_payload())
    assert all(row["score"] is not None for row in release["structural_rows"])
    for ranking in release["lookbacks"]:
        assert ranking["ranked_security_ids"] == []
        assert all(_fraction(row["median_dollar_volume"]) == 9999900 for row in ranking["eligibility_rows"])
        assert all(row["refusal_reasons"] == ["below_median_dollar_volume_floor"] for row in ranking["eligibility_rows"])


@pytest.mark.parametrize("refuse_second_taxonomy_cap", [False, True])
def test_mixed_taxonomy_lineage_refuses_whole_structural_cohort_before_investability(tmp_path, refuse_second_taxonomy_cap):
    contents = _contents(40)
    for row in contents["references"]:
        if int(row["security_id"][-4:]) >= 20:
            row["taxonomy_id"] = "FABRICATED_OTHER_V1"
            if refuse_second_taxonomy_cap and row["observation_session"] == "2024-02-12":
                row["market_cap"] = "299999999"
    release = _release(_rank(tmp_path, contents).to_payload())
    assert len(release["structural_rows"]) == 40
    assert all(row["raw_s1_delta"] is not None for row in release["structural_rows"])
    assert all(row["score"] is None for row in release["structural_rows"])
    assert all(row["refusal_reasons"] == ["mixed_taxonomy_lineage"] for row in release["structural_rows"])
    assert all(row["winsor_lower"] is None and row["winsor_upper"] is None for row in release["structural_rows"])
    assert all(row["sector_median"] is None and row["sector_mad"] is None for row in release["structural_rows"])
    assert "mixed_taxonomy_lineage" in release["refusal_reasons"]
    assert release["common_security_ids"] == []
    for ranking in release["lookbacks"]:
        assert ranking["ranked_security_ids"] == []
        assert ranking["original_high_tail_security_ids"] == []
        assert ranking["original_low_tail_security_ids"] == []
        assert len(ranking["refusals"]) == 40
        assert all("mixed_taxonomy_lineage" in row["reasons"] for row in ranking["refusals"])
        assert len(ranking["eligible_security_ids"]) == (20 if refuse_second_taxonomy_cap else 40)


@pytest.mark.parametrize("role,missing_indices", [("high", (18, 19)), ("low", (0, 1))])
def test_common_comparison_refuses_entire_missing_original_tail_without_replacement(tmp_path, role, missing_indices):
    contents = _contents()
    missing_session = [session for session in _sessions() if session < "2024-02-13"][-30]
    contents["bars"] = [row for row in contents["bars"]
                        if not (row["security_id"] in {_security(i) for i in missing_indices}
                                and row["session"] == missing_session)]
    release = _release(_rank(tmp_path, contents).to_payload())
    assert len(release["common_security_ids"]) == 18
    assert release["status"] == "refused"
    assert f"missing_common_{role}_pressure_tail" in release["refusal_reasons"]
    short = _lookbacks(release)[20]
    assert len(short["rows"]) == 20
    assert short[f"original_{role}_tail_security_ids"] == [_security(i) for i in missing_indices]
    assert short[f"{role}_tail_security_ids"] == []
    assert short[f"lost_{role}_tail_security_ids"] == [_security(i) for i in missing_indices]
    assert all(row[f"{role}_tail"] is True and row["in_common"] is False
               for row in short["rows"] if row["security_id"] in {_security(i) for i in missing_indices})


def test_common_comparison_refuses_nine_names_even_when_all_full_ranks_and_both_tails_suffice(tmp_path):
    contents = _contents()
    recent = {session for session in _sessions() if session < "2024-02-13"}
    recent = set(sorted(recent)[-20:])
    for row in contents["bars"]:
        if row["session"] >= "2024-02-13":
            continue
        index = int(row["security_id"][-4:])
        if 7 <= index <= 12:
            row["volume"] = 100000 if row["session"] in recent else 99999
        if 13 <= index <= 17:
            row["volume"] = 99999 if row["session"] in recent else 100000
    release = _release(_rank(tmp_path, contents).to_payload())
    assert len(release["common_security_ids"]) == 9
    assert [len(ranking["ranked_security_ids"]) for ranking in release["lookbacks"]] == [15, 14, 14, 14]
    assert all(ranking["high_tail_security_ids"] and ranking["low_tail_security_ids"]
               for ranking in release["lookbacks"])
    assert release["status"] == "refused"
    assert "underfilled_common_intersection" in release["refusal_reasons"]
    assert "missing_common_high_pressure_tail" not in release["refusal_reasons"]
    assert "missing_common_low_pressure_tail" not in release["refusal_reasons"]


@pytest.mark.parametrize("role,missing_index", [("high", 19), ("low", 1)])
def test_common_comparison_keeps_partial_original_tail_attrition_ready(tmp_path, role, missing_index):
    contents = _contents()
    missing_session = [session for session in _sessions() if session < "2024-02-13"][-30]
    contents["bars"] = [row for row in contents["bars"]
                        if (row["security_id"], row["session"]) != (_security(missing_index), missing_session)]
    release = _release(_rank(tmp_path, contents).to_payload())
    assert release["status"] == "ready"
    assert len(release["common_security_ids"]) == 19
    assert all(ranking["high_tail_security_ids"] and ranking["low_tail_security_ids"]
               for ranking in release["lookbacks"])
    short = _lookbacks(release)[20]
    assert len(short["rows"]) == 20
    assert len(short[f"original_{role}_tail_security_ids"]) == 2
    assert len(short[f"{role}_tail_security_ids"]) == 1
    assert short[f"lost_{role}_tail_security_ids"] == [_security(missing_index)]
    assert f"original_{role}_tail_lost_at_common_intersection" in short["refusal_reasons"]
    assert f"missing_common_{role}_pressure_tail" not in release["refusal_reasons"]
