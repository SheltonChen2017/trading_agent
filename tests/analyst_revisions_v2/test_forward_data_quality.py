"""Forward receipt preparation uses authenticated offline captures, not QC."""
from __future__ import annotations

import ast
import dataclasses
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from research.analyst_revisions_v2 import forward_data_quality as subject
from research.analyst_revisions_v2.canonical import canonical_json_bytes, sha256_bytes
from scripts import capture_arv2_massive as capture
from scripts import run_arv2_forward_data_quality as cli
from tests.analyst_revisions_v2 import test_massive_capture_adapter as offline


FIRST = "2021-01-01"
LAST = "2021-01-07"


def _row(identity, role, *, target=None, date="2021-01-04"):
    row = offline._row(identity, role=role)
    row["date"] = date
    row["ticker"] = "PRIVATE-DO-NOT-PUBLISH"
    if target is not None:
        row["price_target"] = target
    return row


def _capture(tmp_path, *, newer=False, date=FIRST, duplicate=False):
    roles = capture.ROLE_ORDER
    ratings = (
        [_row("same-rating", roles[0], target=126), _row("new-rating", roles[0])]
        if newer else
        [_row("same-rating", roles[0], target=125), _row("old-rating", roles[0])]
    )
    if duplicate:
        ratings.append(_row("same-rating", roles[0], target=127))
    ratings[0]["date"] = date
    all_rows = [ratings, [_row("same-earnings", roles[1])], [_row("same-guidance", roles[2])]]
    responses = [
        offline.FakeResponse(offline._payload(rows), offline._endpoint(role))
        for role, rows in zip(roles, all_rows, strict=True)
    ]
    clock = datetime(2026, 9, 27, tzinfo=timezone.utc) + timedelta(days=newer)
    loaded = capture._capture_massive_history_spooled_for_test(
        requested_first_event_date=FIRST,
        requested_last_event_date=LAST,
        artifact_root=tmp_path / ("new" if newer else "old"),
        session=offline.FakeSession(responses),
        clock=lambda: clock,
        api_key=offline.KEY,
    )
    return loaded


def _receipt(source):
    return cli.build_receipt(
        source.artifact_path, source.manifest_sha256,
        first_event_date=FIRST, last_event_date=LAST,
        expected_transport=capture.TEST_TRANSPORT,
    )


def test_two_authenticated_captures_observe_same_id_changed_version_without_claiming_vendor_revision(tmp_path):
    before = _receipt(_capture(tmp_path))
    after = _receipt(_capture(tmp_path, newer=True))
    report = subject.compare_receipts(*before, *after)
    rating = report["roles"][capture.ROLE_ORDER[0].value]
    assert rating == {
        "same_id_same_version": 0,
        "same_id_different_version_between_receipts": 1,
        "same_id_ambiguous_multiple_versions": 0,
        "old_only_id_cause_unknown": 1,
        "new_only_id_cause_unknown": 1,
    }
    assert all(report["roles"][role.value]["same_id_same_version"] == 1
               for role in capture.ROLE_ORDER[1:])
    assert report["purpose"] == subject.PURPOSE
    assert report["point_in_time_proven"] is report["paper_look_committed"] is False
    assert report["return_looks"] == 0
    assert b"PRIVATE-DO-NOT-PUBLISH" not in before[0] + after[0]
    assert b"same-rating" not in before[0] + after[0]
    assert b"price_target" not in before[0] + after[0]
    assert before[1] == sha256_bytes(before[0])


def test_multiple_versions_of_one_id_in_a_capture_remain_ambiguous(tmp_path):
    before = _receipt(_capture(tmp_path))
    after = _receipt(_capture(tmp_path, newer=True, duplicate=True))
    rating = subject.compare_receipts(*before, *after)["roles"][
        capture.ROLE_ORDER[0].value
    ]
    assert rating["same_id_different_version_between_receipts"] == 0
    assert rating["same_id_ambiguous_multiple_versions"] == 1


@pytest.mark.parametrize("kind", ("manifest_pin", "page_bytes", "wrong_window", "outside_row"))
def test_capture_is_authenticated_and_exact_window_is_required(tmp_path, kind):
    source = _capture(tmp_path, date="2021-01-08" if kind == "outside_row" else FIRST)
    if kind == "page_bytes":
        manifest = json.loads((source.artifact_path / "manifest.json").read_bytes())
        page = source.artifact_path / manifest["pages"][0]["provider_rows_file"]
        page.write_bytes(page.read_bytes().replace(b"PRIVATE-DO-NOT-PUBLISH", b"PRIVATE-NOT-THE-SAME", 1))
    with pytest.raises(ValueError):
        cli.build_receipt(
            source.artifact_path,
            "0" * 64 if kind == "manifest_pin" else source.manifest_sha256,
            first_event_date="2021-01-02" if kind == "wrong_window" else FIRST,
            last_event_date=LAST,
            expected_transport=capture.TEST_TRANSPORT,
        )


