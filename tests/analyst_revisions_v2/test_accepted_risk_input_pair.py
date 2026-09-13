from __future__ import annotations

import ast
import dataclasses
from fractions import Fraction
from pathlib import Path

import pytest

from research.analyst_revisions_v2 import accepted_risk_input_pair as pair_module
from research.analyst_revisions_v2.accepted_risk_input_pair import (
    AcceptedRiskInputError,
    AcceptedRiskInputPair,
    BreakdownDimension,
    CaptureBinding,
    CapturePageBinding,
    InputView,
    MassiveSourceRole,
    RowDisposition,
    bind_capture_page,
    build_accepted_risk_input_pair,
    build_capture_binding,
    render_redacted_capture_query_bytes,
    require_accepted_risk_input_pair,
    require_capture_binding,
)
from research.analyst_revisions_v2.canonical import (
    CanonicalEvidenceError,
    canonical_json_bytes,
    sha256_bytes,
)


STARTED = "2026-09-11T18:00:00.000000Z"
COMPLETED = "2026-09-11T18:04:00.000000Z"
FIRST = "2011-01-01"
LAST = "2025-12-31"
ROLE_TIMES = {
    MassiveSourceRole.ANALYST_RATINGS: "2026-09-11T18:01:00.000000Z",
    MassiveSourceRole.EARNINGS: "2026-09-11T18:02:00.000000Z",
    MassiveSourceRole.CORPORATE_GUIDANCE: "2026-09-11T18:03:00.000000Z",
}
ROLE_HASHES = {
    MassiveSourceRole.ANALYST_RATINGS: "1" * 64,
    MassiveSourceRole.EARNINGS: "2" * 64,
    MassiveSourceRole.CORPORATE_GUIDANCE: "3" * 64,
}


def _row(
    event_id: str,
    *,
    event_date: str = "2020-01-02",
    event_time: object = "09:31:00",
    last_updated: object = "2020-01-03T12:00:00Z",
    ticker: object = "AAA",
    action: object = "upgrades",
    firm_id: object = "firm-1",
    **extra,
):
    value = {
        "benzinga_id": event_id,
        "date": event_date,
        "time": event_time,
        "last_updated": last_updated,
        "ticker": ticker,
        "rating_action": action,
        "benzinga_firm_id": firm_id,
    }
    value.update(extra)
    return value


def _rows_bytes(rows) -> bytes:
    return b"".join(canonical_json_bytes(row) for row in rows)


def _page(
    role: MassiveSourceRole,
    rows,
    *,
    page_number: int = 1,
    request_cursor_sha256: str | None = None,
    next_cursor_sha256: str | None = None,
    terminal_page: bool = True,
    received_at: str | None = None,
    raw_response_sha256: str | None = None,
    first: str = FIRST,
    last: str = LAST,
):
    return bind_capture_page(
        source_role=role,
        redacted_query_bytes=render_redacted_capture_query_bytes(
            source_role=role,
            requested_first_event_date=first,
            requested_last_event_date=last,
        ),
        page_number=page_number,
        request_cursor_sha256=request_cursor_sha256,
        next_cursor_sha256=next_cursor_sha256,
        terminal_page=terminal_page,
        response_received_at=received_at or ROLE_TIMES[role],
        raw_response_sha256=raw_response_sha256 or ROLE_HASHES[role],
        provider_rows_bytes=_rows_bytes(rows),
    )


def _capture(
    *,
    ratings=None,
    earnings=None,
    guidance=None,
    pages=None,
    started: str = STARTED,
    completed: str = COMPLETED,
):
    if pages is None:
        pages = (
            _page(
                MassiveSourceRole.ANALYST_RATINGS,
                ratings if ratings is not None else [_row("rating-1")],
            ),
            _page(
                MassiveSourceRole.EARNINGS,
                earnings
                if earnings is not None
                else [_row("earnings-1", action="earnings")],
            ),
            _page(
                MassiveSourceRole.CORPORATE_GUIDANCE,
                guidance
                if guidance is not None
                else [_row("guidance-1", action="guidance")],
            ),
        )
    return build_capture_binding(
        capture_started_at=started,
        capture_completed_at=completed,
        pages=tuple(pages),
    )


