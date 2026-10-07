"""Fabricated external files verify plumbing, never an empirical source/look."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from data.exchange_calendar import resolve_nth_session_after, session_open_instant, trading_sessions
from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf.contracts import format_utc_timestamp
from research.short_interest_etf.latest_revised_source import (
    BUNDLE_SCHEMA,
    FILES_SCHEMA,
    LatestRevisedBundle,
    LatestRevisedSourceError,
    load_latest_revised_bundle,
)
import research.short_interest_etf.latest_revised_source as source_module


def fixture_documents(*, security_count: int = 20) -> dict[str, dict]:
    """Complete, deliberately invented file set for vertical-slice tests only."""
    releases = [
        {"settlement_date": "2024-01-12", "publication_date": "2024-01-26"},
        {"settlement_date": "2024-01-31", "publication_date": "2024-02-12"},
        {"settlement_date": "2024-02-15", "publication_date": "2024-02-26"},
    ]
    observations, references, bars = [], [], []
    sessions = trading_sessions(date(2022, 11, 1), date(2024, 2, 27))
    for index in range(security_count):
        figi = f"BBG{index:09d}"
        security_id, ticker = "figi:" + figi, f"TOY{index:02d}"
        for release_index, release in enumerate(releases):
            observations.append({
                "ticker": ticker, "settlement_date": release["settlement_date"],
                "short_interest": 100_000 + index * 100 + release_index * (index + 1) * 1_000,
                "avg_daily_volume": 100_000, "days_to_cover": "1",
            })
        for session in ("2024-01-12", "2024-01-26", "2024-01-31", "2024-02-12", "2024-02-15", "2024-02-26"):
            references.append({
                "security_id": security_id, "share_class_figi": figi, "ticker": ticker,
                "effective_from": "2022-01-01", "effective_to": None,
                "observation_session": session, "available_date": session,
                "shares_outstanding": 10_000_000, "sector": "TOY_SECTOR",
                "taxonomy_id": "toy-taxonomy-v1", "country": "US",
                "security_type": "COMMON_STOCK", "market_cap": "1000000000",
            })
        for session in sessions:
            bars.append({
                "security_id": security_id, "session": session.isoformat(),
                "open": "110" if session.isoformat() == "2024-02-27" else "100",
                "close": "100", "volume": 100_000, "prices_adjusted": False,
            })
    return {
        "si-page-1.json": {"status": "OK", "request_id": "toy-page-1", "results": observations},
        "calendar.json": {"schema": "si-exploratory-calendar-v1", "rows": releases},
        "references.json": {"schema": "si-exploratory-references-v1", "rows": references},
        "bars.json": {"schema": "si-exploratory-bars-v1", "rows": bars},
        "events.json": {"schema": "si-exploratory-events-v1", "rows": []},
    }


def write_fixture(directory: Path, documents: dict[str, dict] | None = None) -> Path:
    """Write only a pytest temporary directory; production imports no tests."""
    directory.mkdir(parents=True, exist_ok=True)
    documents = fixture_documents() if documents is None else documents
    descriptors = {}
    for name, document in documents.items():
        blob = canonical_json(document).encode("utf-8")
        (directory / name).write_bytes(blob)
        descriptors[name] = {"path": name, "sha256": hash_bytes(blob)}
    pages = sorted(name for name in documents if name.startswith("si-page-"))
    manifest = {
        "schema": FILES_SCHEMA, "source_id": "massive-short-interest",
        "retrieved_at": "2026-10-07T12:00:00Z", "universe_scope": "supplied_records_only",
        "short_interest_pages": [{**descriptors[name], "request_url": f"https://example.invalid/{name}"} for name in pages],
        **{kind: descriptors[kind + ".json"] for kind in ("calendar", "references", "bars", "events")},
    }
    path = directory / "manifest.json"
    path.write_bytes(canonical_json(manifest).encode("utf-8"))
    return path


def _rewrite_manifest(path: Path, mutate) -> None:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    mutate(manifest)
    path.write_bytes(canonical_json(manifest).encode("utf-8"))


def test_external_files_form_detached_latest_revised_bundle(tmp_path):
    bundle = load_latest_revised_bundle(write_fixture(tmp_path))
    payload = bundle.to_payload()
    assert payload["schema"] == BUNDLE_SCHEMA
    assert len(payload["observations"]) == 60
    assert [row["entry_session"] for row in payload["releases"]] == ["2024-01-29", "2024-02-13", "2024-02-27"]
    assert payload["releases"][0]["entry_at"] == "2024-01-29T14:30:00Z"
    assert payload["authority"]["latest_revised"] is True
    assert all(value is False for key, value in payload["authority"].items() if key != "latest_revised")
    assert "synthetic_only" not in payload["authority"]
    assert payload["provenance"]["universe_scope"] == "supplied_records_only"
    assert payload["bundle_sha256"] == hash_payload({key: value for key, value in payload.items() if key != "bundle_sha256"})
    payload["observations"].clear()
    assert len(bundle.to_payload()["observations"]) == 60


def test_all_duplicate_ticker_settlement_rows_are_refused(tmp_path):
    documents = fixture_documents(security_count=1)
    row = documents["si-page-1.json"]["results"][0].copy()
    documents["si-page-1.json"]["results"].append(row)
    payload = load_latest_revised_bundle(write_fixture(tmp_path, documents)).to_payload()
    assert len(payload["observations"]) == 2
    assert len(payload["refusals"]) == 2
    assert {row["reason"] for row in payload["refusals"]} == {"duplicate_ticker_settlement"}


@pytest.mark.parametrize("changes,reason", [
    ({"short_sale_volume": 42}, "daily_short_volume_forbidden"),
    ({"short_interest": True}, "exact integer"),
    ({"made_up_revision_time": "2024-01-26T12:00:00Z"}, "unknown fields"),
    ({"short_interest": -1}, "exact integer"),
])
def test_malformed_si_rows_are_visible_refusals(tmp_path, changes, reason):
    documents = fixture_documents(security_count=1)
    documents["si-page-1.json"]["results"][0].update(changes)
    payload = load_latest_revised_bundle(write_fixture(tmp_path, documents)).to_payload()
    assert len(payload["observations"]) == 2
    assert len(payload["refusals"]) == 1
    assert reason in payload["refusals"][0]["reason"]


def test_missing_dtc_and_adv_remain_missing_without_dropping_short_interest(tmp_path):
    documents = fixture_documents(security_count=1)
    row = documents["si-page-1.json"]["results"][0]
    row.pop("avg_daily_volume")
    row["days_to_cover"] = None
    payload = load_latest_revised_bundle(write_fixture(tmp_path, documents)).to_payload()
    assert len(payload["observations"]) == 3 and payload["refusals"] == []
    assert payload["observations"][0]["avg_daily_volume"] is None
    assert payload["observations"][0]["days_to_cover"] is None


def test_all_pages_are_verified_and_complete_chain_is_required(tmp_path):
    documents = fixture_documents(security_count=1)
    documents["si-page-2.json"] = {"status": "OK", "results": []}
    documents["si-page-1.json"]["next_url"] = "https://example.invalid/si-page-2.json"
    path = write_fixture(tmp_path, documents)
    assert len(load_latest_revised_bundle(path).to_payload()["observations"]) == 3
    _rewrite_manifest(path, lambda manifest: manifest["short_interest_pages"].pop())
    with pytest.raises(LatestRevisedSourceError, match="chain incomplete"):
        load_latest_revised_bundle(path)


def test_hash_is_verified_before_json_parse(tmp_path):
    path = write_fixture(tmp_path, fixture_documents(security_count=1))
    (tmp_path / "si-page-1.json").write_text("{not json}", encoding="utf-8")
    with pytest.raises(LatestRevisedSourceError, match="SHA-256 mismatch"):
        load_latest_revised_bundle(path)


@pytest.mark.parametrize("filename", ["../references.json", "/references.json", "nested/references.json", ".", ".."])
def test_manifest_path_traversal_is_refused(tmp_path, filename):
    path = write_fixture(tmp_path, fixture_documents(security_count=1))
    _rewrite_manifest(path, lambda manifest: manifest["references"].update(path=filename))
    with pytest.raises(LatestRevisedSourceError, match="safe relative basename"):
        load_latest_revised_bundle(path)


@pytest.mark.parametrize("text", ['{"schema":1,"schema":2}', '{"x":NaN}', '{"x":Infinity}'])
def test_duplicate_keys_and_nonfinite_json_are_refused(tmp_path, text):
    path = tmp_path / "manifest.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(LatestRevisedSourceError, match="duplicate JSON key|nonfinite JSON"):
        load_latest_revised_bundle(path)


def test_adjusted_bars_are_refused(tmp_path):
    documents = fixture_documents(security_count=1)
    documents["bars.json"]["rows"][0]["prices_adjusted"] = True
    with pytest.raises(LatestRevisedSourceError, match="adjusted bars"):
        load_latest_revised_bundle(write_fixture(tmp_path, documents))


def test_cik_cannot_substitute_for_share_class_identity(tmp_path):
    documents = fixture_documents(security_count=1)
    documents["references.json"]["rows"][0]["security_id"] = "cik:0000123456"
    with pytest.raises(LatestRevisedSourceError, match="never an issuer CIK"):
        load_latest_revised_bundle(write_fixture(tmp_path, documents))


def test_overlapping_ticker_reuse_is_refused(tmp_path):
    documents = fixture_documents(security_count=2)
    for row in documents["references.json"]["rows"]:
        row["ticker"] = "REUSED"
    with pytest.raises(LatestRevisedSourceError, match="different share classes"):
        load_latest_revised_bundle(write_fixture(tmp_path, documents))


def test_dividend_split_and_zero_terminal_event_contract(tmp_path):
    documents = fixture_documents(security_count=1)
    identity = "figi:BBG000000000"
    documents["events.json"]["rows"] = [
        {"event_id": "split-1", "security_id": identity, "kind": "split", "at": "2024-02-20T14:00:00Z", "split_numerator": 2, "split_denominator": 1},
        {"event_id": "ex-1", "security_id": identity, "kind": "dividend_entitlement", "at": "2024-02-21T14:00:00Z", "dividend_id": "d1", "cash_per_share": "1"},
        {"event_id": "pay-1", "security_id": identity, "kind": "dividend_payment", "at": "2024-02-22T14:00:00Z", "dividend_id": "d1", "cash_per_share": "1"},
        {"event_id": "terminal-1", "security_id": identity, "kind": "terminal", "at": "2024-02-23T14:00:00Z", "cash_per_share": "0"},
    ]
    payload = load_latest_revised_bundle(write_fixture(tmp_path, documents)).to_payload()
    assert len(payload["events"]) == 4
    assert next(row for row in payload["events"] if row["kind"] == "terminal")["cash_per_share"] == "0"


def test_bundle_revalidates_authority_and_hash_after_object_mutation(tmp_path):
    bundle = load_latest_revised_bundle(write_fixture(tmp_path, fixture_documents(security_count=1)))
    payload = bundle.to_payload()
    payload["authority"]["point_in_time_data"] = True
    payload["bundle_sha256"] = hash_payload({key: value for key, value in payload.items() if key != "bundle_sha256"})
    object.__setattr__(bundle, "payload_json", canonical_json(payload))
    with pytest.raises(LatestRevisedSourceError, match="closed authority"):
        bundle.to_payload()


def test_bundle_cannot_accept_subclass_or_noncanonical_json(tmp_path):
    bundle = load_latest_revised_bundle(write_fixture(tmp_path, fixture_documents(security_count=1)))
    with pytest.raises(LatestRevisedSourceError, match="canonical serialization"):
        LatestRevisedBundle(json.dumps(bundle.to_payload()))
    class Subclass(LatestRevisedBundle):
        pass
    with pytest.raises(LatestRevisedSourceError, match="exact LatestRevisedBundle"):
        Subclass(bundle.payload_json)


def test_rehashed_financial_mutation_cannot_change_captured_bundle(tmp_path):
    bundle = load_latest_revised_bundle(write_fixture(tmp_path, fixture_documents(security_count=1)))
    payload = bundle.to_payload()
    payload["bars"][0]["open"] = "200"
    payload["bundle_sha256"] = hash_payload({key: value for key, value in payload.items() if key != "bundle_sha256"})
    object.__setattr__(bundle, "payload_json", canonical_json(payload))
    with pytest.raises(LatestRevisedSourceError, match="source record hash mismatch|captured bundle identity changed"):
        bundle.to_payload()


def test_provider_decimal_tokens_normalize_exactly_without_binary_float(tmp_path):
    documents = fixture_documents(security_count=1)
    row = documents["si-page-1.json"]["results"][0]
    row["avg_daily_volume"] = 100000.0
    row["days_to_cover"] = 1.25
    payload = load_latest_revised_bundle(write_fixture(tmp_path, documents)).to_payload()
    assert payload["observations"][0]["avg_daily_volume"] == "100000"
    assert payload["observations"][0]["days_to_cover"] == "1.25"


def test_unknown_companion_fields_and_false_pit_assertions_are_refused(tmp_path):
    documents = fixture_documents(security_count=1)
    documents["references.json"]["rows"][0]["point_in_time_data"] = True
    with pytest.raises(LatestRevisedSourceError, match="unknown fields"):
        load_latest_revised_bundle(write_fixture(tmp_path, documents))


def test_holiday_bar_cannot_be_replenished_into_session_history(tmp_path):
    documents = fixture_documents(security_count=1)
    documents["bars.json"]["rows"][0]["session"] = "2024-01-01"
    with pytest.raises(LatestRevisedSourceError, match="not an XNYS session"):
        load_latest_revised_bundle(write_fixture(tmp_path, documents))


def test_request_url_credentials_are_refused_without_persisting_them(tmp_path):
    path = write_fixture(tmp_path, fixture_documents(security_count=1))
    _rewrite_manifest(path, lambda manifest: manifest["short_interest_pages"][0].update(request_url="https://example.invalid/?apiKey=fabricated-test-value"))
    with pytest.raises(LatestRevisedSourceError, match="must not contain credentials"):
        load_latest_revised_bundle(path)


def test_calendar_predecessor_order_cannot_be_forged_using_later_publication_dates(tmp_path):
    payload = load_latest_revised_bundle(write_fixture(tmp_path, fixture_documents(security_count=1))).to_payload()
    earlier = dict(payload["releases"][1])
    earlier["publication_date"] = "2024-03-11"
    earlier["entry_session"] = resolve_nth_session_after(earlier["publication_date"], 1)
    earlier["entry_at"] = format_utc_timestamp(session_open_instant(earlier["entry_session"]))
    earlier["raw_record_sha256"] = hash_payload({key: earlier[key] for key in ("settlement_date", "publication_date")})
    # Open times increase, but settlement order does not.  A predecessor must
    # mean the prior settlement, not the prior convenient array element.
    payload["releases"] = [payload["releases"][0], payload["releases"][2], earlier]
    payload["bundle_sha256"] = hash_payload({key: value for key, value in payload.items() if key != "bundle_sha256"})
    with pytest.raises(LatestRevisedSourceError, match="schedule-derived open"):
        LatestRevisedBundle(canonical_json(payload))


def test_expected_manifest_hash_refuses_before_json_or_member_read(tmp_path, monkeypatch):
    path = write_fixture(tmp_path, fixture_documents(security_count=1))
    expected = hash_bytes(path.read_bytes())
    path.write_bytes(b"{not valid json}")
    def forbidden(*args, **kwargs):
        pytest.fail("changed manifest reached parsing or member read")
    monkeypatch.setattr(source_module, "_json", forbidden)
    monkeypatch.setattr(source_module, "_read_bound", forbidden)
    with pytest.raises(LatestRevisedSourceError, match="expected manifest SHA-256 mismatch"):
        load_latest_revised_bundle(path, expected_manifest_sha256=expected)


def test_matching_expected_hash_parses_the_exact_captured_manifest_snapshot(tmp_path, monkeypatch):
    path = write_fixture(tmp_path, fixture_documents(security_count=1))
    expected = hash_bytes(path.read_bytes())
    original_read = Path.read_bytes
    def swap_after_capture(target):
        blob = original_read(target)
        if target == path:
            target.write_bytes(b"{replaced after capture}")
        return blob
    monkeypatch.setattr(Path, "read_bytes", swap_after_capture)
    bundle = load_latest_revised_bundle(path, expected_manifest_sha256=expected)
    assert bundle.to_payload()["provenance"]["manifest_sha256"] == expected
    assert len(bundle.to_payload()["observations"]) == 3


@pytest.mark.parametrize("expected", ["BAD", "A" * 64, True, 0])
def test_expected_manifest_hash_requires_exact_canonical_sha256(tmp_path, expected):
    path = write_fixture(tmp_path, fixture_documents(security_count=1))
    with pytest.raises(LatestRevisedSourceError, match="lowercase SHA-256"):
        load_latest_revised_bundle(path, expected_manifest_sha256=expected)