@pytest.mark.parametrize("kind", ("content", "paper_claim", "order", "window", "same"))
def test_comparison_rejects_tampered_or_nonmatching_receipts(tmp_path, kind):
    before = _receipt(_capture(tmp_path))
    after = _receipt(_capture(tmp_path, newer=True))
    if kind == "content":
        after = (after[0].replace(b"development_data_quality", b"development_data_QUALity"), after[1])
    elif kind == "paper_claim":
        changed = json.loads(after[0])
        changed["paper_look_committed"] = True
        after = (canonical_json_bytes(changed), sha256_bytes(canonical_json_bytes(changed)))
    elif kind == "order":
        before, after = after, before
    elif kind == "window":
        changed = json.loads(after[0])
        changed["first_event_date"] = "2021-01-02"
        after = (canonical_json_bytes(changed), sha256_bytes(canonical_json_bytes(changed)))
    else:
        after = before
    with pytest.raises(ValueError):
        subject.compare_receipts(*before, *after)


def test_receipt_publication_is_private_content_addressed_and_write_once(tmp_path, monkeypatch):
    receipt = _receipt(_capture(tmp_path))
    allowed = tmp_path / "allowed"
    monkeypatch.setattr(capture, "REPOSITORY_ARTIFACTS_ROOT", allowed)
    path = cli.publish_receipt(*receipt, allowed / "forward")
    assert path.name == f"forward-quality-{receipt[1]}.json"
    assert path.read_bytes() == receipt[0]
    with pytest.raises(capture.MassiveCaptureError, match="overwrite refused"):
        cli.publish_receipt(*receipt, allowed / "forward")


def test_module_has_no_outcome_order_deployment_or_provider_call_imports():
    tree = ast.parse(Path(subject.__file__).read_text(encoding="utf-8"))
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    imports += [name.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                for name in node.names]
    assert not any(name.startswith(("backtest", "execution", "broker", "quantconnect"))
                   for name in imports if name)
    assert not any(name == "os" or name.startswith("scripts") for name in imports if name)
    assert not any(getattr(node, "attr", None) == "capture_massive_history"
                   for node in ast.walk(tree))


def test_pure_receipt_contract_matches_host_capture_role_and_transport_pins():
    assert subject.ROLE_ORDER == capture.ROLE_ORDER
    assert subject.PRODUCTION_TRANSPORT == capture.PRODUCTION_TRANSPORT
    assert subject.TEST_TRANSPORT == capture.TEST_TRANSPORT


@pytest.mark.parametrize("field, claim", (
    ("point_in_time_proven", True),
    ("paper_look_committed", True),
    ("outcome_reads", 1),
    ("qc_calls", 1),
))
def test_receipt_cannot_claim_more_than_development_authority(tmp_path, field, claim):
    """A correctly pinned receipt that claims point-in-time proof, a paper
    look, an outcome read, or a QC call is refused before any comparison."""

    before = _receipt(_capture(tmp_path))
    after = _receipt(_capture(tmp_path, newer=True))
    changed = json.loads(after[0])
    changed[field] = claim
    payload = canonical_json_bytes(changed)
    with pytest.raises(subject.ForwardDataQualityError, match="authority"):
        subject.compare_receipts(*before, payload, sha256_bytes(payload))


def test_core_refuses_a_host_traversal_that_reports_another_transport(tmp_path):
    """The pure core rechecks the transport that the host traversal reports;
    a test-transport capture relabelled as production yields no receipt."""

    source = _capture(tmp_path)

    def relabelled(visit_page):
        summary = capture._visit_authenticated_massive_capture_pages_for_bridge(
            source.artifact_path,
            expected_transport=capture.TEST_TRANSPORT,
            visit_page=visit_page,
        )
        return dataclasses.replace(summary, capture_transport=capture.PRODUCTION_TRANSPORT)

    with pytest.raises(subject.ForwardDataQualityError, match="transport"):
        subject.build_receipt_from_authenticated_pages(
            relabelled,
            source.manifest_sha256,
            first_event_date=FIRST,
            last_event_date=LAST,
            expected_transport=capture.TEST_TRANSPORT,
        )
