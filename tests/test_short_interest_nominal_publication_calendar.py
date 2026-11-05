"""Entirely fabricated nominal-date evidence; no market or PDF source fetch."""
from __future__ import annotations

import dataclasses
from datetime import date, timedelta
import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.nominal_publication_calendar as calendar

NOW = "2026-10-14T00:01:00Z"
SETTLEMENTS = ("2022-01-04", "2022-01-17", "2022-02-03", "2022-02-17", "2025-01-15")


def weekday(day):
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def paired_dates():
    pairs = []
    for year in (2025, 2026):
        for month in range(1, 13):
            last = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
            while last.weekday() >= 5:
                last -= timedelta(days=1)
            for at in (weekday(date(year, month, 15)), last):
                pairs.append((at.isoformat(), weekday(at + timedelta(days=7)).isoformat()))
    return tuple(pairs)


def sources():
    captures, transcripts = [], []
    for index, request_id in enumerate(calendar.REQUEST_IDS):
        raw = b"%PDF-1.7\nfabricated no real source page" + bytes([index])
        captures.append(calendar.CapturedNominalCalendarPDF(request_id,
            hash_payload(calendar.calendar_request(request_id)), raw, "application/pdf", 200,
            f"2026-10-14T00:00:0{index + 1}Z"))
        releases, pairs = (), ()
        if index < 3:
            releases = tuple(weekday(date(2022 + index, month, day)).isoformat()
                             for month in range(1, 13) for day in (10, 24))
        elif index == 3:
            releases = ("2025-01-07",) + tuple(publication for settlement, publication in paired_dates()
                                             if settlement.startswith("2025") and publication.startswith("2025"))
        else:
            pairs = paired_dates()
        transcripts.append(calendar.VisualCalendarTranscript(request_id, hash_bytes(raw), "c" * 64,
            "2026-10-14T00:00:20Z", "Codex_visual_read", releases, pairs))
    return tuple(captures), tuple(transcripts)


def qualified(captures=None, transcripts=None, settlements=SETTLEMENTS, now=NOW):
    original_captures, original_transcripts = sources()
    return calendar.qualify_nominal_calendar(captures or original_captures, transcripts or original_transcripts,
                                           settlements, retrieved_at=now)


def test_fixed_five_public_GETs_pinned_without_authentication_or_market_routes():
    protocol = calendar.calendar_protocol()
    assert hash_payload(protocol) == calendar.PROTOCOL_SHA256
    assert protocol["maximum_requests"] == 5
    assert all(item["method"] == "GET" and item["authentication"] == "none"
               and item["url"].startswith("https://www.nyse.com/publicdocs/")
               for item in protocol["requests"])
    protocol["maximum_requests"] = 99
    assert calendar.calendar_protocol()["maximum_requests"] == 5


def test_qualifies_nominal_only_and_retains_precise_pairing_semantics():
    report = qualified().to_payload()
    assert report["complete_supplied_settlement_nominal_pairs"] is True
    assert report["rows"][0]["publication_date"] == "2022-01-10"
    assert report["rows"][-1]["publication_date"] == "2025-01-22"
    assert "inference" in report["rows"][0]["pairing_semantic"]
    assert "explicit_official_NYSE" in report["rows"][-1]["pairing_semantic"]
    assert len(report["unpaired_release_markings"]) == 69
    assert all(row["observed_availability_at"] is None for row in report["rows"])
    for field in ("historical_FINRA_calendar_admitted", "availability_clock_admitted", "original_vintages_admitted",
                  "source_admitted", "backtest_ready"):
        assert report[field] is False
    assert report["outcome_looks"] == report["qc_attempts"] == 0


def test_missing_release_is_retained_not_zero_or_dropped():
    report = qualified(settlements=SETTLEMENTS + ("2026-08-25",)).to_payload()
    assert len(report["rows"]) == 6
    assert report["rows"][-1]["publication_date"] is None
    assert report["rows"][-1]["refusal_reasons"] == ["missing_or_ambiguous_nominal_release_adjacency"]
    assert report["complete_supplied_settlement_nominal_pairs"] is False


def test_nonadjacent_sparse_settlement_does_not_choose_among_two_markings():
    report = qualified(settlements=("2022-01-04", "2022-02-17")).to_payload()
    # Both January markings fall before the next supplied settlement and
    # within20days. No arbitrary first/later publication is silently selected.
    assert report["rows"][0]["publication_date"] is None


@pytest.mark.parametrize("field,value", [("http_status", True), ("http_status", 404),
    ("content_type", "text/html"), ("raw", b"<html>failure</html>"),
    ("received_at", "2026-10-14T00:00:00+00:00"), ("request_sha256", "f" * 64)])
