"""Source-only official NYSE nominal schedules, never observed FINRA clocks.

Old annual grids mark release days, not settlement dates. Their association
with a separately supplied SI settlement inventory is an explicit inference.
Transport and visual transcription are supplied evidence, not a permission
checkbox for original vintages, outcomes, or backtesting.
"""
from __future__ import annotations

import dataclasses
from datetime import date
import json
import re

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf.contracts import parse_utc_timestamp

REQUEST_IDS = ("nyse-calendar-2022", "nyse-calendar-2023", "nyse-calendar-2024", "nyse-calendar-2025", "nyse-calendar-2025-2026")
_URLS = (
    "https://www.nyse.com/publicdocs/ICE_NYSE_2022_Yearly_Trading_Calendar.pdf",
    "https://www.nyse.com/publicdocs/ICE_NYSE_2023_Yearly_Trading_Calendar.pdf",
    "https://www.nyse.com/publicdocs/ICE_NYSE_2024_Yearly_Trading_Calendar.pdf",
    "https://www.nyse.com/publicdocs/ICE_NYSE_2025_Yearly_Trading_Calendar.pdf",
    "https://www.nyse.com/publicdocs/nyse/data/NYSE_Group_Short_Interest_Calendar.pdf",
)
MAXIMUM_REQUESTS = 5
MAXIMUM_RESPONSE_BYTES = 4 * 1024 * 1024
_SEAL = object()


class NominalCalendarRefusal(ValueError):
    """Fixed safe reasons, not external PDF text or account information."""


def _require(condition, reason):
    if not condition:
        raise NominalCalendarRefusal("REFUSED: " + reason)


def _sha(value):
    _require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None, "invalid_evidence_digest")
    return value