def test_one_capture_derives_both_explicitly_non_pristine_views():
    capture = _capture(
        ratings=[
            _row("rating-early-touch"),
            _row("rating-late-touch", last_updated="2020-01-07T12:00:00Z"),
            _row(
                "rating-pre-2013",
                event_date="2012-12-31",
                last_updated="2013-01-01T12:00:00Z",
            ),
        ],
        earnings=[_row("earnings-1", action="earnings")],
        guidance=[_row("guidance-1", action="guidance")],
    )
    pair = build_accepted_risk_input_pair(capture)

    assert require_capture_binding(capture) is capture
    assert require_accepted_risk_input_pair(pair) is pair
    assert pair.capture is capture
    assert pair.views_share_one_capture is True
    assert pair.pristine_point_in_time is False
    assert pair.earlier_version_imputation_performed is False
    assert pair.current_view_label.endswith("non_pristine_pit")
    assert pair.censored_view_label.endswith("non_pristine_pit")
    assert pair.report.total_row_count == 5
    assert pair.report.current_included_count == 4
    assert pair.report.censored_included_count == 3
    assert pair.report.disagreement_count == 1

    assert tuple(id(row) for row in pair.current_rows if row.censored_view.included) == tuple(
        id(row) for row in pair.censored_rows
    )
    late = next(row for row in pair.rows if row.provider_event_id == "rating-late-touch")
    assert late.current_view.included is True
    assert late.censored_view.disposition is (
        RowDisposition.CENSORED_LAST_TOUCH_AFTER_DECISION_CUTOFF
    )
    assert late.raw_row_bytes == canonical_json_bytes(
        next(
            row
            for row in capture.pages[0].parsed_rows
            if row["benzinga_id"] == "rating-late-touch"
        )
    )


def test_static_c1_contract_is_content_addressed_and_bound_into_both_artifacts():
    payload = pair_module.render_accepted_risk_input_pair_contract_bytes()
    assert pair_module.INPUT_PAIR_CONTRACT_SHA256 == (
        "b2b78be3e11a8c0f7995af6a14f819a1bc5283ca1c51638e9e92130590c6b4b0"
    )
    assert sha256_bytes(payload) == pair_module.INPUT_PAIR_CONTRACT_SHA256
    record = pair_module.accepted_risk_input_pair_contract_record()
    assert record["capture"]["transactional_snapshot"] is False
    assert record["capture"]["last_updated_filter_applied"] is False
    assert record["pristine_point_in_time"] is False
    capture = _capture()
    pair = build_accepted_risk_input_pair(capture)
    assert capture.contract_id == pair_module.INPUT_PAIR_CONTRACT_ID
    assert capture.contract_sha256 == pair_module.INPUT_PAIR_CONTRACT_SHA256
    assert pair.contract_id == capture.contract_id
    assert pair.contract_sha256 == capture.contract_sha256


def test_censored_cutoff_is_second_exchange_session_open_and_boundary_is_inclusive():
    capture = _capture(
        ratings=[
            _row("at-cutoff", last_updated="2020-01-06T14:30:00Z"),
            _row("after-cutoff", last_updated="2020-01-06T14:30:00.000001Z"),
        ]
    )
    pair = build_accepted_risk_input_pair(capture)
    at_cutoff, after_cutoff = pair.rows[:2]

    assert at_cutoff.current_view.eligible_session == "2020-01-06"
    assert at_cutoff.current_view.eligible_at == "2020-01-06T14:30:00.000000Z"
    assert at_cutoff.current_view.decision_cutoff_at == at_cutoff.current_view.eligible_at
    assert at_cutoff.censored_view.included is True
    assert at_cutoff.censored_view.last_updated_not_after_cutoff is True
    assert after_cutoff.current_view.included is True
    assert after_cutoff.censored_view.included is False
    assert after_cutoff.censored_view.last_updated_not_after_cutoff is False


def test_rating_and_earnings_intraday_clocks_are_audit_only():
    pair = build_accepted_risk_input_pair(_capture())
    rating, earnings = pair.rows[:2]
    assert rating.clock_interpretation == (
        "documented_utc_time_audit_only_date_only_two_session_eligibility"
    )
    assert earnings.clock_interpretation == (
        "literal_est_time_audit_only_no_dst_inference_date_only_two_session_eligibility"
    )
    assert rating.current_view.eligible_session == earnings.current_view.eligible_session
    assert rating.current_view.event_clock_not_after_cutoff is True
    assert earnings.current_view.event_clock_not_after_cutoff is True


def test_guidance_uses_delayed_date_only_policy_without_claiming_clock_authentication():
    pair = build_accepted_risk_input_pair(
        _capture(
            guidance=[
                _row(
                    "guidance-aware",
                    event_time="07:00:00",
                    last_updated="2020-01-02T12:00:00-05:00",
                    action="raises_guidance",
                )
            ]
        )
    )
    guidance = pair.rows[-1]
    assert guidance.normalized_last_updated_at == "2020-01-02T17:00:00.000000Z"
    assert guidance.last_updated_calendar_date == "2020-01-02"
    assert guidance.current_view.disposition is (
        RowDisposition.INCLUDED_CURRENT_ROW_NON_PRISTINE
    )
    assert guidance.censored_view.disposition is (
        RowDisposition.INCLUDED_CONSERVATIVE_CENSORED_NON_PRISTINE
    )
    assert guidance.current_view.eligible_session == "2020-01-07"
    assert guidance.current_view.eligible_at == "2020-01-07T14:30:00.000000Z"
    assert guidance.current_view.included is True
    assert guidance.censored_view.included is True
    assert pair.guidance_clock_authenticated is False


