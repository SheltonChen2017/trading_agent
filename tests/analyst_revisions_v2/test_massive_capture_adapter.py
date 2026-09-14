"""Offline success and refusal tests for the ARV2 Massive capture adapter."""
from __future__ import annotations

import dataclasses
import gc
import inspect
import json
import os
import re
import stat
import weakref
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

from research.analyst_revisions_v2.accepted_risk_input_pair import (
    MassiveSourceRole,
    RowDisposition,
    require_capture_binding,
)
from research.analyst_revisions_v2.canonical import canonical_json_bytes, sha256_bytes
from scripts.capture_arv2_massive import (
    BASE_URL,
    ENDPOINT_PATHS,
    PRODUCTION_TRANSPORT,
    ROLE_ORDER,
    TEST_TRANSPORT,
    MassiveCaptureError,
    SpooledMassiveCapture,
    _capture_massive_history_for_test,
    _capture_massive_history_spooled_for_test,
    _redact_url,
    capture_massive_history,
    load_massive_capture_artifact,
)
from scripts.build_arv2_massive_input_pair import (
    MAX_BRIDGE_SOURCE_PAYLOAD_PEAK_BYTES,
    MassiveAcceptedRiskBridge,
    MassiveInputPairBridgeError,
    _build_massive_accepted_risk_input_pair_for_test,
    build_massive_accepted_risk_input_pair,
    require_massive_accepted_risk_bridge,
)


KEY = "offline-test-key-NEVER-REAL"
FIRST_DATE = "2021-01-01"
LAST_DATE = "2021-12-31"
NOW = datetime(2026, 9, 12, 12, 34, 56, 123456, tzinfo=timezone.utc)


class FakeResponse:
    def __init__(self, content: bytes, url: str, status_code: int = 200) -> None:
        self.content = content
        self.url = url
        self.status_code = status_code
        self.request: object | None = None
        self.close_count = 0

    def iter_content(self, *, chunk_size: int):
        for offset in range(0, len(self.content), chunk_size):
            yield self.content[offset : offset + chunk_size]

    def close(self) -> None:
        self.close_count += 1


class FakeSession:
    def __init__(
        self,
        responses: list[FakeResponse] | None = None,
        *,
        failure: BaseException | None = None,
    ) -> None:
        self.headers: dict[str, str] = {}
        self.responses = list(responses or [])
        self.failure = failure
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.served: list[FakeResponse] = []
        self.close_count = 0

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append((url, dict(kwargs)))
        if self.failure is not None:
            raise self.failure
        if not self.responses:
            raise AssertionError("fake session received an unexpected request")
        response = self.responses.pop(0)
        params = kwargs.get("params")
        prepared_url = url
        if isinstance(params, dict):
            prepared_url += ("&" if "?" in prepared_url else "?") + urlencode(params)
        response.request = SimpleNamespace(method="GET", url=prepared_url)
        if response.url == url:
            response.url = prepared_url
        self.served.append(response)
        return response

    def close(self) -> None:
        self.close_count += 1


def _endpoint(role: MassiveSourceRole) -> str:
    return BASE_URL + ENDPOINT_PATHS[role]


def _payload(rows: list[dict[str, object]], next_url: str | None = None) -> bytes:
    value: dict[str, object] = {"results": rows, "status": "OK"}
    if next_url is not None:
        value["next_url"] = next_url
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _row(identifier: str, *, role: MassiveSourceRole) -> dict[str, object]:
    common: dict[str, object] = {
        "benzinga_id": identifier,
        "date": "2021-01-04",
        "time": "08:30:00",
        "ticker": "AAPL",
    }
    if role is MassiveSourceRole.CORPORATE_GUIDANCE:
        common["last_updated"] = "2021-01-04 09:30:00"
        common["guidance_type"] = "Revenue"
    else:
        common["last_updated"] = "2021-01-04T13:30:00Z"
    if role is MassiveSourceRole.ANALYST_RATINGS:
        common.update(
            {
                "benzinga_firm_id": "firm-1",
                "rating_action": "Maintains",
                "price_target": 125,
            }
        )
    return common


def _success_responses(*, all_empty: bool = False) -> list[FakeResponse]:
    ratings_cursor = _endpoint(MassiveSourceRole.ANALYST_RATINGS) + "?cursor=ratings-2"
    ratings_one = [] if all_empty else [_row("rating-1", role=ROLE_ORDER[0])]
    ratings_two = [] if all_empty else [_row("rating-2", role=ROLE_ORDER[0])]
    earnings = [] if all_empty else [_row("earnings-1", role=ROLE_ORDER[1])]
    guidance = [] if all_empty else [_row("guidance-1", role=ROLE_ORDER[2])]
    if all_empty:
        return [
            FakeResponse(_payload([]), _endpoint(role)) for role in ROLE_ORDER
        ]
    return [
        FakeResponse(
            _payload(ratings_one, ratings_cursor),
            _endpoint(MassiveSourceRole.ANALYST_RATINGS),
        ),
        FakeResponse(_payload(ratings_two), ratings_cursor),
        FakeResponse(
            _payload(earnings), _endpoint(MassiveSourceRole.EARNINGS)
        ),
        FakeResponse(
            _payload(guidance), _endpoint(MassiveSourceRole.CORPORATE_GUIDANCE)
        ),
    ]


def _capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    responses: list[FakeResponse] | None = None,
    session: FakeSession | None = None,
    build_input_pair: bool = False,
    page_limit: int = 50_000,
):
    fake = session or FakeSession(responses or _success_responses())
    loaded = _capture_massive_history_for_test(
        requested_first_event_date=FIRST_DATE,
        requested_last_event_date=LAST_DATE,
        artifact_root=tmp_path / "captures",
        page_limit=page_limit,
        session=fake,
        clock=lambda: NOW,
        api_key=KEY,
        build_input_pair=build_input_pair,
    )
    return loaded, fake


def _spooled_capture(
    tmp_path: Path,
    *,
    responses: list[FakeResponse] | None = None,
    session: FakeSession | None = None,
    page_limit: int = 50_000,
):
    fake = session or FakeSession(responses or _success_responses())
    loaded = _capture_massive_history_spooled_for_test(
        requested_first_event_date=FIRST_DATE,
        requested_last_event_date=LAST_DATE,
        artifact_root=tmp_path / "spooled-captures",
        page_limit=page_limit,
        session=fake,
        clock=lambda: NOW,
        api_key=KEY,
    )
    return loaded, fake


def _rewrite_manifest(path: Path, mutate) -> None:
    manifest_path = path / "manifest.json"
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutate(value)
    payload = canonical_json_bytes(value)
    manifest_path.write_bytes(payload)
    (path / "manifest.sha256").write_bytes(
        (sha256_bytes(payload) + "\n").encode("ascii")
    )


def _exact_error(message: str) -> str:
    return f"^{re.escape(message)}$"


