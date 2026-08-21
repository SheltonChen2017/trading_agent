"""Behavioral and boundary tests for the ACER analyst-event backbone.

Two kinds of test live here. Most are behavioral: they drive the dangerous
directions (silent row loss, look-ahead availability, mutation of caller
data, overwriting an immutable dataset). A few are AST tests, used only for
invariants runtime behavior cannot observe -- specifically that this package
never acquires research or execution authority by importing its way into it.
"""
from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

import pytest

from research.acer.dataset import (
    DatasetConflictError,
    build_identity,
    load_identity,
    summarize,
    write_dataset,
)
from research.acer.normalize import (
    ERA_EASTERN_CONSISTENT_CLOCK,
    ERA_INGESTION_CLOCK,
    REFUSAL_DUPLICATE_ID,
    REFUSAL_INCONSISTENT_TRANSITION,
    REFUSAL_MISSING_DATE,
    REFUSAL_MISSING_FIRM,
    REFUSAL_MISSING_ID,
    REFUSAL_MISSING_LAST_UPDATED,
    REFUSAL_MISSING_RATING,
    REFUSAL_MISSING_TICKER,
    REFUSAL_UPDATE_BEFORE_ACTION,
    normalize_rows,
    parse_last_updated,
)
from research.acer.snapshot import (
    SnapshotError,
    load_verified_rows,
    load_verified_snapshot,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
ACER_PACKAGE = REPO_ROOT / "research" / "acer"


def _row(**overrides) -> dict:
    row = {
        "benzinga_id": "id-1",
        "date": "2024-03-14",
        "time": "14:30:00",
        "last_updated": "2024-03-14T18:31:00Z",
        "ticker": "AAPL",
        "company_name": "Apple Inc",
        "firm": "Example Securities",
        "analyst": "A. Analyst",
        "rating_action": "Upgrades",
        "rating": "Buy",
        "previous_rating": "Neutral",
        "price_target": "230.00",
        "previous_price_target": "200.00",
    }
    row.update(overrides)
    return row


# --------------------------------------------------------------------------
# Availability: the frozen date-level rule
# --------------------------------------------------------------------------


def test_availability_is_the_later_of_action_date_and_update_date():
    """The frozen rule is max(action_date, last_updated UTC date)."""
    same_day, _ = normalize_rows([_row()])
    assert same_day[0].available_date == "2024-03-14"

    restated, _ = normalize_rows(
        [_row(benzinga_id="id-2", last_updated="2025-01-09T12:00:00Z")]
    )
    assert restated[0].available_date == "2025-01-09"
    assert restated[0].action_date == "2024-03-14"


def test_a_late_utc_update_defers_availability_rather_than_rounding_back():
    """A 23:59Z update on the action date still defers to that same date;
    an update just past UTC midnight defers a full day.

    This is the boundary where a timezone shortcut would silently reintroduce
    look-ahead, so it is pinned rather than assumed.
    """
    same, _ = normalize_rows([_row(last_updated="2024-03-14T23:59:59Z")])
    assert same[0].available_date == "2024-03-14"

    next_day, _ = normalize_rows([_row(last_updated="2024-03-15T00:00:01Z")])
    assert next_day[0].available_date == "2024-03-15"


def test_an_update_offset_is_honoured_rather_than_ignored():
    """A non-UTC offset must convert, not be truncated to its local date.

    23:30 at -05:00 is 04:30Z the following day, so availability defers.
    Reading the date off the string would keep it on the action date and
    make the event available a day too early.
    """
    events, _ = normalize_rows([_row(last_updated="2024-03-14T23:30:00-05:00")])
    assert events[0].last_updated_date_utc == "2024-03-15"
    assert events[0].available_date == "2024-03-15"


def test_no_utc_action_timestamp_is_derived_from_the_vendor_time_field():
    """The frozen rule is date-level, so the module must not emit an instant.

    A derived `action_ts_utc` would rest on the Eastern reading of `time`,
    which is measured but not vendor-confirmed. Its absence is the contract.
    """
    events, _ = normalize_rows([_row()])
    payload = events[0].to_payload()
    assert "action_ts_utc" not in payload
    assert payload["action_time_raw"] == "14:30:00"
    assert set(payload) & {"available_at_utc", "action_timestamp_utc"} == set()


def test_time_field_era_is_recorded_by_action_year_including_the_mixed_year():
    """2016 groups with the unreliable era: a mixed year is not reliable."""
    rows = [
        _row(benzinga_id="old", date="2015-06-01", last_updated="2015-06-01T10:00:00Z"),
        _row(benzinga_id="mix", date="2016-06-01", last_updated="2016-06-01T10:00:00Z"),
        _row(benzinga_id="new", date="2017-06-01", last_updated="2017-06-01T10:00:00Z"),
    ]
    events, refusals = normalize_rows(rows)
    assert not refusals
    eras = {event.benzinga_id: event.time_field_era for event in events}
    assert eras == {
        "old": ERA_INGESTION_CLOCK,
        "mix": ERA_INGESTION_CLOCK,
        "new": ERA_EASTERN_CONSISTENT_CLOCK,
    }


# --------------------------------------------------------------------------
# Refusals: no row is ever silently dropped
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides, expected_reason",
    [
        ({"benzinga_id": ""}, REFUSAL_MISSING_ID),
        ({"benzinga_id": None}, REFUSAL_MISSING_ID),
        ({"date": "not-a-date"}, REFUSAL_MISSING_DATE),
        ({"date": "2024-02-31"}, REFUSAL_MISSING_DATE),
        ({"rating": ""}, REFUSAL_MISSING_RATING),
        ({"firm": None}, REFUSAL_MISSING_FIRM),
        ({"ticker": ""}, REFUSAL_MISSING_TICKER),
        ({"last_updated": ""}, REFUSAL_MISSING_LAST_UPDATED),
        ({"last_updated": "03/14/2024 18:31:00"}, REFUSAL_MISSING_LAST_UPDATED),
        ({"last_updated": "2024-03-14T18:31:00"}, REFUSAL_MISSING_LAST_UPDATED),
    ],
)
def test_every_unusable_row_becomes_a_named_refusal(overrides, expected_reason):
    events, refusals = normalize_rows([_row(**overrides)])
    assert events == []
    assert [refusal.reason for refusal in refusals] == [expected_reason]