def test_guidance_naive_last_updated_is_censored_by_calendar_date_only():
    pair = build_accepted_risk_input_pair(
        _capture(
            guidance=[
                _row(
                    "guidance-naive-before",
                    last_updated="2020-01-06 23:59:59",
                    action="raises_guidance",
                ),
                _row(
                    "guidance-naive-on-cutoff",
                    last_updated="2020-01-07T00:00:00",
                    action="lowers_guidance",
                ),
            ]
        )
    )
    before, on_cutoff = pair.rows[-2:]
    assert before.normalized_last_updated_at is None
    assert before.last_updated_calendar_date == "2020-01-06"
    assert before.current_view.included is True
    assert before.censored_view.included is True
    assert on_cutoff.last_updated_calendar_date == "2020-01-07"
    assert on_cutoff.current_view.included is True
    assert on_cutoff.censored_view.included is False
    assert on_cutoff.censored_view.disposition is (
        RowDisposition.CENSORED_LAST_TOUCH_AFTER_DECISION_CUTOFF
    )


def test_pre_2013_rows_are_quarantined_in_both_views():
    pair = build_accepted_risk_input_pair(
        _capture(
            ratings=[
                _row(
                    "old",
                    event_date="2012-01-03",
                    last_updated="2012-01-03T18:00:00Z",
                )
            ]
        )
    )
    old = pair.rows[0]
    expected = RowDisposition.PROVIDER_BACKFILL_SEMANTICS_UNVERIFIED_PRE_2013
    assert old.current_view.disposition is expected
    assert old.censored_view.disposition is expected
    assert old.event_year == 2012


@pytest.mark.parametrize(
    "last_updated",
    [None, "", "2020-01-03 12:00:00", "2020-01-03T12:00:00", "not-a-time"],
)
def test_missing_or_naive_last_updated_is_current_only_not_imputed(last_updated):
    pair = build_accepted_risk_input_pair(
        _capture(ratings=[_row("invalid-update", last_updated=last_updated)])
    )
    row = pair.rows[0]
    assert row.current_view.included is True
    assert row.censored_view.disposition is (
        RowDisposition.INVALID_LAST_UPDATED_EXPLICIT_OFFSET
    )
    assert row.normalized_last_updated_at is None
    assert pair.earlier_version_imputation_performed is False


def test_last_updated_later_than_capture_invalidates_both_views():
    pair = build_accepted_risk_input_pair(
        _capture(ratings=[_row("future-touch", last_updated="2027-01-01T00:00:00Z")])
    )
    row = pair.rows[0]
    assert row.current_view.disposition is RowDisposition.LAST_UPDATED_AFTER_CAPTURE
    assert row.censored_view.disposition is RowDisposition.LAST_UPDATED_AFTER_CAPTURE
    assert row.current_view.included is False


def test_overprecision_last_updated_cannot_round_down_across_cutoff():
    pair = build_accepted_risk_input_pair(
        _capture(
            ratings=[
                _row(
                    "overprecision",
                    last_updated="2020-01-06T14:30:00.0000009Z",
                )
            ]
        )
    )
    row = pair.rows[0]
    assert row.normalized_last_updated_at is None
    assert row.current_view.included is True
    assert row.censored_view.disposition is (
        RowDisposition.INVALID_LAST_UPDATED_EXPLICIT_OFFSET
    )


@pytest.mark.parametrize(
    ("row", "disposition"),
    [
        (
            {"date": "2020-01-02", "time": "09:00:00", "last_updated": "2020-01-03T00:00:00Z"},
            RowDisposition.INVALID_PROVIDER_EVENT_ID,
        ),
        (
            _row("bad-date", event_date="2020-02-30"),
            RowDisposition.INVALID_EVENT_DATE,
        ),
        (
            _row("bad-time", event_time="25:00:00"),
            RowDisposition.INVALID_EVENT_TIME,
        ),
    ],
)
def test_structural_row_defects_have_exhaustive_named_dispositions(row, disposition):
    pair = build_accepted_risk_input_pair(_capture(ratings=[row]))
    source = pair.rows[0]
    assert source.current_view.disposition is disposition
    assert source.censored_view.disposition is disposition
    assert len(pair.rows) == pair.capture.total_row_count