def test_v2_spooling_persists_each_page_before_the_next_request(
    tmp_path, monkeypatch
):
    import scripts.capture_arv2_massive as module

    capture_root = tmp_path / "spooled-captures"
    inventories_before_request: list[tuple[str, ...]] = []
    checkpoint_count = 0
    original_sync = module._fsync_fd

    def observe_sync(descriptor: int, name: str) -> None:
        nonlocal checkpoint_count
        original_sync(descriptor, name)
        if name == "capture pages checkpoint":
            checkpoint_count += 1

    monkeypatch.setattr(module, "_fsync_fd", observe_sync)

    class PersistenceObservingSession(FakeSession):
        def get(self, url: str, **kwargs: object) -> FakeResponse:
            if self.calls:
                assert checkpoint_count == len(self.calls)
                staging = list(capture_root.glob(".*.incomplete"))
                assert len(staging) == 1
                pages = staging[0] / "pages"
                inventories_before_request.append(
                    tuple(sorted(path.name for path in pages.iterdir()))
                )
            return super().get(url, **kwargs)

    session = PersistenceObservingSession(_success_responses())
    loaded, _ = _spooled_capture(tmp_path, session=session)

    assert type(loaded) is SpooledMassiveCapture
    assert not hasattr(loaded, "capture")
    assert inventories_before_request[0] == (
        "01-analyst_ratings-page-000001.raw.json",
        "01-analyst_ratings-page-000001.rows.jsonl",
    )
    assert len(inventories_before_request) == 3
    manifest_bytes = (loaded.artifact_path / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    assert manifest["page_spooled_before_next_request"] is True
    assert manifest["full_capture_retained_in_memory"] is False
    assert manifest["stored_capture_byte_limit"] == 8 * 1024 * 1024 * 1024
    assert (
        manifest["raw_response_total_byte_count"]
        + manifest["provider_rows_total_byte_count"]
        + len(manifest_bytes)
        + 65
        <= manifest["stored_capture_byte_limit"]
    )
    assert list(capture_root.iterdir()) == [loaded.artifact_path]


def test_v2_spooling_releases_the_prior_bound_page_before_next_request(
    tmp_path, monkeypatch
):
    import scripts.capture_arv2_massive as module

    original_bind = module.bind_capture_page
    prior_page: weakref.ReferenceType[object] | None = None

    def remember_bound_page(**kwargs):
        nonlocal prior_page
        page = original_bind(**kwargs)
        prior_page = weakref.ref(page)
        return page

    class PageLifetimeObservingSession(FakeSession):
        def get(self, url: str, **kwargs: object) -> FakeResponse:
            if self.calls:
                gc.collect()
                assert prior_page is not None
                assert prior_page() is None
            return super().get(url, **kwargs)

    monkeypatch.setattr(module, "bind_capture_page", remember_bound_page)
    _spooled_capture(
        tmp_path,
        session=PageLifetimeObservingSession(_success_responses()),
    )


def test_v2_spooling_preserves_legacy_oracle_logical_capture_identity(
    tmp_path, monkeypatch
):
    oracle, _ = _capture(tmp_path / "oracle", monkeypatch)
    spooled, _ = _spooled_capture(tmp_path / "spooled")

    assert spooled.capture_id == oracle.capture.capture_id
    assert spooled.capture_sha256 == oracle.capture.capture_sha256
    assert spooled.total_page_count == oracle.capture.total_page_count
    assert spooled.total_row_count == oracle.capture.total_row_count
    assert spooled.role_row_counts == oracle.capture.role_row_counts
    oracle_manifest = json.loads(
        (oracle.artifact_path / "manifest.json").read_bytes()
    )
    spooled_manifest = json.loads(
        (spooled.artifact_path / "manifest.json").read_bytes()
    )
    assert spooled_manifest["pages"] == oracle_manifest["pages"]
    assert spooled_manifest["role_counts"] == oracle_manifest["role_counts"]
    assert oracle_manifest["page_spooled_before_next_request"] is False
    assert oracle_manifest["full_capture_retained_in_memory"] is True
    assert spooled_manifest["page_spooled_before_next_request"] is True
    assert spooled_manifest["full_capture_retained_in_memory"] is False
    reloaded = load_massive_capture_artifact(spooled.artifact_path)
    assert reloaded.capture.capture_id == oracle.capture.capture_id


def test_v1_manifest_is_explicitly_outside_the_v2_loader_contract(tmp_path):
    spooled, _ = _spooled_capture(tmp_path)
    _rewrite_manifest(
        spooled.artifact_path,
        lambda value: value.__setitem__(
            "schema", "arv2-massive-three-role-capture-artifact-v1"
        ),
    )
    with pytest.raises(
        MassiveCaptureError,
        match=_exact_error("capture manifest schema changed"),
    ):
        load_massive_capture_artifact(spooled.artifact_path)


@pytest.mark.parametrize("kind", ["raw", "rows", "order"])
def test_v2_spooled_artifact_tamper_or_order_change_refuses(
    tmp_path, kind
):
    spooled, _ = _spooled_capture(tmp_path)
    root = spooled.artifact_path
    manifest = json.loads((root / "manifest.json").read_bytes())
    if kind == "raw":
        target = root / manifest["pages"][0]["raw_response_file"]
        target.write_bytes(target.read_bytes() + b" ")
    elif kind == "rows":
        target = root / manifest["pages"][0]["provider_rows_file"]
        target.write_bytes(target.read_bytes().replace(b"AAPL", b"MSFT"))
    else:
        _rewrite_manifest(
            root,
            lambda value: value["pages"].__setitem__(
                slice(0, 2), list(reversed(value["pages"][:2]))
            ),
        )
    with pytest.raises(MassiveCaptureError):
        load_massive_capture_artifact(root)


def test_v2_spooled_duplicate_provider_id_is_only_a_source_candidate(tmp_path):
    responses = _success_responses()
    ratings_cursor = (
        _endpoint(MassiveSourceRole.ANALYST_RATINGS) + "?cursor=ratings-2"
    )
    responses[1] = FakeResponse(
        _payload([_row("rating-1", role=ROLE_ORDER[0])]),
        ratings_cursor,
    )

    spooled, _ = _spooled_capture(tmp_path, responses=responses)

    assert spooled.artifact_path.is_dir()
    assert not hasattr(spooled, "capture")
    with pytest.raises(
        MassiveCaptureError,
        match=_exact_error("persisted capture failed authentication"),
    ):
        load_massive_capture_artifact(spooled.artifact_path)
    with pytest.raises(
        MassiveInputPairBridgeError,
        match=_exact_error("Massive artifact failed physical authentication"),
    ):
        _build_massive_accepted_risk_input_pair_for_test(spooled.artifact_path)


def test_v2_spooled_cursor_cycle_has_no_publication_or_staging(tmp_path):
    cursor = _endpoint(ROLE_ORDER[0]) + "?cursor=repeat"
    session = FakeSession(
        [
            FakeResponse(
                _payload([_row("rating-1", role=ROLE_ORDER[0])], cursor),
                _endpoint(ROLE_ORDER[0]),
            ),
            FakeResponse(
                _payload([_row("rating-2", role=ROLE_ORDER[0])], cursor),
                cursor,
            ),
        ]
    )
    expected = "provider cursor repeats or cycles"
    with pytest.raises(MassiveCaptureError, match=_exact_error(expected)):
        _spooled_capture(tmp_path, session=session)
    assert len(session.calls) == 2
    assert list((tmp_path / "spooled-captures").iterdir()) == []


def test_v2_spooled_clock_regression_has_no_publication_or_staging(tmp_path):
    instants = iter((NOW, NOW - timedelta(microseconds=1)))
    session = FakeSession(_success_responses())
    expected = "capture page receipt times must be nondecreasing"
    with pytest.raises(MassiveCaptureError, match=_exact_error(expected)):
        _capture_massive_history_spooled_for_test(
            requested_first_event_date=FIRST_DATE,
            requested_last_event_date=LAST_DATE,
            artifact_root=tmp_path / "spooled-captures",
            session=session,
            clock=lambda: next(instants),
            api_key=KEY,
        )
    assert session.headers == {}
    assert list((tmp_path / "spooled-captures").iterdir()) == []


@pytest.mark.parametrize(
    ("limit_name", "limit", "message"),
    [
        (
            "MAX_CAPTURE_STORED_BYTES",
            1,
            "capture exceeded the reviewed stored-byte budget",
        ),
        (
            "MAX_CAPTURE_ROWS",
            0,
            "capture exceeded the reviewed stored-row budget",
        ),
        ("MAX_ARTIFACT_PAGES", 1, "capture exceeded the bounded page count"),
    ],
)
def test_v2_spooled_aggregate_limits_leave_no_publication(
    tmp_path, monkeypatch, limit_name, limit, message
):
    import scripts.capture_arv2_massive as module

    monkeypatch.setattr(module, limit_name, limit)
    session = FakeSession(_success_responses())
    with pytest.raises(MassiveCaptureError, match=_exact_error(message)):
        _spooled_capture(tmp_path, session=session)
    assert list((tmp_path / "spooled-captures").iterdir()) == []


def test_v2_spooled_write_failure_leaves_no_publication_or_staging(
    tmp_path, monkeypatch
):
    import scripts.capture_arv2_massive as module

    original_write = module._exclusive_private_write_at
    writes = 0

    def interrupted_write(
        parent_fd: int, filename: str, payload: bytes, name: str
    ) -> None:
        nonlocal writes
        writes += 1
        if writes == 2:
            raise MassiveCaptureError("synthetic spooled storage interruption")
        original_write(parent_fd, filename, payload, name)

    monkeypatch.setattr(module, "_exclusive_private_write_at", interrupted_write)
    expected = "synthetic spooled storage interruption"
    with pytest.raises(MassiveCaptureError, match=_exact_error(expected)):
        _spooled_capture(tmp_path)
    assert list((tmp_path / "spooled-captures").iterdir()) == []


def test_v2_staging_open_failure_removes_the_just_created_empty_directory(
    tmp_path, monkeypatch
):
    import scripts.capture_arv2_massive as module

    original_open = module._open_private_child_directory

    def fail_staging_open(parent_fd: int, child_name: str, name: str) -> int:
        if name == "capture staging directory":
            raise OSError("synthetic staging descriptor failure")
        return original_open(parent_fd, child_name, name)

    monkeypatch.setattr(module, "_open_private_child_directory", fail_staging_open)
    expected = "timestamped capture staging could not be created"
    with pytest.raises(MassiveCaptureError, match=_exact_error(expected)):
        _spooled_capture(tmp_path)
    assert list((tmp_path / "spooled-captures").iterdir()) == []


def test_v2_spooled_capture_replay_refusal_is_isolated_and_cleans_staging(
    tmp_path,
):
    cursor = _endpoint(ROLE_ORDER[0]) + "?cursor=replayed"
    raw = _payload([_row("rating-1", role=ROLE_ORDER[0])], cursor)
    session = FakeSession(
        [
            FakeResponse(raw, _endpoint(ROLE_ORDER[0])),
            FakeResponse(raw, cursor),
        ]
    )
    expected = "provider replayed a response page"
    with pytest.raises(MassiveCaptureError, match=_exact_error(expected)):
        _spooled_capture(tmp_path, session=session)
    assert list((tmp_path / "spooled-captures").iterdir()) == []


def test_v2_spooled_page_binding_refusal_is_isolated_and_cleans_staging(
    tmp_path, monkeypatch
):
    import scripts.capture_arv2_massive as module

    def refuse_page_binding(**kwargs):
        raise module.AcceptedRiskInputError("synthetic page-binding refusal")

    monkeypatch.setattr(module, "bind_capture_page", refuse_page_binding)
    expected = "provider page failed capture binding"
    with pytest.raises(MassiveCaptureError, match=_exact_error(expected)):
        _spooled_capture(tmp_path)
    assert list((tmp_path / "spooled-captures").iterdir()) == []


def test_v2_spooled_completion_clock_regression_is_isolated_and_cleans_staging(
    tmp_path,
):
    instants = iter((NOW, NOW, NOW, NOW, NOW, NOW - timedelta(microseconds=1)))
    session = FakeSession(_success_responses())
    expected = "capture chronology is reversed"
    with pytest.raises(MassiveCaptureError, match=_exact_error(expected)):
        _capture_massive_history_spooled_for_test(
            requested_first_event_date=FIRST_DATE,
            requested_last_event_date=LAST_DATE,
            artifact_root=tmp_path / "spooled-captures",
            session=session,
            clock=lambda: next(instants),
            api_key=KEY,
        )
    assert list((tmp_path / "spooled-captures").iterdir()) == []


def test_v2_spooled_manifest_size_refusal_is_isolated_and_cleans_staging(
    tmp_path, monkeypatch
):
    import scripts.capture_arv2_massive as module

    monkeypatch.setattr(module, "MAX_MANIFEST_BYTES", 1)
    expected = "capture manifest exceeds the byte limit"
    with pytest.raises(MassiveCaptureError, match=_exact_error(expected)):
        _spooled_capture(tmp_path)
    assert list((tmp_path / "spooled-captures").iterdir()) == []


def test_v2_total_stored_file_ceiling_includes_manifest_and_digest(
    tmp_path, monkeypatch
):
    import scripts.capture_arv2_massive as module

    original_manifest = module._manifest_from_page_records

    def render_then_narrow_limit(**kwargs):
        manifest = original_manifest(**kwargs)
        page_bytes = (
            manifest["raw_response_total_byte_count"]
            + manifest["provider_rows_total_byte_count"]
        )
        required = page_bytes + len(canonical_json_bytes(manifest)) + 65
        monkeypatch.setattr(module, "MAX_CAPTURE_STORED_BYTES", required - 1)
        return manifest

    monkeypatch.setattr(module, "_manifest_from_page_records", render_then_narrow_limit)
    expected = "capture exceeds the reviewed stored-byte budget"
    with pytest.raises(MassiveCaptureError, match=_exact_error(expected)):
        _spooled_capture(tmp_path)
    assert list((tmp_path / "spooled-captures").iterdir()) == []


def test_v2_spooled_publication_failure_is_isolated_and_cleans_staging(
    tmp_path, monkeypatch
):
    import scripts.capture_arv2_massive as module

    original_inventory = module._validate_inventory_at

    def refuse_rename(*args, **kwargs):
        raise OSError("synthetic rename failure")

    def validate_then_arm_rename(*args, **kwargs):
        original_inventory(*args, **kwargs)
        monkeypatch.setattr(module.os, "rename", refuse_rename)

    monkeypatch.setattr(module, "_validate_inventory_at", validate_then_arm_rename)
    expected = "capture publication failed"
    with pytest.raises(MassiveCaptureError, match=_exact_error(expected)):
        _spooled_capture(tmp_path)
    assert list((tmp_path / "spooled-captures").iterdir()) == []


def test_v2_spooled_ambiguous_publication_refusal_is_isolated(
    tmp_path, monkeypatch
):
    import scripts.capture_arv2_massive as module

    original_rename = module.os.rename
    original_sync = module._fsync_fd
    original_inventory = module._validate_inventory_at
    rename_count = 0

    def fail_only_rollback(*args, **kwargs):
        nonlocal rename_count
        rename_count += 1
        if rename_count == 2:
            raise OSError("synthetic rollback failure")
        return original_rename(*args, **kwargs)

    def fail_root_sync(descriptor: int, name: str) -> None:
        if name == "capture root publication":
            raise MassiveCaptureError("synthetic root sync failure")
        original_sync(descriptor, name)

    def validate_then_arm_rename(*args, **kwargs):
        original_inventory(*args, **kwargs)
        monkeypatch.setattr(module.os, "rename", fail_only_rollback)

    monkeypatch.setattr(module, "_validate_inventory_at", validate_then_arm_rename)
    monkeypatch.setattr(module, "_fsync_fd", fail_root_sync)
    expected = "capture publication state is ambiguous after root-sync failure"
    with pytest.raises(MassiveCaptureError, match=_exact_error(expected)):
        _spooled_capture(tmp_path)
    assert rename_count == 2


def test_v2_spooled_post_rename_identity_failure_is_explicitly_ambiguous(
    tmp_path, monkeypatch
):
    import scripts.capture_arv2_massive as module

    original_identity_check = module._require_pinned_child_identity

    def fail_published_identity(parent_fd, child, child_fd, name):
        if name == "published capture artifact":
            raise MassiveCaptureError("synthetic published identity failure")
        return original_identity_check(parent_fd, child, child_fd, name)

    monkeypatch.setattr(
        module, "_require_pinned_child_identity", fail_published_identity
    )
    expected = (
        "capture publication state is ambiguous after identity verification failure"
    )
    with pytest.raises(MassiveCaptureError, match=_exact_error(expected)):
        _spooled_capture(tmp_path)
    entries = list((tmp_path / "spooled-captures").iterdir())
    assert len(entries) == 1
    assert not entries[0].name.startswith(".")


def test_v2_spooled_root_sync_rollback_is_durable_before_cleanup(
    tmp_path, monkeypatch
):
    import scripts.capture_arv2_massive as module

    original_sync = module._fsync_fd
    sync_names: list[str] = []

    def fail_publication_sync(descriptor: int, name: str) -> None:
        sync_names.append(name)
        if name == "capture root publication":
            raise MassiveCaptureError("synthetic root sync failure")
        original_sync(descriptor, name)

    monkeypatch.setattr(module, "_fsync_fd", fail_publication_sync)
    with pytest.raises(
        MassiveCaptureError,
        match=_exact_error("synthetic root sync failure"),
    ):
        _spooled_capture(tmp_path)
    assert sync_names[-2:] == ["capture root publication", "capture root rollback"]
    assert list((tmp_path / "spooled-captures").iterdir()) == []


def test_v2_spooled_rollback_sync_failure_preserves_hidden_artifact(
    tmp_path, monkeypatch
):
    import scripts.capture_arv2_massive as module

    original_sync = module._fsync_fd
    sync_names: list[str] = []

    def fail_both_root_syncs(descriptor: int, name: str) -> None:
        sync_names.append(name)
        if name in {"capture root publication", "capture root rollback"}:
            raise MassiveCaptureError(f"synthetic {name} failure")
        original_sync(descriptor, name)

    monkeypatch.setattr(module, "_fsync_fd", fail_both_root_syncs)
    expected = "capture publication state is ambiguous after rollback sync failure"
    with pytest.raises(MassiveCaptureError, match=_exact_error(expected)):
        _spooled_capture(tmp_path)
    assert sync_names[-2:] == ["capture root publication", "capture root rollback"]
    entries = list((tmp_path / "spooled-captures").iterdir())
    assert len(entries) == 1
    assert entries[0].name.startswith(".")
    assert entries[0].name.endswith(".incomplete")


def test_v2_spooled_collision_refusal_is_isolated_before_provider_io(tmp_path):
    first, _ = _spooled_capture(tmp_path)
    session = FakeSession(_success_responses())
    expected = "timestamped capture or incomplete staging already exists"
    with pytest.raises(MassiveCaptureError, match=_exact_error(expected)):
        _spooled_capture(tmp_path, session=session)
    assert session.calls == []
    assert list((tmp_path / "spooled-captures").iterdir()) == [
        first.artifact_path
    ]


def test_v2_spooled_configuration_refusal_is_isolated_before_provider_io(
    tmp_path,
):
    import scripts.capture_arv2_massive as module

    session = FakeSession(_success_responses())
    expected = "spooled capture configuration is not reviewed"
    with pytest.raises(MassiveCaptureError, match=_exact_error(expected)):
        module._capture_massive_history_spooled_core(
            requested_first_event_date=FIRST_DATE,
            requested_last_event_date=LAST_DATE,
            artifact_root=tmp_path / "spooled-captures",
            page_limit=50_000,
            session=session,
            clock=lambda: NOW,
            api_key=KEY,
            capture_transport="unreviewed-transport",
            close_owned_session=False,
        )
    assert session.calls == []
    assert not (tmp_path / "spooled-captures").exists()


def test_v2_manifest_construction_refusals_are_isolated(
    tmp_path, monkeypatch
):
    import scripts.capture_arv2_massive as module

    expected = "capture page did not retain exact raw response bytes"
    with pytest.raises(MassiveCaptureError, match=_exact_error(expected)):
        module._artifact_page_record(
            SimpleNamespace(source_role=ROLE_ORDER[0], raw_response_bytes=None)
        )

    expected = "capture storage mode must be an exact boolean"
    with pytest.raises(MassiveCaptureError, match=_exact_error(expected)):
        module._manifest_from_page_records(
            artifact_id="arv2-massive-three-role-20260912T123456123456Z",
            capture_started_at="2026-09-12T12:34:56.123456Z",
            capture_completed_at="2026-09-12T12:34:56.123456Z",
            requested_first_event_date=FIRST_DATE,
            requested_last_event_date=LAST_DATE,
            page_records=(),
            page_limit=50_000,
            capture_transport=TEST_TRANSPORT,
            page_spooled_before_next_request=1,
        )

    loaded, _ = _capture(tmp_path, monkeypatch)
    original_logical_record = module._logical_capture_record

    def changed_logical_record(**kwargs):
        value = original_logical_record(**kwargs)
        value["contract_id"] = "changed-contract"
        return value

    monkeypatch.setattr(module, "_logical_capture_record", changed_logical_record)
    expected = "artifact manifest changed logical capture identity"
    with pytest.raises(MassiveCaptureError, match=_exact_error(expected)):
        module._manifest_record(
            loaded.artifact_path.name,
            loaded.capture,
            50_000,
            TEST_TRANSPORT,
        )


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("stored_byte_limit", "manifest stored-byte budget changed"),
        ("stored_row_limit", "manifest stored-row budget changed"),
        ("inconsistent_storage", "manifest capture storage mode is inconsistent"),
        ("production_not_spooled", "production capture was not page-spooled"),
        ("stored_bytes_exceeded", "manifest exceeds the stored-byte budget"),
        ("stored_rows_exceeded", "manifest exceeds the stored-row budget"),
    ],
)
def test_v2_manifest_storage_refusals_are_isolated(
    tmp_path, mutation, expected
):
    import scripts.capture_arv2_massive as module

    spooled, _ = _spooled_capture(tmp_path)

    def mutate(value):
        if mutation == "stored_byte_limit":
            value["stored_capture_byte_limit"] -= 1
        elif mutation == "stored_row_limit":
            value["stored_capture_row_limit"] -= 1
        elif mutation == "inconsistent_storage":
            value["full_capture_retained_in_memory"] = True
        elif mutation == "production_not_spooled":
            value["capture_transport"] = PRODUCTION_TRANSPORT
            value["provider_io_read_only"] = True
            value["page_spooled_before_next_request"] = False
            value["full_capture_retained_in_memory"] = True
        elif mutation == "stored_bytes_exceeded":
            value["raw_response_total_byte_count"] = 8 * 1024 * 1024 * 1024
        else:
            value["total_row_count"] = value["stored_capture_row_limit"] + 1

    _rewrite_manifest(spooled.artifact_path, mutate)
    with pytest.raises(MassiveCaptureError, match=_exact_error(expected)):
        load_massive_capture_artifact(spooled.artifact_path)