def _date(value):
    _require(type(value) is str, "invalid_calendar_date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise NominalCalendarRefusal("REFUSED: invalid_calendar_date") from None
    _require(parsed.isoformat() == value, "noncanonical_calendar_date")
    return parsed


def _clock(value):
    _require(type(value) is str and value.endswith("Z"), "invalid_evidence_clock")
    try:
        return parse_utc_timestamp(value, "nominal_calendar_evidence_clock")
    except ValueError:
        raise NominalCalendarRefusal("REFUSED: invalid_evidence_clock") from None


def calendar_request(request_id):
    _require(type(request_id) is str and request_id in REQUEST_IDS, "unknown_calendar_request")
    return {"request_id": request_id, "method": "GET", "url": _URLS[REQUEST_IDS.index(request_id)],
            "authentication": "none", "accept": "application/pdf"}


def _protocol_payload():
    return {"schema": "si-nominal-publication-calendar-protocol-v1",
            "requests": [calendar_request(item) for item in REQUEST_IDS],
            "maximum_requests": MAXIMUM_REQUESTS, "maximum_response_bytes": MAXIMUM_RESPONSE_BYTES,
            "automatic_retries": 0, "redirects": False, "proxies": False,
            "source": "official_NYSE_nominal_schedule_not_FINRA_actual_dissemination",
            "old_years": [2022, 2023, 2024], "old_year_rule": "24_visually_verified_release_markings_2_per_month_no_official_settlement_pairs",
            "bridge_year": 2025, "bridge_rule": "full_2025_annual_grid_earliest_January_release_for_Dec2024_only_other23_exactly_match_explicit2025_pairs",
            "paired_years": [2025, 2026], "paired_year_rule": "48_visually_verified_explicit_NYSE_settlement_release_pairs",
            "transcription_rule": "original_PDF_digest_and_separately_rendered_page_digest_required_no_text_only_color_guess",
            "old_pairing_rule": "unique_chronological_adjacency_to_supplied_SI_inventory_inferred_not_FINRA_authenticated",
            "old_pairing_maximum_calendar_days": 20,
            "requested_settlement_range": ["2022-01-01", "2026-08-31"],
            "missing_rule": "retain_every_supplied_settlement_and_unmatched_release_marking_no_default_dates",
            "timing": "hypothetical_publication_day_next_XNYS_open_no_release_instant_claim",
            "original_vintages_admitted": False, "availability_clock_admitted": False,
            "historical_FINRA_calendar_admitted": False, "backtest_ready": False,
            "outcome_looks": 0, "qc_attempts": 0}


PROTOCOL_SHA256 = "817e939b80ee3d6a43eb61f5c56e4027487d325ba344977f5e361b3df42e5b5e"


def calendar_protocol():
    result = _protocol_payload()
    _require(hash_payload(result) == PROTOCOL_SHA256, "calendar_protocol_pending_or_changed")
    return result


@dataclasses.dataclass(frozen=True, slots=True)
class CapturedNominalCalendarPDF:
    request_id: str
    request_sha256: str
    raw: bytes
    content_type: str
    http_status: int
    received_at: str

    def __post_init__(self):
        _require(type(self) is CapturedNominalCalendarPDF, "exact_calendar_capture_type_required")
        _require(self.request_sha256 == hash_payload(calendar_request(self.request_id)), "calendar_request_digest_mismatch")
        _require(type(self.request_sha256) is str, "calendar_request_digest_type")
        _require(type(self.raw) is bytes and 8 <= len(self.raw) <= MAXIMUM_RESPONSE_BYTES
                 and self.raw.startswith(b"%PDF-"), "calendar_PDF_signature_or_size")
        _require(type(self.http_status) is int and self.http_status == 200, "calendar_HTTP_status")
        _require(type(self.content_type) is str and len(self.content_type) <= 256
                 and self.content_type.split(";", 1)[0].strip().lower() == "application/pdf", "calendar_media_type")
        _clock(self.received_at)


@dataclasses.dataclass(frozen=True, slots=True)
class VisualCalendarTranscript:
    request_id: str
    source_sha256: str
    render_sha256: str
    checked_at: str
    checked_by: str
    release_dates: tuple[str, ...] = ()
    settlement_publication_pairs: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        _require(type(self) is VisualCalendarTranscript, "exact_visual_transcript_type_required")
        calendar_request(self.request_id)
        _sha(self.source_sha256), _sha(self.render_sha256)
        _clock(self.checked_at)
        _require(type(self.checked_by) is str and self.checked_by in ("Codex_visual_read", "owner_visual_read"), "visual_check_actor")
        _require(type(self.release_dates) is tuple and type(self.settlement_publication_pairs) is tuple,
                 "immutable_transcription_required")
        if self.request_id != REQUEST_IDS[-1]:
            year = 2022 + REQUEST_IDS.index(self.request_id)
            _require(not self.settlement_publication_pairs and len(self.release_dates) == 24,
                     "annual_grid_requires_24_release_dates_not_settlement_assertions")
            days = tuple(_date(item) for item in self.release_dates)
            _require(tuple(sorted(set(days))) == days and all(day.year == year and day.weekday() < 5 for day in days)
                     and all(sum(day.month == month for day in days) == 2 for month in range(1, 13)),
                     "annual_release_markings_duplicate_order_year_or_month")
        else:
            _require(not self.release_dates and len(self.settlement_publication_pairs) == 48,
                     "paired_grid_requires_48_explicit_pairs")
            pairs = self.settlement_publication_pairs
            _require(all(type(pair) is tuple and len(pair) == 2 for pair in pairs), "immutable_pair_required")
            settlements = tuple(_date(pair[0]) for pair in pairs)
            publications = tuple(_date(pair[1]) for pair in pairs)
            _require(tuple(sorted(set(settlements))) == settlements and tuple(sorted(set(publications))) == publications
                     and all(a < b and a.weekday() < 5 and b.weekday() < 5 for a, b in zip(settlements, publications))
                     and all(sum(a.year == year and a.month == month for a in settlements) == 2
                             for year in (2025, 2026) for month in range(1, 13))
                     and all(a.year in (2025, 2026) for a in settlements), "paired_schedule_order_or_inventory")


@dataclasses.dataclass(frozen=True, slots=True)
class QualifiedNominalCalendar:
    _raw: bytes
    _sha256: str
    _original: bytes
    _seal: object

    def to_payload(self):
        _require(type(self) is QualifiedNominalCalendar and self._seal is _SEAL
                 and type(self._raw) is bytes and self._raw is self._original
                 and hash_bytes(self._raw) == self._sha256, "nominal_calendar_seal_changed")
        return json.loads(self._raw)

    def to_bytes(self):
        self.to_payload()
        return self._raw

    @property
    def sha256(self):
        self.to_payload()
        return self._sha256


def qualify_nominal_calendar(captures, transcripts, settlement_dates, *, retrieved_at):
    """Bind supplied visual evidence; do not authenticate its human assertions.

    Every supplied settlement survives in the report even when unpaired. Old
    release-only grids do not suddenly become official FINRA settlement pairs.
    """
    calendar_protocol()
    end = _clock(retrieved_at)
    _require(type(captures) is tuple and type(transcripts) is tuple
             and len(captures) == len(transcripts) == 5, "complete_five_calendar_sources_required")
    _require(all(type(item) is CapturedNominalCalendarPDF for item in captures)
             and tuple(item.request_id for item in captures) == REQUEST_IDS
             and all(type(item) is VisualCalendarTranscript for item in transcripts)
             and tuple(item.request_id for item in transcripts) == REQUEST_IDS,
             "calendar_source_order_or_type")
    _require(type(settlement_dates) is tuple and bool(settlement_dates), "supplied_settlement_inventory_required")
    days = tuple(_date(item) for item in settlement_dates)
    _require(tuple(sorted(set(days))) == days and all(date(2022, 1, 1) <= day <= date(2026, 8, 31) for day in days),
             "settlement_inventory_order_or_scope")
    sources, old_releases, paired, used = [], [], {}, set()
    previous = None
    for capture, transcript in zip(captures, transcripts):
        capture.__post_init__(), transcript.__post_init__()
        received, checked = _clock(capture.received_at), _clock(transcript.checked_at)
        _require((previous is None or previous <= received) and received <= checked <= end, "visual_source_chronology")
        previous = received
        _require(transcript.source_sha256 == hash_bytes(capture.raw), "visual_transcription_source_digest")
        source = {"request_id": capture.request_id, "request_sha256": capture.request_sha256,
                  "url": calendar_request(capture.request_id)["url"], "raw_sha256": hash_bytes(capture.raw),
                  "raw_bytes": len(capture.raw), "http_status": capture.http_status,
                  "content_type": capture.content_type, "received_at": capture.received_at,
                  "render_sha256": transcript.render_sha256, "checked_at": transcript.checked_at,
                  "checked_by": transcript.checked_by, "PDF_check": "signature_only_not_full_PDF_validation",
                  "visual_check": "supplied_visual_transcription_assertion_bound_to_digests",
                  "release_dates": list(transcript.release_dates),
                  "settlement_publication_pairs": [list(pair) for pair in transcript.settlement_publication_pairs]}
        sources.append(source)
        if capture.request_id == "nyse-calendar-2025":
            old_releases.append((transcript.release_dates[0], capture.request_id))
        else:
            old_releases.extend((item, capture.request_id) for item in transcript.release_dates)
        paired.update((a, (b, capture.request_id)) for a, b in transcript.settlement_publication_pairs)
    bridge_grid = transcripts[3].release_dates
    current_2025 = tuple(publication for settlement, (publication, _) in paired.items()
                         if _date(settlement).year == 2025 and _date(publication).year == 2025)
    _require(len(current_2025) == 23 and tuple(sorted(current_2025)) == bridge_grid[1:]
             and _date(bridge_grid[0]).month == 1 and bridge_grid[0] < min(current_2025),
             "annual2025_explicit2025_nominal_schedule_conflict")
    rows = []
    for index, (settlement, day) in enumerate(zip(settlement_dates, days)):
        next_day = days[index + 1] if index + 1 < len(days) else date.max
        reasons = []
        if settlement in paired:
            publication, request_id = paired[settlement]
            semantic = "explicit_official_NYSE_pair_not_authenticated_FINRA_historical_calendar"
        else:
            candidates = [(at, request_id) for at, request_id in old_releases
                          if day < _date(at) < next_day and 0 < (_date(at) - day).days <= 20
                          and (request_id != "nyse-calendar-2025" or day.year == 2024 and day.month == 12)]
            if len(candidates) != 1:
                publication, request_id = None, None
                reasons.append("missing_or_ambiguous_nominal_release_adjacency")
            else:
                publication, request_id = candidates[0]
                used.add((publication, request_id))
            semantic = "supplied_SI_settlement_unique_adjacency_inference_not_official_FINRA_pair"
        rows.append({"settlement_date": settlement, "publication_date": publication,
                     "request_id": request_id, "pairing_semantic": semantic,
                     "observed_availability_at": None, "refusal_reasons": reasons})
    payload = {"schema": "si-qualified-nominal-publication-calendar-v1", "protocol_sha256": PROTOCOL_SHA256,
               "retrieved_at": retrieved_at, "sources": sources, "rows": rows,
               "unpaired_release_markings": [{"publication_date": at, "request_id": request_id}
                                              for at, request_id in old_releases if (at, request_id) not in used],
               "complete_supplied_settlement_nominal_pairs": all(not row["refusal_reasons"] for row in rows),
               "source": "NYSE_nominal_schedule_only", "latest_revised_hypothetical_replay_only": True,
               "historical_FINRA_calendar_admitted": False, "availability_clock_admitted": False,
               "original_vintages_admitted": False, "source_admitted": False, "backtest_ready": False,
               "outcome_looks": 0, "qc_attempts": 0}
    raw = canonical_json(payload).encode()
    return QualifiedNominalCalendar(raw, hash_bytes(raw), raw, _SEAL)