def test_null_event_time_is_allowed_because_intraday_is_not_used_for_eligibility():
    pair = build_accepted_risk_input_pair(
        _capture(ratings=[_row("date-only", event_time=None)])
    )
    row = pair.rows[0]
    assert row.raw_event_time is None
    assert row.current_view.included is True
    assert row.censored_view.included is True


def test_out_of_query_range_is_a_named_row_disposition():
    pair = build_accepted_risk_input_pair(
        _capture(ratings=[_row("outside", event_date="2026-01-02")])
    )
    row = pair.rows[0]
    assert row.current_view.disposition is (
        RowDisposition.EVENT_OUTSIDE_REQUESTED_CAPTURE_RANGE
    )


def test_query_descriptor_forbids_last_updated_filter_credentials_and_cursor_material():
    payload = render_redacted_capture_query_bytes(
        source_role=MassiveSourceRole.ANALYST_RATINGS,
        requested_first_event_date=FIRST,
        requested_last_event_date=LAST,
    )
    assert b"api_key" not in payload
    assert b'"last_updated_filter_applied":false' in payload
    assert b'"credential_material_included":false' in payload
    assert b'"cursor_material_included":false' in payload

    record = pair_module.require_canonical_json_bytes(payload, "query")
    record["last_updated_filter_applied"] = True
    changed = canonical_json_bytes(record)
    with pytest.raises(AcceptedRiskInputError, match="literal false"):
        _page(
            MassiveSourceRole.ANALYST_RATINGS,
            [_row("r")],
        ).__class__(
            schema=pair_module.CAPTURE_PAGE_SCHEMA,
            source_role=MassiveSourceRole.ANALYST_RATINGS,
            endpoint_identifier="massive_benzinga_analyst_ratings_rest",
            redacted_query_bytes=changed,
            redacted_query_sha256=sha256_bytes(changed),
            page_number=1,
            request_cursor_sha256=None,
            next_cursor_sha256=None,
            terminal_page=True,
            response_received_at=ROLE_TIMES[MassiveSourceRole.ANALYST_RATINGS],
            raw_response_sha256="1" * 64,
            provider_rows_bytes=_rows_bytes([_row("r")]),
            provider_rows_sha256=sha256_bytes(_rows_bytes([_row("r")])),
            row_count=1,
        )


def test_page_binding_authenticates_exact_jsonl_bytes_hash_and_count():
    page = _page(MassiveSourceRole.ANALYST_RATINGS, [_row("r")])
    assert page.provider_rows_sha256 == sha256_bytes(page.provider_rows_bytes)
    assert page.redacted_query_sha256 == sha256_bytes(page.redacted_query_bytes)
    assert page.row_count == 1

    with pytest.raises(AcceptedRiskInputError, match="bytes/hash mismatch"):
        dataclasses.replace(page, provider_rows_sha256="f" * 64)
    with pytest.raises(AcceptedRiskInputError, match="row_count"):
        dataclasses.replace(page, row_count=2)
    with pytest.raises(AcceptedRiskInputError, match="JSON object"):
        bind_capture_page(
            source_role=MassiveSourceRole.ANALYST_RATINGS,
            redacted_query_bytes=page.redacted_query_bytes,
            page_number=1,
            request_cursor_sha256=None,
            next_cursor_sha256=None,
            terminal_page=True,
            response_received_at=page.response_received_at,
            raw_response_sha256="1" * 64,
            provider_rows_bytes=b'[{"benzinga_id":"r"}]\n',
        )


def test_raw_response_bytes_prove_complete_ordered_results_extraction_when_present():
    rows = [_row("raw-1"), _row("raw-2", ticker="BBB")]
    raw_response = canonical_json_bytes(
        {"results": rows, "status": "OK", "next_url": None}
    )
    page = bind_capture_page(
        source_role=MassiveSourceRole.ANALYST_RATINGS,
        redacted_query_bytes=render_redacted_capture_query_bytes(
            source_role=MassiveSourceRole.ANALYST_RATINGS,
            requested_first_event_date=FIRST,
            requested_last_event_date=LAST,
        ),
        page_number=1,
        request_cursor_sha256=None,
        next_cursor_sha256=None,
        terminal_page=True,
        response_received_at=ROLE_TIMES[MassiveSourceRole.ANALYST_RATINGS],
        raw_response_sha256=sha256_bytes(raw_response),
        raw_response_bytes=raw_response,
        provider_rows_bytes=_rows_bytes(rows),
    )
    assert page.raw_response_extraction_verified is True
    assert page.lineage_record()["raw_response_extraction_verified"] is True
    assert _page(
        MassiveSourceRole.ANALYST_RATINGS, [_row("hash-only")]
    ).raw_response_extraction_verified is False

    with pytest.raises(AcceptedRiskInputError, match="complete ordered"):
        dataclasses.replace(
            page,
            provider_rows_bytes=_rows_bytes(tuple(reversed(rows))),
            provider_rows_sha256=sha256_bytes(_rows_bytes(tuple(reversed(rows)))),
        )
    with pytest.raises(AcceptedRiskInputError, match="raw response bytes/hash"):
        dataclasses.replace(page, raw_response_sha256="f" * 64)