def test_three_roles_pagination_private_persistence_and_reload(
    tmp_path, monkeypatch
):
    loaded, fake = _capture(tmp_path, monkeypatch)

    capture = require_capture_binding(loaded.capture)
    assert capture.requested_first_event_date == FIRST_DATE
    assert capture.requested_last_event_date == LAST_DATE
    assert capture.total_page_count == 4
    assert capture.total_row_count == 4
    assert tuple(role for role, _ in capture.role_row_counts) == ROLE_ORDER
    assert loaded.accepted_risk_input_pair is None
    assert loaded.capture_transport == TEST_TRANSPORT

    assert fake.headers == {}
    assert [url for url, _ in fake.calls] == [
        _endpoint(ROLE_ORDER[0]),
        _endpoint(ROLE_ORDER[0]) + "?cursor=ratings-2",
        _endpoint(ROLE_ORDER[1]),
        _endpoint(ROLE_ORDER[2]),
    ]
    expected_first_params = {
        "date.gte": FIRST_DATE,
        "date.lte": LAST_DATE,
        "limit": 50_000,
        "sort": "date.asc",
    }
    assert fake.calls[0][1] == {
        "params": expected_first_params,
        "timeout": 60,
        "allow_redirects": False,
        "stream": True,
    }
    assert fake.calls[1][1]["params"] is None
    assert fake.calls[2][1]["params"] == expected_first_params
    assert fake.calls[3][1]["params"] == expected_first_params

    manifest_bytes = (loaded.artifact_path / "manifest.json").read_bytes()
    assert manifest_bytes.endswith(b"\n") and b"\r" not in manifest_bytes
    manifest = json.loads(manifest_bytes)
    assert manifest["role_order"] == [role.value for role in ROLE_ORDER]
    assert manifest["capture_transport"] == TEST_TRANSPORT
    assert manifest["provider_io_read_only"] is False
    assert manifest["cursor_material_persisted_outside_raw_provider_responses"] is False
    assert "ratings-2" not in manifest_bytes.decode("utf-8")
    assert KEY not in manifest_bytes.decode("utf-8")
    assert [page["page_number"] for page in manifest["pages"]] == [1, 2, 1, 1]
    assert manifest["pages"][0]["next_cursor_sha256"] == manifest["pages"][1][
        "request_cursor_sha256"
    ]
    assert manifest["pages"][1]["terminal_page"] is True
    first_rows = loaded.artifact_path / manifest["pages"][0]["provider_rows_file"]
    assert first_rows.read_bytes().endswith(b"\n")
    assert b"\r" not in first_rows.read_bytes()
    assert first_rows.read_text(encoding="utf-8").splitlines()[0] == json.dumps(
        _row("rating-1", role=ROLE_ORDER[0]),
        sort_keys=True,
        separators=(",", ":"),
    )
    if os.name != "nt":
        assert stat.S_IMODE(loaded.artifact_path.stat().st_mode) == 0o700
        assert stat.S_IMODE((loaded.artifact_path / "pages").stat().st_mode) == 0o700
        for file_path in loaded.artifact_path.rglob("*"):
            if file_path.is_file():
                assert stat.S_IMODE(file_path.stat().st_mode) == 0o600

    reloaded = load_massive_capture_artifact(loaded.artifact_path)
    assert reloaded.manifest_sha256 == loaded.manifest_sha256
    assert reloaded.capture.capture_sha256 == capture.capture_sha256
    assert reloaded.accepted_risk_input_pair is None
    assert reloaded.capture_transport == TEST_TRANSPORT
    assert all(response.close_count == 1 for response in fake.served)