def test_a_naive_last_updated_is_malformed_rather_than_assumed_utc():
    """Assuming a timezone is the unsafe direction for an availability bound."""
    assert parse_last_updated("2024-03-14T18:31:00") is None
    assert parse_last_updated("2024-03-14T18:31:00Z") is not None


def test_an_update_preceding_the_action_date_is_refused():
    """Snapshot A's 39 reverse-order rows: the vendor's own fields disagree.

    Taking max() would quietly hand these rows the action date as their
    availability, which is precisely the unverifiable timestamp the audit
    refused to trade on.
    """
    events, refusals = normalize_rows(
        [_row(date="2023-08-09", last_updated="2023-08-08T18:17:51Z")]
    )
    assert events == []
    assert refusals[0].reason == REFUSAL_UPDATE_BEFORE_ACTION


def test_a_directional_action_whose_rating_did_not_change_is_refused():
    events, refusals = normalize_rows(
        [_row(rating_action="Downgrades", previous_rating="Buy", rating="Buy")]
    )
    assert events == []
    assert refusals[0].reason == REFUSAL_INCONSISTENT_TRANSITION


def test_directional_no_change_ignores_case_and_presentation_whitespace():
    """Vendor presentation differences cannot manufacture a transition."""
    events, refusals = normalize_rows(
        [
            _row(
                rating_action="  DOWNGRADES ",
                previous_rating="  Sector   Perform ",
                rating="sector perform",
            )
        ]
    )
    assert events == []
    assert refusals[0].reason == REFUSAL_INCONSISTENT_TRANSITION


def test_transition_comparison_does_not_guess_punctuation_aliases():
    """Firm-specific aliases belong to ACER-0, not this plumbing layer."""
    events, refusals = normalize_rows(
        [_row(rating_action="Upgrades", previous_rating="Buy", rating="Buy+")]
    )
    assert not refusals
    assert events[0].previous_rating_raw == "Buy"
    assert events[0].rating_raw == "Buy+"


def test_a_maintained_rating_with_no_change_is_kept_not_refused():
    """Only upgrades/downgrades must actually move; maintains legitimately
    repeat the same rating, and 205,516 Snapshot A rows do exactly that."""
    events, refusals = normalize_rows(
        [_row(rating_action="Maintains", previous_rating="Buy", rating="Buy")]
    )
    assert refusals == []
    assert events[0].rating_raw == "Buy"


def test_an_initiation_without_a_previous_rating_is_kept():
    """44% of Snapshot A lacks previous_rating; that is structural, not a defect."""
    events, refusals = normalize_rows(
        [_row(rating_action="Initiates Coverage On", previous_rating=None)]
    )
    assert refusals == []
    assert events[0].previous_rating_raw is None