def test_exact_provider_numeric_lexemes_are_preserved_without_reserialization():
    raw = (
        b'{"benzinga_firm_id":"firm-1","benzinga_id":"numeric-row",'
        b'"date":"2020-01-02","last_updated":"2020-01-03T12:00:00Z",'
        b'"price_target":12.3400,"rating_action":"upgrades",'
        b'"ticker":"AAA","time":"09:31:00"}\n'
    )
    ratings = bind_capture_page(
        source_role=MassiveSourceRole.ANALYST_RATINGS,
        redacted_query_bytes=render_redacted_capture_query_bytes(
            source_role=MassiveSourceRole.ANALYST_RATINGS,
            requested_first_event_date=FIRST,
            requested_last_event_date=LAST,
        ),
        page_number=1,
        request_cursor_sha256=None,
        next_cursor_sha256=None,
        terminal_page=True,
        response_received_at=ROLE_TIMES[MassiveSourceRole.ANALYST_RATINGS],
        raw_response_sha256="1" * 64,
        provider_rows_bytes=raw,
    )
    capture = _capture(pages=(ratings, *_capture().pages[1:]))
    source = build_accepted_risk_input_pair(capture).rows[0]
    assert source.raw_row_bytes == raw
    assert b"12.3400" in source.raw_row_bytes
    assert source.locator.raw_row_sha256 == sha256_bytes(raw)


def test_cursor_lineage_is_complete_hashed_and_contiguous():
    cursor = "a" * 64
    first = _page(
        MassiveSourceRole.ANALYST_RATINGS,
        [_row("r1")],
        page_number=1,
        next_cursor_sha256=cursor,
        terminal_page=False,
        received_at="2026-09-11T18:00:30.000000Z",
    )
    second = _page(
        MassiveSourceRole.ANALYST_RATINGS,
        [_row("r2")],
        page_number=2,
        request_cursor_sha256=cursor,
        received_at="2026-09-11T18:01:00.000000Z",
        raw_response_sha256="4" * 64,
    )
    capture = _capture(
        pages=(
            first,
            second,
            _page(MassiveSourceRole.EARNINGS, [_row("e")]),
            _page(MassiveSourceRole.CORPORATE_GUIDANCE, [_row("g")]),
        )
    )
    assert capture.total_page_count == 4
    assert capture.total_row_count == 4

    broken = dataclasses.replace(second, request_cursor_sha256="b" * 64)
    with pytest.raises(AcceptedRiskInputError, match="cursor chain"):
        _capture(pages=(first, broken, *capture.pages[2:]))


def test_cursor_self_loop_and_raw_response_replay_refuse_capture():
    cursor = "a" * 64
    first = _page(
        MassiveSourceRole.ANALYST_RATINGS,
        [_row("r1")],
        page_number=1,
        next_cursor_sha256=cursor,
        terminal_page=False,
        received_at="2026-09-11T18:00:30.000000Z",
    )
    loop = _page(
        MassiveSourceRole.ANALYST_RATINGS,
        [_row("r2")],
        page_number=2,
        request_cursor_sha256=cursor,
        next_cursor_sha256=cursor,
        terminal_page=False,
        received_at="2026-09-11T18:00:45.000000Z",
        raw_response_sha256="4" * 64,
    )
    terminal = _page(
        MassiveSourceRole.ANALYST_RATINGS,
        [_row("r3")],
        page_number=3,
        request_cursor_sha256=cursor,
        received_at="2026-09-11T18:01:00.000000Z",
        raw_response_sha256="5" * 64,
    )
    remaining = _capture().pages[1:]
    with pytest.raises(AcceptedRiskInputError, match="repeats or cycles"):
        _capture(pages=(first, loop, terminal, *remaining))

    replay = dataclasses.replace(terminal, raw_response_sha256=first.raw_response_sha256)
    middle = dataclasses.replace(
        loop,
        next_cursor_sha256="b" * 64,
    )
    replay = dataclasses.replace(replay, request_cursor_sha256="b" * 64)
    with pytest.raises(AcceptedRiskInputError, match="replays a response"):
        _capture(pages=(first, middle, replay, *remaining))