def test_decimal_lexeme_is_preserved_in_canonical_ordered_extraction(
    tmp_path, monkeypatch
):
    rating_raw = (
        b'{"status":"OK","results":[{"z":1.20,"integral_decimal":1e0,'
        b'"benzinga_id":"rating-decimal",'
        b'"date":"2021-01-04","time":"08:30:00",'
        b'"last_updated":"2021-01-04T13:30:00Z","ticker":"AAPL"}]}'
    )
    responses = [
        FakeResponse(rating_raw, _endpoint(ROLE_ORDER[0])),
        FakeResponse(_payload([]), _endpoint(ROLE_ORDER[1])),
        FakeResponse(_payload([]), _endpoint(ROLE_ORDER[2])),
    ]
    loaded, _ = _capture(tmp_path, monkeypatch, responses=responses)
    manifest = json.loads((loaded.artifact_path / "manifest.json").read_bytes())
    row_file = loaded.artifact_path / manifest["pages"][0]["provider_rows_file"]
    assert b'"z":1.20' in row_file.read_bytes()
    assert b'"integral_decimal":1E+0' in row_file.read_bytes()
    load_massive_capture_artifact(loaded.artifact_path)


def test_empty_terminal_page_for_each_role_is_a_complete_capture(tmp_path, monkeypatch):
    loaded, fake = _capture(
        tmp_path, monkeypatch, responses=_success_responses(all_empty=True)
    )
    capture = require_capture_binding(loaded.capture)
    assert capture.total_page_count == 3
    assert capture.total_row_count == 0
    assert all(page.terminal_page and page.provider_rows_bytes == b"" for page in capture.pages)
    assert len(fake.calls) == 3


def test_page_limit_50000_is_admitted_and_larger_limit_refuses_before_io(
    tmp_path, monkeypatch
):
    loaded, _ = _capture(tmp_path, monkeypatch, page_limit=50_000)
    assert loaded.capture.total_page_count == 4
    fake = FakeSession()
    with pytest.raises(MassiveCaptureError, match="at most 50000"):
        _capture_massive_history_for_test(
            requested_first_event_date=FIRST_DATE,
            requested_last_event_date=LAST_DATE,
            artifact_root=tmp_path / "other",
            page_limit=50_001,
            session=fake,
            clock=lambda: NOW,
            api_key=KEY,
        )
    assert fake.calls == []


def test_missing_or_malformed_credential_refuses_before_io(tmp_path, monkeypatch):
    import scripts.capture_arv2_massive as module

    monkeypatch.setattr(module, "REPOSITORY_ARTIFACTS_ROOT", tmp_path)
    monkeypatch.setattr(
        module,
        "_new_session",
        lambda: pytest.fail("session construction must follow credential validation"),
    )
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    with pytest.raises(MassiveCaptureError, match="unavailable or malformed"):
        capture_massive_history(
            requested_first_event_date=FIRST_DATE,
            requested_last_event_date=LAST_DATE,
            artifact_root=tmp_path / "captures",
        )


def test_provider_exception_and_url_diagnostics_never_echo_credentials(
    tmp_path, monkeypatch
):
    secret_url = f"https://user:{KEY}@api.massive.com/x?apiKey={KEY}&cursor=c#{KEY}"
    session = FakeSession(failure=RuntimeError(f"failure at {secret_url}"))
    with pytest.raises(MassiveCaptureError) as captured:
        _capture_massive_history_for_test(
            requested_first_event_date=FIRST_DATE,
            requested_last_event_date=LAST_DATE,
            artifact_root=tmp_path / "captures",
            session=session,
            clock=lambda: NOW,
            api_key=KEY,
        )
    assert KEY not in str(captured.value)
    redacted = _redact_url(secret_url)
    assert KEY not in redacted
    assert "user:" not in redacted
    assert "cursor=c" not in redacted
    assert "#" not in redacted
    assert redacted == (
        "https://REDACTED@api.massive.com/x?apiKey=REDACTED&cursor=REDACTED"
    )


def test_response_echoing_credential_refuses_before_artifact_creation(
    tmp_path, monkeypatch
):
    responses = [
        FakeResponse(
            _payload([{"benzinga_id": "x", "notes": KEY}]),
            _endpoint(ROLE_ORDER[0]),
        )
    ]
    session = FakeSession(responses)
    with pytest.raises(MassiveCaptureError, match="echo credential") as captured:
        _capture_massive_history_for_test(
            requested_first_event_date=FIRST_DATE,
            requested_last_event_date=LAST_DATE,
            artifact_root=tmp_path / "captures",
            session=session,
            clock=lambda: NOW,
            api_key=KEY,
        )
    assert KEY not in str(captured.value)
    assert not (tmp_path / "captures").exists()