def test_capture_signature_media_status_and_clock_refuse(field, value):
    capture = sources()[0][0]
    with pytest.raises(calendar.NominalCalendarRefusal):
        dataclasses.replace(capture, **{field: value})


@pytest.mark.parametrize("which", ["source", "render", "future", "before_receipt"])
def test_transcript_evidence_and_clock_are_bound(which):
    captures, transcripts = sources()
    changes = {"source": {"source_sha256": "d" * 64}, "render": {"render_sha256": "not-a-digest"},
               "future": {"checked_at": "2026-10-14T00:01:01Z"},
               "before_receipt": {"checked_at": "2026-10-14T00:00:00Z"}}[which]
    with pytest.raises(calendar.NominalCalendarRefusal):
        replacement = dataclasses.replace(transcripts[0], **changes)
        qualified(captures=captures, transcripts=(replacement,) + transcripts[1:])


def test_missing_duplicate_and_reordered_source_cannot_qualify():
    captures, transcripts = sources()
    for bad in (captures[:-1], (captures[0],) * 5, captures[::-1]):
        with pytest.raises(calendar.NominalCalendarRefusal):
            calendar.qualify_nominal_calendar(bad, transcripts, SETTLEMENTS, retrieved_at=NOW)


@pytest.mark.parametrize("bad", [("2022-01-04", "2022-01-04"), ("2026-09-01",), ["2022-01-04"], ("20220104",)])
def test_supplied_settlement_scope_order_type_and_duplicates_refuse(bad):
    with pytest.raises(calendar.NominalCalendarRefusal):
        qualified(settlements=bad)


def test_duplicate_missing_or_wrongyear_annual_visual_markings_refuse():
    transcript = sources()[1][0]
    for dates in (transcript.release_dates[:-1], (transcript.release_dates[0],) * 24,
                  tuple(at.replace("2022", "2021") for at in transcript.release_dates)):
        with pytest.raises(calendar.NominalCalendarRefusal):
            dataclasses.replace(transcript, release_dates=dates)


def test_annual_grid_cannot_claim_explicit_settlement_pairs():
    transcript = sources()[1][0]
    with pytest.raises(calendar.NominalCalendarRefusal):
        dataclasses.replace(transcript, settlement_publication_pairs=(("2022-01-04", "2022-01-10"),))


def test_current_paired_schedule_requires_full_48_pairs_and_exact_immutable_types():
    transcript = sources()[1][-1]
    for pairs in (transcript.settlement_publication_pairs[:-1],
                  (["2025-01-01", "2025-01-08"],) + transcript.settlement_publication_pairs[1:]):
        with pytest.raises(calendar.NominalCalendarRefusal):
            dataclasses.replace(transcript, settlement_publication_pairs=pairs)


def test_revalidates_source_mutation_before_report_and_returns_detached_bytes():
    captures, transcripts = sources()
    object.__setattr__(captures[0], "raw", b"<html>substituted</html>")
    with pytest.raises(calendar.NominalCalendarRefusal):
        qualified(captures=captures, transcripts=transcripts)
    report = qualified()
    detached = report.to_payload()
    detached["availability_clock_admitted"] = True
    assert report.to_payload()["availability_clock_admitted"] is False


def test_coherent_reseal_without_original_byte_anchor_refuses():
    report = qualified()
    payload = report.to_payload()
    payload["availability_clock_admitted"] = True
    rewritten = canonical_json(payload).encode()
    object.__setattr__(report, "_raw", rewritten)
    object.__setattr__(report, "_sha256", hash_bytes(rewritten))
    with pytest.raises(calendar.NominalCalendarRefusal, match="seal_changed"):
        report.to_payload()


def test_December_2024_settlement_keeps_nextyear_nominal_bridge():
    report = qualified(settlements=("2024-12-31", "2025-01-15")).to_payload()
    assert report["rows"][0]["publication_date"] == "2025-01-07"
    assert report["rows"][0]["request_id"] == "nyse-calendar-2025"
    assert "inference" in report["rows"][0]["pairing_semantic"]


def test_last_August_2026_settlement_keeps_September_nominal_release_without_exposure():
    report = qualified(settlements=("2026-08-31",)).to_payload()
    assert report["rows"][0]["publication_date"] == "2026-09-07"
    assert report["complete_supplied_settlement_nominal_pairs"] is True
    assert report["outcome_looks"] == 0 and report["backtest_ready"] is False


def test_2025_annual_overlap_conflict_cannot_select_a_preferred_calendar():
    captures, transcripts = sources()
    changed = list(transcripts[3].release_dates)
    changed[1] = "2025-01-23"
    replaced = dataclasses.replace(transcripts[3], release_dates=tuple(changed))
    with pytest.raises(calendar.NominalCalendarRefusal, match="conflict"):
        qualified(captures=captures, transcripts=transcripts[:3] + (replaced,) + transcripts[4:])