@pytest.mark.parametrize("mutation", ["first_cursor", "unterminated", "gap"])
def test_cursor_and_page_topology_refuses_ambiguous_capture(mutation):
    first = _page(MassiveSourceRole.ANALYST_RATINGS, [_row("r")])
    if mutation == "first_cursor":
        first = dataclasses.replace(first, request_cursor_sha256="a" * 64)
    elif mutation == "unterminated":
        first = dataclasses.replace(
            first, terminal_page=False, next_cursor_sha256="a" * 64
        )
    else:
        first = dataclasses.replace(first, page_number=2)
    with pytest.raises(AcceptedRiskInputError):
        _capture(
            pages=(
                first,
                _page(MassiveSourceRole.EARNINGS, [_row("e")]),
                _page(MassiveSourceRole.CORPORATE_GUIDANCE, [_row("g")]),
            )
        )


def test_every_required_role_and_one_date_range_are_mandatory():
    pages = (
        _page(MassiveSourceRole.ANALYST_RATINGS, [_row("r")]),
        _page(MassiveSourceRole.EARNINGS, [_row("e")]),
        _page(MassiveSourceRole.CORPORATE_GUIDANCE, [_row("g")]),
    )
    with pytest.raises(AcceptedRiskInputError, match="all three"):
        _capture(pages=pages[:-1])
    with pytest.raises(AcceptedRiskInputError, match="canonical order"):
        _capture(pages=(pages[1], pages[0], pages[2]))
    changed_earnings = _page(
        MassiveSourceRole.EARNINGS, [_row("e")], last="2024-12-31"
    )
    with pytest.raises(AcceptedRiskInputError, match="same requested"):
        _capture(pages=(pages[0], changed_earnings, pages[2]))


def test_duplicate_provider_id_within_a_source_role_invalidates_whole_capture():
    with pytest.raises(AcceptedRiskInputError, match="duplicate provider event ID"):
        _capture(
            ratings=[_row("duplicate"), _row("duplicate", ticker="BBB")]
        )


def test_duplicate_provider_id_across_endpoints_also_invalidates_capture():
    with pytest.raises(AcceptedRiskInputError, match="duplicate provider event ID"):
        _capture(
            ratings=[_row("global-id")],
            earnings=[_row("global-id", action="earnings")],
        )


def test_capture_identity_binds_pages_queries_receipts_counts_and_hashes():
    first = _capture()
    second = _capture()
    assert first.capture_id == second.capture_id
    assert first.capture_sha256 == second.capture_sha256

    changed_page = _page(
        MassiveSourceRole.ANALYST_RATINGS, [_row("rating-1", ticker="BBB")]
    )
    changed = _capture(pages=(changed_page, *first.pages[1:]))
    assert changed.capture_sha256 != first.capture_sha256
    assert changed.capture_id != first.capture_id
    assert first.transactional_snapshot is False
    assert first.complete_version_history is False
    assert first.complete_deletion_tombstones is False
    assert first.point_in_time_ticker_identity is False
    assert first.pristine_point_in_time is False


def test_capture_and_pair_authority_refuse_clones_and_post_build_mutation():
    capture = _capture()
    capture_clone = object.__new__(CaptureBinding)
    for field in dataclasses.fields(capture):
        object.__setattr__(capture_clone, field.name, getattr(capture, field.name))
    with pytest.raises(AcceptedRiskInputError, match="builder-authenticated"):
        require_capture_binding(capture_clone)

    pair = build_accepted_risk_input_pair(capture)
    pair_clone = object.__new__(AcceptedRiskInputPair)
    for field in dataclasses.fields(pair):
        object.__setattr__(pair_clone, field.name, getattr(pair, field.name))
    with pytest.raises(AcceptedRiskInputError, match="builder-authenticated"):
        require_accepted_risk_input_pair(pair_clone)

    object.__setattr__(pair, "signal_rows_constructed", True)
    with pytest.raises(AcceptedRiskInputError, match="changed after authentication"):
        require_accepted_risk_input_pair(pair)


def test_pair_authority_refuses_equal_report_rewire_and_hostile_nested_scalar():
    pair = build_accepted_risk_input_pair(_capture())
    equal_report = dataclasses.replace(pair.report)
    object.__setattr__(pair, "report", equal_report)
    with pytest.raises(AcceptedRiskInputError, match="container topology changed"):
        require_accepted_risk_input_pair(pair)

    pair = build_accepted_risk_input_pair(_capture())
    calls = 0

    class HostileString(str):
        def __eq__(self, other):
            nonlocal calls
            calls += 1
            return super().__eq__(other)

    object.__setattr__(pair.rows[0], "action_label", HostileString("attacker-label"))
    with pytest.raises(AcceptedRiskInputError, match="exact string"):
        require_accepted_risk_input_pair(pair)
    assert calls == 0