@pytest.mark.parametrize(
    "raw",
    [
        b'{"results":[],"status":"ERROR"}',
        b'{"results":[]}',
        b'{"results":[],"results":[]}',
        b'{"results":[NaN]}',
        b'{"results":{}}',
        b'{"results":[1]}',
        b'{"results":[],"next_url":""}',
        b"\xff",
    ],
)
def test_noncanonical_or_invalid_provider_response_refuses_without_persistence(
    tmp_path, monkeypatch, raw
):
    session = FakeSession([FakeResponse(raw, _endpoint(ROLE_ORDER[0]))])
    with pytest.raises(MassiveCaptureError):
        _capture_massive_history_for_test(
            requested_first_event_date=FIRST_DATE,
            requested_last_event_date=LAST_DATE,
            artifact_root=tmp_path / "captures",
            session=session,
            clock=lambda: NOW,
            api_key=KEY,
        )
    assert not (tmp_path / "captures").exists()


@pytest.mark.parametrize(
    "next_url",
    [
        "http://api.massive.com/benzinga/v1/ratings?cursor=x",
        "https://evil.example/benzinga/v1/ratings?cursor=x",
        "https://user:password@api.massive.com/benzinga/v1/ratings?cursor=x",
        "https://api.massive.com/benzinga/v1/earnings?cursor=x",
        "https://api.massive.com/benzinga/v1/ratings?cursor=x#token=secret",
        "https://api.massive.com/benzinga/v1/ratings?cursor=x&apiKey=secret",
        "https://api.massive.com/benzinga/v1/ratings?cursor=x&unknown=y",
        "https://api.massive.com/benzinga/v1/ratings?cursor=x&limit=1",
        "https://api.massive.com/benzinga/v1/ratings?cursor=x&date.gte=2022-01-01",
        "https://api.massive.com/benzinga/v1/ratings?cursor=x&date.lte=2022-12-31",
        "https://api.massive.com/benzinga/v1/ratings?cursor=x&sort=date.desc",
        "https://api.massive.com/benzinga/v1/ratings?cursor=x&cursor=y",
    ],
)
def test_unreviewed_or_credential_bearing_next_url_refuses(
    tmp_path, monkeypatch, next_url
):
    session = FakeSession(
        [
            FakeResponse(
                _payload([_row("rating-1", role=ROLE_ORDER[0])], next_url),
                _endpoint(ROLE_ORDER[0]),
            )
        ]
    )
    with pytest.raises(MassiveCaptureError, match="next_url"):
        _capture_massive_history_for_test(
            requested_first_event_date=FIRST_DATE,
            requested_last_event_date=LAST_DATE,
            artifact_root=tmp_path / "captures",
            session=session,
            clock=lambda: NOW,
            api_key=KEY,
        )
    assert not (tmp_path / "captures").exists()


def test_cursor_url_with_exact_frozen_query_is_admitted_but_only_hash_is_metadata(
    tmp_path, monkeypatch
):
    cursor_token = "opaque-cursor-never-metadata"
    cursor = (
        _endpoint(ROLE_ORDER[0])
        + f"?date.gte={FIRST_DATE}&date.lte={LAST_DATE}"
        + f"&limit=50000&sort=date.asc&cursor={cursor_token}"
    )
    responses = [
        FakeResponse(
            _payload([_row("rating-1", role=ROLE_ORDER[0])], cursor),
            _endpoint(ROLE_ORDER[0]),
        ),
        FakeResponse(_payload([_row("rating-2", role=ROLE_ORDER[0])]), cursor),
        FakeResponse(_payload([]), _endpoint(ROLE_ORDER[1])),
        FakeResponse(_payload([]), _endpoint(ROLE_ORDER[2])),
    ]
    loaded, fake = _capture(tmp_path, monkeypatch, responses=responses)
    manifest_bytes = (loaded.artifact_path / "manifest.json").read_bytes()
    assert cursor_token.encode() not in manifest_bytes
    assert b"apiKey" not in manifest_bytes
    assert fake.calls[1][0] == cursor
    assert fake.calls[1][1]["params"] is None
    load_massive_capture_artifact(loaded.artifact_path)


def test_duplicate_cursor_cycle_refuses(tmp_path, monkeypatch):
    cursor = _endpoint(ROLE_ORDER[0]) + "?cursor=repeat"
    responses = [
        FakeResponse(
            _payload([_row("rating-1", role=ROLE_ORDER[0])], cursor),
            _endpoint(ROLE_ORDER[0]),
        ),
        FakeResponse(
            _payload([_row("rating-2", role=ROLE_ORDER[0])], cursor), cursor
        ),
    ]
    session = FakeSession(responses)
    with pytest.raises(MassiveCaptureError, match="cursor repeats or cycles"):
        _capture_massive_history_for_test(
            requested_first_event_date=FIRST_DATE,
            requested_last_event_date=LAST_DATE,
            artifact_root=tmp_path / "captures",
            session=session,
            clock=lambda: NOW,
            api_key=KEY,
        )
    assert len(session.calls) == 2
    assert not (tmp_path / "captures").exists()


def test_interrupted_provider_chain_leaves_no_publishable_artifact(
    tmp_path, monkeypatch
):
    cursor = _endpoint(ROLE_ORDER[0]) + "?cursor=second-page"

    class InterruptingSession(FakeSession):
        def get(self, url: str, **kwargs: object) -> FakeResponse:
            if not self.calls:
                return super().get(url, **kwargs)
            self.calls.append((url, dict(kwargs)))
            raise TimeoutError(f"provider timeout with hidden key {KEY}")

    session = InterruptingSession(
        [
            FakeResponse(
                _payload([_row("rating-1", role=ROLE_ORDER[0])], cursor),
                _endpoint(ROLE_ORDER[0]),
            )
        ]
    )
    with pytest.raises(MassiveCaptureError) as captured:
        _capture_massive_history_for_test(
            requested_first_event_date=FIRST_DATE,
            requested_last_event_date=LAST_DATE,
            artifact_root=tmp_path / "captures",
            session=session,
            clock=lambda: NOW,
            api_key=KEY,
        )
    assert KEY not in str(captured.value)
    assert len(session.calls) == 2
    assert not (tmp_path / "captures").exists()


def test_replayed_raw_response_refuses(tmp_path, monkeypatch):
    cursor = _endpoint(ROLE_ORDER[0]) + "?cursor=repeat"
    raw = _payload([_row("rating-1", role=ROLE_ORDER[0])], cursor)
    session = FakeSession(
        [
            FakeResponse(raw, _endpoint(ROLE_ORDER[0])),
            FakeResponse(raw, cursor),
        ]
    )
    with pytest.raises(MassiveCaptureError, match="replayed"):
        _capture_massive_history_for_test(
            requested_first_event_date=FIRST_DATE,
            requested_last_event_date=LAST_DATE,
            artifact_root=tmp_path / "captures",
            session=session,
            clock=lambda: NOW,
            api_key=KEY,
        )