def test_a_repeated_identity_is_refused_even_when_the_first_row_was_refused():
    """A duplicated identity key breaks restatement measurement outright.

    Tracking only accepted ids would let a second row quietly occupy the
    slot of a refused first one, hiding the duplication entirely.
    """
    rows = [_row(benzinga_id="dup", rating=""), _row(benzinga_id="dup")]
    events, refusals = normalize_rows(rows)
    assert events == []
    assert [refusal.reason for refusal in refusals] == [
        REFUSAL_DUPLICATE_ID,
        REFUSAL_DUPLICATE_ID,
    ]


def test_every_occurrence_of_an_accepted_first_duplicate_is_refused():
    """Keeping the first row would silently choose an arbitrary authority."""
    rows = [
        _row(benzinga_id="dup", rating="Buy"),
        _row(benzinga_id="dup", rating="Sell"),
    ]
    events, refusals = normalize_rows(rows)
    assert events == []
    assert [refusal.reason for refusal in refusals] == [
        REFUSAL_DUPLICATE_ID,
        REFUSAL_DUPLICATE_ID,
    ]


def test_no_input_row_is_lost_between_events_and_refusals():
    rows = [
        _row(benzinga_id="a"),
        _row(benzinga_id="b", rating=""),
        _row(benzinga_id="c", date="bad"),
        _row(benzinga_id="d"),
    ]
    events, refusals = normalize_rows(rows)
    assert len(events) + len(refusals) == len(rows)


# --------------------------------------------------------------------------
# Contract hygiene
# --------------------------------------------------------------------------


def test_caller_rows_are_never_mutated():
    rows = [_row(), _row(benzinga_id="id-2", rating="")]
    before = copy.deepcopy(rows)
    normalize_rows(rows)
    assert rows == before


def test_output_order_is_deterministic_regardless_of_input_order():
    rows = [
        _row(benzinga_id="z", date="2024-01-02", last_updated="2024-01-02T10:00:00Z"),
        _row(benzinga_id="a", date="2024-01-02", last_updated="2024-01-02T10:00:00Z"),
        _row(benzinga_id="m", date="2024-01-01", last_updated="2024-01-01T10:00:00Z"),
    ]
    forward, _ = normalize_rows(rows)
    backward, _ = normalize_rows(list(reversed(rows)))
    assert [event.benzinga_id for event in forward] == ["m", "a", "z"]
    assert [event.benzinga_id for event in backward] == [event.benzinga_id for event in forward]


def test_rating_vocabulary_is_preserved_unmapped():
    """Scale mapping is an ACER-0 decision; this layer must not pre-empt it."""
    events, _ = normalize_rows([_row(rating="Sector Outperform", previous_rating="Mkt Perform")])
    assert events[0].rating_raw == "Sector Outperform"
    assert events[0].previous_rating_raw == "Mkt Perform"


def test_price_targets_stay_text_so_no_float_arithmetic_can_creep_in():
    events, _ = normalize_rows([_row(price_target="230.00", previous_price_target="200.00")])
    assert events[0].price_target_raw == "230.00"
    assert isinstance(events[0].price_target_raw, str)


def test_events_are_frozen_against_post_construction_mutation():
    events, _ = normalize_rows([_row()])
    with pytest.raises(Exception):
        events[0].available_date = "2030-01-01"  # type: ignore[misc]


# --------------------------------------------------------------------------
# Dataset identity and immutability
# --------------------------------------------------------------------------


def test_dataset_identity_changes_when_refusals_change(tmp_path):
    """A build that started discarding rows must not look identical."""
    events, refusals = normalize_rows([_row(), _row(benzinga_id="b")])
    identity_a, _, _ = build_identity(
        events, refusals, source_snapshot_name="s", source_manifest_sha256="0" * 64
    )
    identity_b, _, _ = build_identity(
        events,
        [*refusals, *normalize_rows([_row(benzinga_id="c", rating="")])[1]],
        source_snapshot_name="s",
        source_manifest_sha256="0" * 64,
    )
    assert identity_a["content_hash"] != identity_b["content_hash"]
    assert identity_a["dataset_id"] != identity_b["dataset_id"]


def test_dataset_identity_changes_with_source_lineage():
    events, refusals = normalize_rows([_row()])
    first, _, _ = build_identity(
        events, refusals, source_snapshot_name="a", source_manifest_sha256="0" * 64
    )
    second, _, _ = build_identity(
        events, refusals, source_snapshot_name="a", source_manifest_sha256="1" * 64
    )
    assert first["content_hash"] != second["content_hash"]