def test_capture_page_hostile_scalar_is_refused_before_equality_dispatch():
    capture = _capture()
    calls = 0

    class HostileString(str):
        def __eq__(self, other):
            nonlocal calls
            calls += 1
            return super().__eq__(other)

    object.__setattr__(capture.pages[0], "endpoint_identifier", HostileString("x"))
    with pytest.raises(AcceptedRiskInputError, match="capture page changed"):
        require_capture_binding(capture)
    assert calls == 0


def test_static_guard_and_inner_duplicate_helper_are_identity_pinned():
    pages = _capture().pages
    original_helper = pair_module._candidate_provider_event_id
    pair_module._candidate_provider_event_id = lambda row: None
    try:
        with pytest.raises(AcceptedRiskInputError, match="static contract changed"):
            build_capture_binding(
                capture_started_at=STARTED,
                capture_completed_at=COMPLETED,
                pages=pages,
            )
    finally:
        pair_module._candidate_provider_event_id = original_helper

    original_guard = pair_module._require_static_contract
    pair_module._require_static_contract = lambda: None
    try:
        with pytest.raises(AcceptedRiskInputError, match="static contract changed"):
            build_capture_binding(
                capture_started_at=STARTED,
                capture_completed_at=COMPLETED,
                pages=pages,
            )
    finally:
        pair_module._require_static_contract = original_guard

    original_capture_type = pair_module.CaptureBinding

    class FakeCapture:
        pass

    pair_module.CaptureBinding = FakeCapture
    try:
        with pytest.raises(AcceptedRiskInputError, match="static contract changed"):
            build_capture_binding(
                capture_started_at=STARTED,
                capture_completed_at=COMPLETED,
                pages=pages,
            )
    finally:
        pair_module.CaptureBinding = original_capture_type


@pytest.mark.parametrize(
    "alias_name",
    [
        "_PINNED_DERIVE_EVENT_AVAILABILITY",
        "_PINNED_REFUSE_DUPLICATE_PROVIDER_IDS",
        "_PINNED_VALIDATE_PAGE_SEQUENCE",
        "_PINNED_DERIVE_ROWS",
        "_PINNED_BUILD_REPORT",
    ],
)
def test_every_live_pinned_helper_alias_rebinding_refuses(alias_name):
    original = getattr(pair_module, alias_name)
    setattr(pair_module, alias_name, lambda *args, **kwargs: None)
    try:
        with pytest.raises(AcceptedRiskInputError, match="static contract changed"):
            if alias_name in {
                "_PINNED_DERIVE_ROWS",
                "_PINNED_BUILD_REPORT",
            }:
                build_accepted_risk_input_pair(_capture())
            else:
                build_capture_binding(
                    capture_started_at=STARTED,
                    capture_completed_at=COMPLETED,
                    pages=_capture().pages,
                )
    finally:
        setattr(pair_module, alias_name, original)


def test_capture_authority_detects_nested_page_replacement():
    capture = _capture()
    replacement = dataclasses.replace(capture.pages[0], raw_response_sha256="f" * 64)
    object.__setattr__(capture, "pages", (replacement, *capture.pages[1:]))
    with pytest.raises(AcceptedRiskInputError, match="container topology changed"):
        require_capture_binding(capture)


def test_report_is_exhaustive_and_has_exact_rational_marginal_rates():
    pair = build_accepted_risk_input_pair(
        _capture(
            ratings=[
                _row("included", firm_id="firm-z", ticker="AAA"),
                _row(
                    "censored",
                    firm_id="firm-z",
                    ticker="AAA",
                    last_updated="2020-02-01T00:00:00Z",
                ),
            ],
            earnings=[_row("earnings", action="earnings", ticker="BBB")],
            guidance=[_row("guidance", action="guidance", ticker="CCC")],
        )
    )
    report = pair.report
    assert len(report.disposition_counts) == len(InputView) * len(RowDisposition)
    assert all(
        sum(item.count for item in report.disposition_counts if item.view is view)
        == report.total_row_count
        for view in InputView
    )
    overall = report.breakdowns[0]
    assert overall.dimension is BreakdownDimension.OVERALL
    assert overall.current_inclusion_rate.fraction == Fraction(1, 1)
    assert overall.censored_inclusion_rate.fraction == Fraction(3, 4)
    assert overall.disagreement_rate.fraction == Fraction(1, 4)
    assert {item.dimension for item in report.breakdowns} == set(BreakdownDimension)
    assert any(
        item.dimension is BreakdownDimension.FIRM and item.key == "firm-z"
        for item in report.breakdowns
    )
    assert any(
        item.dimension is BreakdownDimension.SECURITY_LABEL and item.key == "AAA"
        for item in report.breakdowns
    )
    assert any(
        item.dimension is BreakdownDimension.ACTION and item.key == "upgrades"
        for item in report.breakdowns
    )