def test_timestamp_collision_refuses_overwrite_and_preserves_existing_bytes(
    tmp_path, monkeypatch
):
    first, _ = _capture(tmp_path, monkeypatch)
    before = {
        path.relative_to(first.artifact_path): path.read_bytes()
        for path in first.artifact_path.rglob("*")
        if path.is_file()
    }
    with pytest.raises(MassiveCaptureError, match="overwrite refused"):
        _capture(tmp_path, monkeypatch)
    after = {
        path.relative_to(first.artifact_path): path.read_bytes()
        for path in first.artifact_path.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_interrupted_persistence_has_no_manifest_and_loader_refuses(
    tmp_path, monkeypatch
):
    import scripts.capture_arv2_massive as module

    original_write = module._exclusive_private_write_at
    writes = 0

    def interrupted_write(
        parent_fd: int, filename: str, payload: bytes, name: str
    ) -> None:
        nonlocal writes
        writes += 1
        if writes == 2:
            raise MassiveCaptureError("synthetic storage interruption")
        original_write(parent_fd, filename, payload, name)

    monkeypatch.setattr(module, "_exclusive_private_write_at", interrupted_write)
    with pytest.raises(MassiveCaptureError, match="synthetic storage interruption"):
        _capture(tmp_path, monkeypatch)
    artifacts = list((tmp_path / "captures").iterdir())
    assert len(artifacts) == 1
    assert artifacts[0].name.startswith(".") and artifacts[0].name.endswith(
        ".incomplete"
    )
    assert not (artifacts[0] / "manifest.json").exists()
    with pytest.raises(MassiveCaptureError):
        load_massive_capture_artifact(artifacts[0])


@pytest.mark.parametrize("kind", ["raw", "rows", "manifest", "digest"])
def test_byte_tampering_refuses(tmp_path, monkeypatch, kind):
    loaded, _ = _capture(tmp_path, monkeypatch)
    root = loaded.artifact_path
    manifest = json.loads((root / "manifest.json").read_bytes())
    if kind == "raw":
        target = root / manifest["pages"][0]["raw_response_file"]
        target.write_bytes(target.read_bytes() + b" ")
    elif kind == "rows":
        target = root / manifest["pages"][0]["provider_rows_file"]
        target.write_bytes(target.read_bytes().replace(b"AAPL", b"MSFT"))
    elif kind == "manifest":
        target = root / "manifest.json"
        target.write_bytes(target.read_bytes() + b" ")
    else:
        (root / "manifest.sha256").write_bytes(("0" * 64 + "\n").encode())
    with pytest.raises(MassiveCaptureError):
        load_massive_capture_artifact(root)


def test_semantically_equal_but_noncanonical_rows_refuse(tmp_path, monkeypatch):
    loaded, _ = _capture(tmp_path, monkeypatch)
    root = loaded.artifact_path
    manifest = json.loads((root / "manifest.json").read_bytes())
    page = manifest["pages"][0]
    rows_path = root / page["provider_rows_file"]
    parsed = json.loads(rows_path.read_text(encoding="utf-8").splitlines()[0])
    noncanonical = (json.dumps(parsed, indent=2) + "\n").encode()
    rows_path.write_bytes(noncanonical)
    _rewrite_manifest(
        root,
        lambda value: value["pages"][0].update(
            provider_rows_byte_count=len(noncanonical),
            provider_rows_sha256=sha256_bytes(noncanonical),
        ),
    )
    with pytest.raises(MassiveCaptureError, match="canonical ordered extraction"):
        load_massive_capture_artifact(root)


def test_manifest_cursor_chain_forgery_refuses_even_with_rehashed_manifest(
    tmp_path, monkeypatch
):
    loaded, _ = _capture(tmp_path, monkeypatch)
    root = loaded.artifact_path
    _rewrite_manifest(
        root,
        lambda value: value["pages"][0].update(next_cursor_sha256="0" * 64),
    )
    with pytest.raises(MassiveCaptureError, match="cursor hash"):
        load_massive_capture_artifact(root)


def test_manifest_page_reordering_refuses_even_with_rehashed_manifest(
    tmp_path, monkeypatch
):
    loaded, _ = _capture(tmp_path, monkeypatch)
    root = loaded.artifact_path

    def reverse_first_two(value):
        value["pages"][0], value["pages"][1] = value["pages"][1], value["pages"][0]

    _rewrite_manifest(root, reverse_first_two)
    with pytest.raises(MassiveCaptureError, match="contiguous|canonical role order"):
        load_massive_capture_artifact(root)


def test_unknown_manifest_field_refuses_even_with_rehashed_manifest(
    tmp_path, monkeypatch
):
    loaded, _ = _capture(tmp_path, monkeypatch)
    root = loaded.artifact_path
    _rewrite_manifest(root, lambda value: value.update(extra="not reviewed"))
    with pytest.raises(MassiveCaptureError, match="not canonical|field|keys"):
        load_massive_capture_artifact(root)


def test_extra_file_refuses_inventory(tmp_path, monkeypatch):
    loaded, _ = _capture(tmp_path, monkeypatch)
    extra = loaded.artifact_path / "extra.txt"
    extra.write_bytes(b"not authenticated")
    if os.name != "nt":
        extra.chmod(0o600)
    with pytest.raises(MassiveCaptureError, match="inventory"):
        load_massive_capture_artifact(loaded.artifact_path)


def test_leaf_symlink_refuses(tmp_path, monkeypatch):
    loaded, _ = _capture(tmp_path, monkeypatch)
    root = loaded.artifact_path
    manifest = json.loads((root / "manifest.json").read_bytes())
    target = root / manifest["pages"][0]["raw_response_file"]
    saved = target.with_name("saved-private-page")
    target.rename(saved)
    try:
        target.symlink_to(saved)
    except OSError as exc:
        pytest.skip(f"host cannot create symlink: {exc}")
    with pytest.raises(MassiveCaptureError, match="link|symlink"):
        load_massive_capture_artifact(root)


@pytest.mark.skipif(os.name == "nt", reason="POSIX hard-link custody check")
def test_external_hard_link_to_page_refuses_single_link_custody(tmp_path, monkeypatch):
    loaded, _ = _capture(tmp_path, monkeypatch)
    root = loaded.artifact_path
    manifest = json.loads((root / "manifest.json").read_bytes())
    target = root / manifest["pages"][0]["provider_rows_file"]
    alias = tmp_path / "external-page-alias"
    try:
        os.link(target, alias)
    except OSError as exc:
        pytest.skip(f"host cannot create hard link: {exc}")
    with pytest.raises(MassiveCaptureError, match="single-link"):
        load_massive_capture_artifact(root)


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are not Windows ACLs")
@pytest.mark.parametrize("target_kind", ["artifact", "pages", "manifest", "page"])
def test_nonprivate_mode_refuses(tmp_path, monkeypatch, target_kind):
    loaded, _ = _capture(tmp_path, monkeypatch)
    root = loaded.artifact_path
    manifest = json.loads((root / "manifest.json").read_bytes())
    targets = {
        "artifact": root,
        "pages": root / "pages",
        "manifest": root / "manifest.json",
        "page": root / manifest["pages"][0]["raw_response_file"],
    }
    targets[target_kind].chmod(0o755 if targets[target_kind].is_dir() else 0o644)
    with pytest.raises(MassiveCaptureError, match="private|0700"):
        load_massive_capture_artifact(root)


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are not Windows ACLs")
def test_existing_nonprivate_capture_root_refuses_without_chmod(tmp_path, monkeypatch):
    root = tmp_path / "shared-root"
    root.mkdir(mode=0o755)
    root.chmod(0o755)
    session = FakeSession(_success_responses())
    with pytest.raises(MassiveCaptureError, match="private 0700"):
        _capture_massive_history_for_test(
            requested_first_event_date=FIRST_DATE,
            requested_last_event_date=LAST_DATE,
            artifact_root=root,
            session=session,
            clock=lambda: NOW,
            api_key=KEY,
        )
    assert stat.S_IMODE(root.stat().st_mode) == 0o755
    assert list(root.iterdir()) == []
    assert session.calls == []


def test_symlinked_capture_root_refuses(tmp_path, monkeypatch):
    real = tmp_path / "real-root"
    real.mkdir()
    linked = tmp_path / "linked-root"
    try:
        linked.symlink_to(real, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"host cannot create directory symlink: {exc}")
    session = FakeSession(_success_responses())
    with pytest.raises(MassiveCaptureError, match="link"):
        _capture_massive_history_for_test(
            requested_first_event_date=FIRST_DATE,
            requested_last_event_date=LAST_DATE,
            artifact_root=linked,
            session=session,
            clock=lambda: NOW,
            api_key=KEY,
        )
    assert list(real.iterdir()) == []
    assert session.calls == []


def test_operational_default_session_cannot_write_outside_ignored_artifacts(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MASSIVE_API_KEY", "production-key-never-contacted")
    with pytest.raises(MassiveCaptureError, match="beneath repository artifacts"):
        capture_massive_history(
            requested_first_event_date=FIRST_DATE,
            requested_last_event_date=LAST_DATE,
            artifact_root=tmp_path / "not-repository-artifacts",
        )
    assert not (tmp_path / "not-repository-artifacts").exists()


def test_offline_session_is_the_only_request_surface_and_retains_no_key(
    tmp_path, monkeypatch
):
    loaded, fake = _capture(tmp_path, monkeypatch)
    assert loaded.capture.total_row_count == 4
    assert len(fake.calls) == 4
    assert fake.responses == []
    assert fake.headers == {}
    assert all(response.close_count == 1 for response in fake.served)


def test_public_capture_surface_has_no_transport_or_clock_injection() -> None:
    parameters = inspect.signature(capture_massive_history).parameters
    assert "_session" not in parameters
    assert "_clock" not in parameters
    assert "session" not in parameters
    assert "clock" not in parameters


def test_unbounded_pair_construction_refuses_before_transport_or_filesystem(
    tmp_path, monkeypatch
):
    session = FakeSession(_success_responses())
    with pytest.raises(MassiveCaptureError, match="separately reviewed bounded bridge"):
        _capture_massive_history_for_test(
            requested_first_event_date=FIRST_DATE,
            requested_last_event_date=LAST_DATE,
            artifact_root=tmp_path / "captures",
            session=session,
            clock=lambda: NOW,
            api_key=KEY,
            build_input_pair=True,
        )
    assert session.calls == []
    assert not (tmp_path / "captures").exists()
    with pytest.raises(MassiveCaptureError, match="separately reviewed bounded bridge"):
        load_massive_capture_artifact(
            tmp_path / "does-not-exist", build_input_pair=True
        )


def test_stream_only_responses_are_consumed_and_closed(tmp_path, monkeypatch):
    class StreamOnlyResponse:
        def __init__(self, payload: bytes, url: str) -> None:
            self._payload = payload
            self.url = url
            self.status_code = 200
            self.request: object | None = None
            self.close_count = 0

        @property
        def content(self):
            raise AssertionError("unbounded Response.content must not be read")

        def iter_content(self, *, chunk_size: int):
            for offset in range(0, len(self._payload), chunk_size):
                yield self._payload[offset : offset + chunk_size]

        def close(self) -> None:
            self.close_count += 1

    responses = [
        StreamOnlyResponse(_payload([]), _endpoint(role)) for role in ROLE_ORDER
    ]
    session = FakeSession(responses)  # type: ignore[arg-type]
    loaded, _ = _capture(tmp_path, monkeypatch, session=session)
    assert loaded.capture.total_row_count == 0
    assert all(response.close_count == 1 for response in responses)
    assert all(call[1]["stream"] is True for call in session.calls)


def test_decoded_response_byte_cap_applies_during_streaming(
    tmp_path, monkeypatch
):
    import scripts.capture_arv2_massive as module

    response = FakeResponse(b"x" * 17, _endpoint(ROLE_ORDER[0]))
    session = FakeSession([response])
    monkeypatch.setattr(module, "MAX_RAW_RESPONSE_BYTES", 16)
    with pytest.raises(MassiveCaptureError, match="exceeded the byte limit"):
        _capture_massive_history_for_test(
            requested_first_event_date=FIRST_DATE,
            requested_last_event_date=LAST_DATE,
            artifact_root=tmp_path / "captures",
            session=session,
            clock=lambda: NOW,
            api_key=KEY,
        )
    assert response.close_count == 1
    assert session.headers == {}
    assert not (tmp_path / "captures").exists()


def test_aggregate_retention_cap_refuses_before_persistence(
    tmp_path, monkeypatch
):
    import scripts.capture_arv2_massive as module

    session = FakeSession(_success_responses())
    monkeypatch.setattr(module, "MAX_CAPTURE_RETAINED_BYTES", 1)
    with pytest.raises(MassiveCaptureError, match="retained-byte budget"):
        _capture_massive_history_for_test(
            requested_first_event_date=FIRST_DATE,
            requested_last_event_date=LAST_DATE,
            artifact_root=tmp_path / "captures",
            session=session,
            clock=lambda: NOW,
            api_key=KEY,
        )
    assert len(session.calls) == 1
    assert session.served[0].close_count == 1
    assert session.headers == {}
    assert not (tmp_path / "captures").exists()


def test_prepared_request_must_match_the_exact_frozen_query(
    tmp_path, monkeypatch
):
    class LyingPreparedRequestSession(FakeSession):
        def get(self, url: str, **kwargs: object) -> FakeResponse:
            response = super().get(url, **kwargs)
            response.request = SimpleNamespace(method="GET", url=url)
            return response

    response = FakeResponse(_payload([]), _endpoint(ROLE_ORDER[0]))
    session = LyingPreparedRequestSession([response])
    with pytest.raises(MassiveCaptureError, match="prepared provider request"):
        _capture_massive_history_for_test(
            requested_first_event_date=FIRST_DATE,
            requested_last_event_date=LAST_DATE,
            artifact_root=tmp_path / "captures",
            session=session,
            clock=lambda: NOW,
            api_key=KEY,
        )
    assert response.close_count == 1
    assert session.headers == {}


def test_owned_production_session_is_closed_before_publication(
    tmp_path, monkeypatch
):
    import scripts.capture_arv2_massive as module

    session = FakeSession(_success_responses())
    monkeypatch.setattr(module, "REPOSITORY_ARTIFACTS_ROOT", tmp_path)
    monkeypatch.setattr(module, "_new_session", lambda: session)
    monkeypatch.setenv("MASSIVE_API_KEY", "production-test-key-never-real")
    original_identity_check = module._require_pinned_child_identity

    def require_closed_at_publication(parent_fd, child, child_fd, name):
        if name == "published capture artifact":
            assert session.close_count == 1
        return original_identity_check(parent_fd, child, child_fd, name)

    monkeypatch.setattr(
        module, "_require_pinned_child_identity", require_closed_at_publication
    )
    loaded = capture_massive_history(
        requested_first_event_date=FIRST_DATE,
        requested_last_event_date=LAST_DATE,
        artifact_root=tmp_path / "captures",
    )
    manifest = json.loads((loaded.artifact_path / "manifest.json").read_bytes())
    assert session.close_count == 1
    assert session.headers == {}
    assert loaded.capture_transport == PRODUCTION_TRANSPORT
    assert manifest["capture_transport"] == PRODUCTION_TRANSPORT
    assert manifest["provider_io_read_only"] is True


def test_owned_production_session_close_failure_is_not_retried(
    tmp_path, monkeypatch
):
    import scripts.capture_arv2_massive as module

    class RaisingCloseSession(FakeSession):
        def close(self) -> None:
            self.close_count += 1
            raise RuntimeError("secret-bearing synthetic close detail")

    session = RaisingCloseSession(_success_responses())
    monkeypatch.setattr(module, "REPOSITORY_ARTIFACTS_ROOT", tmp_path)
    monkeypatch.setattr(module, "_new_session", lambda: session)
    monkeypatch.setenv("MASSIVE_API_KEY", "production-test-key-never-real")
    with pytest.raises(MassiveCaptureError, match="details redacted") as caught:
        capture_massive_history(
            requested_first_event_date=FIRST_DATE,
            requested_last_event_date=LAST_DATE,
            artifact_root=tmp_path / "captures",
        )
    assert "secret-bearing" not in str(caught.value)
    assert session.close_count == 1


def test_owned_production_session_closes_if_core_preflight_changes(
    tmp_path, monkeypatch
):
    import scripts.capture_arv2_massive as module

    session = FakeSession(_success_responses())
    original_validate = module._validated_capture_arguments
    validations = 0

    def refuse_second_validation(**kwargs):
        nonlocal validations
        validations += 1
        if validations == 2:
            raise MassiveCaptureError("synthetic core preflight failure")
        return original_validate(**kwargs)

    monkeypatch.setattr(module, "REPOSITORY_ARTIFACTS_ROOT", tmp_path)
    monkeypatch.setattr(module, "_new_session", lambda: session)
    monkeypatch.setattr(module, "_validated_capture_arguments", refuse_second_validation)
    monkeypatch.setenv("MASSIVE_API_KEY", "production-test-key-never-real")
    with pytest.raises(MassiveCaptureError, match="core preflight failure"):
        capture_massive_history(
            requested_first_event_date=FIRST_DATE,
            requested_last_event_date=LAST_DATE,
            artifact_root=tmp_path / "captures",
        )
    assert session.close_count == 1
    assert session.calls == []


def test_root_sync_failure_rolls_publication_back_to_hidden_staging(
    tmp_path, monkeypatch
):
    import scripts.capture_arv2_massive as module

    original_sync = module._fsync_fd

    def fail_root_sync(descriptor: int, name: str) -> None:
        if name == "capture root publication":
            raise MassiveCaptureError("synthetic root sync failure")
        original_sync(descriptor, name)

    monkeypatch.setattr(module, "_fsync_fd", fail_root_sync)
    with pytest.raises(MassiveCaptureError, match="synthetic root sync failure"):
        _capture(tmp_path, monkeypatch)
    entries = list((tmp_path / "captures").iterdir())
    assert len(entries) == 1
    assert entries[0].name.startswith(".") and entries[0].name.endswith(
        ".incomplete"
    )
    assert not any(entry.name.startswith("arv2-massive-three-role-") for entry in entries)
    with pytest.raises(MassiveCaptureError):
        load_massive_capture_artifact(entries[0])


def test_parent_directory_swap_cannot_redirect_page_writes(
    tmp_path, monkeypatch
):
    import scripts.capture_arv2_massive as module

    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    outside.chmod(0o700)
    original_write = module._exclusive_private_write_at
    swapped = False

    def swap_pages_then_write(
        parent_fd: int, filename: str, payload: bytes, name: str
    ) -> None:
        nonlocal swapped
        if not swapped:
            staging = next((tmp_path / "captures").glob(".*.incomplete"))
            pages = staging / "pages"
            pinned = staging / "pages-pinned"
            pages.rename(pinned)
            pages.symlink_to(outside, target_is_directory=True)
            swapped = True
        original_write(parent_fd, filename, payload, name)

    monkeypatch.setattr(module, "_exclusive_private_write_at", swap_pages_then_write)
    with pytest.raises(MassiveCaptureError, match="inventory|identity"):
        _capture(tmp_path, monkeypatch)
    assert swapped is True
    assert list(outside.iterdir()) == []
    assert not any(
        entry.name.startswith("arv2-massive-three-role-")
        for entry in (tmp_path / "captures").iterdir()
    )


def test_physical_bridge_builds_exhaustive_two_view_pair_without_raw_responses(
    tmp_path, monkeypatch
):
    loaded, _ = _capture(tmp_path, monkeypatch)
    bridge = _build_massive_accepted_risk_input_pair_for_test(
        loaded.artifact_path
    )

    assert require_massive_accepted_risk_bridge(bridge) is bridge
    assert type(bridge) is MassiveAcceptedRiskBridge
    assert bridge.physical_capture_id == loaded.capture.capture_id
    assert bridge.physical_capture_sha256 == loaded.capture.capture_sha256
    assert bridge.derived_capture_id == bridge.pair.capture.capture_id
    assert bridge.derived_capture_id != bridge.physical_capture_id
    assert bridge.source_page_count == 4
    assert bridge.source_row_count == 4
    assert len(bridge.pair.rows) == 4
    assert bridge.pair.report.total_row_count == 4
    assert tuple(role for role, _ in bridge.role_row_counts) == ROLE_ORDER
    assert all(
        page.raw_response_bytes is None for page in bridge.pair.capture.pages
    )
    assert bridge.physical_raw_extraction_authenticated is True
    assert bridge.raw_response_bytes_retained_in_pair is False
    assert bridge.pristine_point_in_time is False
    assert bridge.caller_completeness_claim_accepted is False
    assert bridge.filesystem_io_performed is True
    assert bridge.provider_io_performed is False
    assert bridge.credential_access_performed is False
    assert bridge.quantconnect_io_performed is False
    assert bridge.outcome_access_performed is False
    assert MAX_BRIDGE_SOURCE_PAYLOAD_PEAK_BYTES == 264 * 1024 * 1024


def test_physical_bridge_is_deterministic_for_the_same_capture(tmp_path, monkeypatch):
    loaded, _ = _capture(tmp_path, monkeypatch)
    first = _build_massive_accepted_risk_input_pair_for_test(
        loaded.artifact_path
    )
    second = _build_massive_accepted_risk_input_pair_for_test(
        loaded.artifact_path
    )
    assert second.bridge_id == first.bridge_id
    assert second.bridge_sha256 == first.bridge_sha256
    assert second.source_page_root_sha256 == first.source_page_root_sha256
    assert second.pair.pair_id == first.pair.pair_id
    assert second.pair.pair_sha256 == first.pair.pair_sha256


def test_public_bridge_refuses_offline_transport_and_has_no_injection_surface(
    tmp_path, monkeypatch
):
    import scripts.build_arv2_massive_input_pair as bridge_module

    loaded, _ = _capture(tmp_path, monkeypatch)
    monkeypatch.setattr(
        bridge_module._massive, "REPOSITORY_ARTIFACTS_ROOT", tmp_path
    )
    signature = inspect.signature(build_massive_accepted_risk_input_pair)
    assert tuple(signature.parameters) == ("artifact_path",)
    assert not {
        "api_key",
        "session",
        "clock",
        "complete",
        "trusted",
        "pristine_point_in_time",
    }.intersection(signature.parameters)
    with pytest.raises(MassiveInputPairBridgeError, match="transport"):
        build_massive_accepted_risk_input_pair(loaded.artifact_path)


def test_public_bridge_admits_only_production_marked_capture_beneath_artifacts(
    tmp_path, monkeypatch
):
    import scripts.build_arv2_massive_input_pair as bridge_module
    import scripts.capture_arv2_massive as capture_module

    session = FakeSession(_success_responses())
    monkeypatch.setattr(capture_module, "REPOSITORY_ARTIFACTS_ROOT", tmp_path)
    monkeypatch.setattr(capture_module, "_new_session", lambda: session)
    monkeypatch.setenv("MASSIVE_API_KEY", "production-test-key-never-real")
    loaded = capture_massive_history(
        requested_first_event_date=FIRST_DATE,
        requested_last_event_date=LAST_DATE,
        artifact_root=tmp_path / "captures",
    )
    monkeypatch.delenv("MASSIVE_API_KEY")
    monkeypatch.setattr(
        capture_module,
        "_api_key",
        lambda: pytest.fail("physical bridge must not reacquire the credential"),
    )
    assert bridge_module._massive is capture_module
    bridge = build_massive_accepted_risk_input_pair(loaded.artifact_path)
    assert require_massive_accepted_risk_bridge(bridge) is bridge
    assert bridge.capture_transport == PRODUCTION_TRANSPORT
    assert bridge.provider_io_performed is False
    assert bridge.credential_access_performed is False


def test_bridge_never_reads_a_credential_or_constructs_a_session(
    tmp_path, monkeypatch
):
    import scripts.build_arv2_massive_input_pair as bridge_module

    loaded, _ = _capture(tmp_path, monkeypatch)
    monkeypatch.setattr(
        bridge_module._massive,
        "_api_key",
        lambda: pytest.fail("bridge must not read a credential"),
    )
    monkeypatch.setattr(
        bridge_module._massive,
        "_new_session",
        lambda: pytest.fail("bridge must not construct a provider session"),
    )
    bridge = _build_massive_accepted_risk_input_pair_for_test(
        loaded.artifact_path
    )
    assert bridge.credential_access_performed is False
    assert bridge.provider_io_performed is False


def test_bridge_releases_raw_responses_before_pair_derivation(tmp_path, monkeypatch):
    import scripts.build_arv2_massive_input_pair as bridge_module

    loaded, _ = _capture(tmp_path, monkeypatch)
    real_builder = bridge_module.build_accepted_risk_input_pair
    calls = 0

    def assert_slim_then_build(capture):
        nonlocal calls
        calls += 1
        assert all(page.raw_response_bytes is None for page in capture.pages)
        return real_builder(capture)

    monkeypatch.setattr(
        bridge_module, "build_accepted_risk_input_pair", assert_slim_then_build
    )
    bridge = _build_massive_accepted_risk_input_pair_for_test(
        loaded.artifact_path
    )
    assert calls == 1
    assert bridge.source_row_count == 4


def test_bridge_unknown_rating_action_refuses_without_pair(tmp_path, monkeypatch):
    rating = _row("rating-unknown", role=ROLE_ORDER[0])
    rating["rating_action"] = "Clarifies"
    responses = [
        FakeResponse(_payload([rating]), _endpoint(ROLE_ORDER[0])),
        FakeResponse(
            _payload([_row("earnings-1", role=ROLE_ORDER[1])]),
            _endpoint(ROLE_ORDER[1]),
        ),
        FakeResponse(
            _payload([_row("guidance-1", role=ROLE_ORDER[2])]),
            _endpoint(ROLE_ORDER[2]),
        ),
    ]
    loaded, _ = _capture(tmp_path, monkeypatch, responses=responses)
    with pytest.raises(
        MassiveInputPairBridgeError, match="reviewed provider action"
    ):
        _build_massive_accepted_risk_input_pair_for_test(loaded.artifact_path)


def test_bridge_preserves_missing_id_and_later_touch_as_named_dispositions(
    tmp_path, monkeypatch
):
    missing_id = _row("placeholder", role=ROLE_ORDER[0])
    missing_id.pop("benzinga_id")
    later_touch = _row("rating-later-touch", role=ROLE_ORDER[0])
    later_touch["last_updated"] = "2021-01-07T13:30:00Z"
    responses = [
        FakeResponse(
            _payload([missing_id, later_touch]), _endpoint(ROLE_ORDER[0])
        ),
        FakeResponse(
            _payload([_row("earnings-1", role=ROLE_ORDER[1])]),
            _endpoint(ROLE_ORDER[1]),
        ),
        FakeResponse(
            _payload([_row("guidance-1", role=ROLE_ORDER[2])]),
            _endpoint(ROLE_ORDER[2]),
        ),
    ]
    loaded, _ = _capture(tmp_path, monkeypatch, responses=responses)
    bridge = _build_massive_accepted_risk_input_pair_for_test(
        loaded.artifact_path
    )
    first, second = bridge.pair.rows[:2]
    assert first.provider_event_id is None
    assert (
        first.current_view.disposition
        is RowDisposition.INVALID_PROVIDER_EVENT_ID
    )
    assert (
        first.censored_view.disposition
        is RowDisposition.INVALID_PROVIDER_EVENT_ID
    )
    assert second.current_view.included is True
    assert second.censored_view.included is False
    assert (
        second.censored_view.disposition
        is RowDisposition.CENSORED_LAST_TOUCH_AFTER_DECISION_CUTOFF
    )


@pytest.mark.parametrize(
    ("limit_name", "limit_value", "message"),
    [
        ("MAX_BRIDGE_PAGE_COUNT", 3, "page-count"),
        ("MAX_BRIDGE_ROW_COUNT", 3, "row-count"),
        ("MAX_BRIDGE_RETAINED_SOURCE_BYTES", 1, "retained-byte"),
        ("MAX_BRIDGE_PROVIDER_ROWS_BYTES", 1, "provider-row byte"),
    ],
)
def test_bridge_aggregate_caps_refuse_before_any_page_read(
    tmp_path, monkeypatch, limit_name, limit_value, message
):
    import scripts.build_arv2_massive_input_pair as bridge_module

    loaded, _ = _capture(tmp_path, monkeypatch)
    monkeypatch.setattr(bridge_module, limit_name, limit_value)
    real_read = bridge_module._massive._read_private_regular_at
    page_reads: list[str] = []

    def observe_read(parent_fd, filename, *, maximum_bytes, name):
        if name in {"raw response page", "canonical provider-row page"}:
            page_reads.append(name)
        return real_read(
            parent_fd, filename, maximum_bytes=maximum_bytes, name=name
        )

    monkeypatch.setattr(
        bridge_module._massive, "_read_private_regular_at", observe_read
    )
    with pytest.raises(MassiveInputPairBridgeError) as captured:
        _build_massive_accepted_risk_input_pair_for_test(loaded.artifact_path)
    assert message in str(captured.value.__cause__)
    assert page_reads == []


def test_bridge_per_row_cap_and_physical_tamper_refuse(tmp_path, monkeypatch):
    import scripts.build_arv2_massive_input_pair as bridge_module

    loaded, _ = _capture(tmp_path, monkeypatch)
    monkeypatch.setattr(bridge_module, "MAX_BRIDGE_ROW_BYTES", 32)
    with pytest.raises(MassiveInputPairBridgeError, match="row-byte budget"):
        _build_massive_accepted_risk_input_pair_for_test(loaded.artifact_path)

    monkeypatch.setattr(bridge_module, "MAX_BRIDGE_ROW_BYTES", 256 * 1024)
    manifest = json.loads((loaded.artifact_path / "manifest.json").read_bytes())
    raw_path = loaded.artifact_path / manifest["pages"][0]["raw_response_file"]
    raw_path.write_bytes(raw_path.read_bytes() + b" ")
    raw_path.chmod(0o600)
    with pytest.raises(MassiveInputPairBridgeError, match="authentication"):
        _build_massive_accepted_risk_input_pair_for_test(loaded.artifact_path)


def test_bridge_propagates_pagination_and_symlink_refusals(tmp_path, monkeypatch):
    loaded, _ = _capture(tmp_path, monkeypatch)
    _rewrite_manifest(
        loaded.artifact_path,
        lambda value: value["pages"][0].update(next_cursor_sha256="0" * 64),
    )
    with pytest.raises(MassiveInputPairBridgeError, match="authentication"):
        _build_massive_accepted_risk_input_pair_for_test(loaded.artifact_path)

    second, _ = _capture(tmp_path / "second", monkeypatch)
    manifest = json.loads((second.artifact_path / "manifest.json").read_bytes())
    row_path = second.artifact_path / manifest["pages"][0]["provider_rows_file"]
    saved = tmp_path / "saved-rows"
    row_path.rename(saved)
    try:
        row_path.symlink_to(saved)
    except OSError as exc:
        pytest.skip(f"host cannot create symlink: {exc}")
    with pytest.raises(MassiveInputPairBridgeError, match="authentication"):
        _build_massive_accepted_risk_input_pair_for_test(second.artifact_path)


def test_bridge_authority_rejects_forged_or_changed_instances(tmp_path, monkeypatch):
    loaded, _ = _capture(tmp_path, monkeypatch)
    bridge = _build_massive_accepted_risk_input_pair_for_test(
        loaded.artifact_path
    )
    forged = object.__new__(MassiveAcceptedRiskBridge)
    for field in dataclasses.fields(bridge):
        object.__setattr__(forged, field.name, getattr(bridge, field.name))
    with pytest.raises(MassiveInputPairBridgeError, match="builder-authenticated"):
        require_massive_accepted_risk_bridge(forged)
    object.__setattr__(bridge, "source_row_count", bridge.source_row_count + 1)
    with pytest.raises(MassiveInputPairBridgeError, match="builder-authenticated"):
        require_massive_accepted_risk_bridge(bridge)