def test_dataset_identity_is_canonical_under_caller_order():
    events, refusals = normalize_rows(
        [_row(benzinga_id="a"), _row(benzinga_id="b", rating="")]
    )
    forward = build_identity(
        events,
        refusals,
        source_snapshot_name="snap",
        source_manifest_sha256="0" * 64,
    )
    backward = build_identity(
        list(reversed(events)),
        list(reversed(refusals)),
        source_snapshot_name="snap",
        source_manifest_sha256="0" * 64,
    )
    assert forward == backward


def test_dataset_identity_refuses_duplicate_event_ids():
    events, refusals = normalize_rows([_row()])
    with pytest.raises(DatasetConflictError, match="duplicate benzinga_id"):
        build_identity(
            [events[0], events[0]],
            refusals,
            source_snapshot_name="snap",
            source_manifest_sha256="0" * 64,
        )


@pytest.mark.parametrize(
    "source_name, source_hash",
    [("", "0" * 64), ("snap", "not-a-sha256")],
)
def test_dataset_identity_refuses_malformed_source_lineage(source_name, source_hash):
    events, refusals = normalize_rows([_row()])
    with pytest.raises(DatasetConflictError, match="REFUSED"):
        build_identity(
            events,
            refusals,
            source_snapshot_name=source_name,
            source_manifest_sha256=source_hash,
        )


def test_writing_the_same_dataset_twice_is_idempotent(tmp_path):
    events, refusals = normalize_rows([_row()])
    kwargs = {
        "source_snapshot_name": "snap",
        "source_manifest_sha256": "0" * 64,
    }
    first = write_dataset(events, refusals, tmp_path, **kwargs)
    second = write_dataset(events, refusals, tmp_path, **kwargs)
    assert first == second
    assert load_identity(tmp_path / first["dataset_id"]) == first


def test_a_tampered_dataset_file_refuses_to_load(tmp_path):
    events, refusals = normalize_rows([_row()])
    identity = write_dataset(
        events,
        refusals,
        tmp_path,
        source_snapshot_name="snap",
        source_manifest_sha256="0" * 64,
    )
    target = tmp_path / identity["dataset_id"] / "events.jsonl"
    target.write_bytes(target.read_bytes() + b"{}\n")
    with pytest.raises(DatasetConflictError, match="does not match"):
        load_identity(tmp_path / identity["dataset_id"])


@pytest.mark.parametrize(
    "field, forged",
    [
        ("source_manifest_sha256", "f" * 64),
        ("event_count", 999),
        ("dataset_id", "acer-analyst-events-forged"),
        ("contract_version", 999),
    ],
)
def test_tampered_dataset_identity_metadata_refuses_to_load(tmp_path, field, forged):
    events, refusals = normalize_rows([_row()])
    identity = write_dataset(
        events,
        refusals,
        tmp_path,
        source_snapshot_name="snap",
        source_manifest_sha256="0" * 64,
    )
    target = tmp_path / identity["dataset_id"] / "dataset.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload[field] = forged
    target.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DatasetConflictError, match="REFUSED"):
        load_identity(tmp_path / identity["dataset_id"])


def test_a_dataset_path_holding_different_bytes_refuses_rather_than_overwrites(tmp_path):
    events, refusals = normalize_rows([_row()])
    identity, _, _ = build_identity(
        events, refusals, source_snapshot_name="snap", source_manifest_sha256="0" * 64
    )
    squatted = tmp_path / identity["dataset_id"]
    squatted.mkdir(parents=True)
    (squatted / "events.jsonl").write_bytes(b"not the real events\n")
    with pytest.raises(DatasetConflictError, match="REFUSED"):
        write_dataset(
            events,
            refusals,
            tmp_path,
            source_snapshot_name="snap",
            source_manifest_sha256="0" * 64,
        )
    assert (squatted / "events.jsonl").read_bytes() == b"not the real events\n"