def test_current_ticker_is_only_a_restated_label_not_an_identity_binding():
    pair = build_accepted_risk_input_pair(_capture())
    assert pair.rows[0].current_restated_security_label == "AAA"
    assert pair.identity_mapping_authenticated is False
    assert pair.security_master_binding is None
    assert pair.report.mapping_disagreement_report is None
    assert pair.report.signal_disagreement_report is None
    assert pair.signal_rows_constructed is False


def test_all_external_capabilities_and_bindings_remain_false_or_null():
    pair = build_accepted_risk_input_pair(_capture())
    false_fields = (
        "guidance_clock_authenticated",
        "identity_mapping_authenticated",
        "rating_mapping_authenticated",
        "signal_rows_constructed",
        "production_input_authority",
        "outcome_gate_open",
        "provider_io_performed",
        "credential_access_performed",
        "filesystem_io_performed",
        "quantconnect_io_performed",
        "object_store_io_performed",
        "market_data_access_performed",
        "outcome_access_performed",
        "deployment_performed",
        "order_access_performed",
        "trading_performed",
    )
    assert all(getattr(pair, name) is False for name in false_fields)
    assert pair.provider_binding is None
    assert pair.security_master_binding is None
    assert pair.outcome_binding is None


def test_capture_chronology_is_strict_and_page_receipts_are_ordered():
    with pytest.raises(AcceptedRiskInputError, match="chronology is reversed"):
        _capture(started=COMPLETED, completed=STARTED)

    pages = (
        _page(
            MassiveSourceRole.ANALYST_RATINGS,
            [_row("r")],
            received_at="2026-09-11T18:03:00.000000Z",
        ),
        _page(
            MassiveSourceRole.EARNINGS,
            [_row("e")],
            received_at="2026-09-11T18:02:00.000000Z",
        ),
        _page(MassiveSourceRole.CORPORATE_GUIDANCE, [_row("g")]),
    )
    with pytest.raises(AcceptedRiskInputError, match="nondecreasing"):
        _capture(pages=pages)


def test_pair_is_deterministic_and_bound_to_every_row_disposition():
    first = build_accepted_risk_input_pair(_capture())
    second = build_accepted_risk_input_pair(_capture())
    assert first.pair_id == second.pair_id
    assert first.pair_sha256 == second.pair_sha256

    changed = build_accepted_risk_input_pair(
        _capture(ratings=[_row("rating-1", last_updated="2020-02-01T00:00:00Z")])
    )
    assert changed.pair_sha256 != first.pair_sha256


def test_module_has_no_external_or_side_effect_capable_imports_or_calls():
    path = Path(pair_module.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden_import_roots = {
        "requests",
        "urllib",
        "httpx",
        "socket",
        "subprocess",
        "quantconnect",
        "lean",
        "execution",
        "broker",
        "outcomes",
    }
    imported_roots = set()
    called_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called_names.add(node.func.attr)
    assert not (imported_roots & forbidden_import_roots)
    assert not (
        called_names
        & {
            "open",
            "read_bytes",
            "read_text",
            "write_bytes",
            "write_text",
            "urlopen",
            "request",
            "post",
            "History",
            "history",
            "MarketOrder",
            "market_order",
        }
    )


def test_exact_enum_and_boolean_types_are_required():
    query = render_redacted_capture_query_bytes(
        source_role=MassiveSourceRole.ANALYST_RATINGS,
        requested_first_event_date=FIRST,
        requested_last_event_date=LAST,
    )
    with pytest.raises(AcceptedRiskInputError, match="MassiveSourceRole"):
        bind_capture_page(
            source_role="analyst_ratings",
            redacted_query_bytes=query,
            page_number=1,
            request_cursor_sha256=None,
            next_cursor_sha256=None,
            terminal_page=True,
            response_received_at=ROLE_TIMES[MassiveSourceRole.ANALYST_RATINGS],
            raw_response_sha256="1" * 64,
            provider_rows_bytes=_rows_bytes([_row("r")]),
        )
    page = _page(MassiveSourceRole.ANALYST_RATINGS, [_row("r")])
    with pytest.raises(CanonicalEvidenceError):
        dataclasses.replace(page, terminal_page=1)


def test_empty_complete_capture_is_represented_but_empty_pair_refuses():
    capture = _capture(ratings=[], earnings=[], guidance=[])
    assert capture.total_row_count == 0
    with pytest.raises(AcceptedRiskInputError, match="cannot be empty"):
        build_accepted_risk_input_pair(capture)