def test_events_are_written_as_one_canonical_json_object_per_line(tmp_path):
    events, refusals = normalize_rows([_row(), _row(benzinga_id="b")])
    identity = write_dataset(
        events,
        refusals,
        tmp_path,
        source_snapshot_name="snap",
        source_manifest_sha256="0" * 64,
    )
    lines = (
        (tmp_path / identity["dataset_id"] / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert len(lines) == 2
    assert json.loads(lines[0])["benzinga_id"] == "b"


# --------------------------------------------------------------------------
# Coverage summary
# --------------------------------------------------------------------------


def test_summary_counts_refusals_and_deferred_availability():
    rows = [
        _row(benzinga_id="a"),
        _row(benzinga_id="b", last_updated="2025-06-01T00:00:00Z"),
        _row(benzinga_id="c", rating=""),
    ]
    events, refusals = normalize_rows(rows)
    report = summarize(events, refusals)
    assert report["input_rows"] == 3
    assert report["event_count"] == 2
    assert report["refusal_count"] == 1
    assert report["availability_deferred_beyond_action_date"] == 1
    assert report["refusals_by_reason"] == {REFUSAL_MISSING_RATING: 1}
    assert report["events_by_action_year"] == {"2024": 2}


def test_summary_of_an_empty_input_does_not_divide_by_zero():
    assert summarize([], [])["retention_rate"] == 0.0


# --------------------------------------------------------------------------
# Snapshot verification is shared, not re-implemented
# --------------------------------------------------------------------------


def test_the_backbone_refuses_the_same_snapshots_the_audit_refuses(tmp_path):
    """Consolidation guard: one authoritative verification rule, not two."""
    import scripts.audit_benzinga_ratings as audit

    snap = tmp_path / "snap"
    (snap / "raw").mkdir(parents=True)
    (snap / "manifest.json").write_bytes(b'{"complete": true, "partitions": []}')
    (snap / "manifest.sha256").write_text("0" * 64 + "\n", encoding="utf-8")

    with pytest.raises(SnapshotError, match="manifest hash mismatch"):
        load_verified_rows(snap)
    with pytest.raises(SystemExit, match="manifest hash mismatch"):
        audit._load_rows(snap, False)


def test_verified_rows_and_lineage_hash_come_from_one_manifest_read(
    tmp_path, monkeypatch
):
    """Rows from manifest A must never be labelled with manifest B's hash."""
    import research.acer.snapshot as snapshot

    calls = []

    def fake_load(_snap):
        calls.append(True)
        return {"complete": True, "partitions": []}, "a" * 64

    monkeypatch.setattr(snapshot, "_load_manifest_and_hash", fake_load)
    rows, manifest_hash = load_verified_snapshot(tmp_path)
    assert rows == []
    assert manifest_hash == "a" * 64
    assert len(calls) == 1


def test_an_incomplete_snapshot_cannot_publish_a_canonical_dataset(tmp_path):
    """The audit override is diagnostic; canonical persistence stays complete."""
    from scripts.build_acer_events import main

    with pytest.raises(SystemExit, match="incomplete snapshot.*only.*dry-run"):
        main([str(tmp_path / "not-read"), "--allow-incomplete"])


# --------------------------------------------------------------------------
# Boundary invariants (AST: not observable at runtime)
# --------------------------------------------------------------------------


_FORBIDDEN_IMPORT_ROOTS = {
    "assistant",  # proposal and execution authority
    "execution",
    "risk",
    "backtest",  # return/outcome computation
    "signals",
    "strategies",
    "yfinance",  # any direct market-data pull
}


def test_the_acer_package_never_imports_authority_or_outcome_code():
    """ACER-1 is data plumbing. Joining events to outcomes is a research
    look that requires an ACER-0 freeze, and no research artifact may hold
    execution authority (CLAUDE.md section 4)."""
    offenders: list[str] = []
    for path in ACER_PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name.split(".")[0] in _FORBIDDEN_IMPORT_ROOTS:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {name}")
    assert not offenders, offenders


def test_the_acer_package_makes_no_network_call():
    """The backbone reads a frozen snapshot. A vendor call here would mean a
    past result could change under a restatement (plan section 4.1)."""
    offenders: list[str] = []
    for path in ACER_PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name.split(".")[0] in {"requests", "urllib", "http", "socket"}:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {name}")
    assert not offenders, offenders


def test_no_rating_scale_mapping_is_hard_coded_in_the_backbone():
    """A numeric rating scale is an ACER-0 specification decision.

    This catches the specific way it would sneak in: a module-level literal
    mapping rating vocabulary to numbers, added 'just to get started'.
    """
    offenders: list[str] = []
    vocabulary = {"buy", "sell", "hold", "outperform", "underperform", "neutral"}
    for path in ACER_PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = [
                key.value.strip().lower()
                for key in node.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            ]
            values_are_numeric = node.values and all(
                isinstance(value, ast.Constant)
                and isinstance(value.value, (int, float))
                and not isinstance(value.value, bool)
                for value in node.values
            )
            if values_are_numeric and vocabulary & set(keys):
                offenders.append(
                    f"{path.relative_to(REPO_ROOT)}:{node.lineno}: rating scale literal"
                )
    assert not offenders, offenders
