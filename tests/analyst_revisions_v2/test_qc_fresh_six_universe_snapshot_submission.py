"""Offline, behaviorally isolated boundaries for the R247 input-only QC launch."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.analyst_revisions_v2_qc import (
    fresh_six_universe_snapshot as snapshot,
    fresh_six_universe_snapshot_submission as subject,
)


def _plan(tmp_path: Path, attempt: int = 1):
    return subject.SnapshotQcPlan(
        organization_id="a" * 32,
        control_directory=tmp_path / "private",
        attempt=attempt,
    )


def _canonical(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    )


class FakeQc:
    """A deliberately small QC boundary fake; never opens a connection."""

    def __init__(self, plan):
        self.plan = plan
        self.calls: list[tuple[str, dict]] = []
        self.files = {"main.py": "# QC default\n", "research.ipynb": "{}"}
        self.project = None
        self.corrupt_readback = False
        self.status = "Completed."
        self.compile_reads = 0
        self.raw_meta = None
        canonical_sha = "b" * 64
        self.meta = {
            "schema": snapshot.SCHEMA,
            "object_store_key": snapshot.PREFIX + "2026-09-25/" + canonical_sha + ".json.gz",
            "canonical_sha256": canonical_sha,
            "compressed_sha256": "c" * 64,
            "canonical_byte_count": 20_000,
            "compressed_byte_count": 5_000,
        }

    def __call__(self, api, endpoint: str, payload: dict) -> dict:
        self.calls.append((endpoint, payload))
        result: dict = {"success": True}
        if endpoint == "projects/read":
            result["projects"] = [] if self.project is None else [self.project]
        elif endpoint == "projects/create":
            self.project = {
                "projectId": 247, "name": payload["name"],
                "organizationId": payload["organizationId"],
                "language": "Py", "owner": True, "codeRunning": False,
                "collaborators": [{"owner": True}],
            }
            result["projects"] = [self.project]
        elif endpoint == "files/read":
            result["files"] = [
                {
                    "projectId": 247, "name": name,
                    "content": content + (
                        "# mutated\n" if self.corrupt_readback and name == "main.py" else ""
                    ),
                }
                for name, content in self.files.items()
            ]
        elif endpoint == "files/delete":
            del self.files[payload["name"]]
        elif endpoint in {"files/create", "files/update"}:
            self.files[payload["name"]] = payload["content"]
        elif endpoint == "compile/create":
            result.update(projectId=247, compileId="compile-r247", state="InQueue")
        elif endpoint == "compile/read":
            self.compile_reads += 1
            result.update(
                projectId=247, compileId="compile-r247", state="BuildSuccess",
            )
        elif endpoint == "backtests/create":
            result["backtest"] = {
                "projectId": 247, "backtestId": "backtest-r247",
                "name": payload["backtestName"], "status": "In Queue...",
            }
        elif endpoint == "backtests/list":
            assert payload["includeStatistics"] is False
            result.update(count=1, backtests=[{
                "projectId": 247, "backtestId": "backtest-r247",
                "name": subject.BACKTEST_NAME, "status": self.status,
                "created": "2026-09-28 12:00:00",
                "sharpeRatio": "NEVER RETAIN THIS",
            }])
        elif endpoint == "backtests/read":
            result["backtest"] = {
                "projectId": 247, "backtestId": "backtest-r247",
                "name": subject.BACKTEST_NAME, "status": self.status,
                "statistics": {
                    "ARV2_FRESH_SIX_INPUT_META": (
                        _canonical(self.meta) if self.raw_meta is None else self.raw_meta
                    ),
                    "Net Profit": "NEVER RETAIN THIS",
                },
                "orders": [{"raw": "NEVER RETAIN THIS"}],
                "logs": ["NEVER RETAIN THIS"],
            }
        return result


def _offline_api(monkeypatch, fake):
    api = object()
    def check_client(observed):
        assert observed is api

    monkeypatch.setattr(subject, "_client", check_client)
    monkeypatch.setattr(subject, "_post", fake)
    return api


def test_preview_and_waiver_are_offline_and_bind_two_exact_sources(tmp_path):
    plan = _plan(tmp_path)
    preview = subject.preview_plan(plan)
    assert preview["quantconnect_io_performed"] is False
    assert [row["path"] for row in preview["source_files"]] == [
        "fresh_six_universe_snapshot.py", "main.py",
    ]
    assert all(row["bytes"] > 0 and len(row["sha256"]) == 64 for row in preview["source_files"])
    waiver = subject.render_owner_waiver_payload(plan)
    assert _canonical(json.loads(waiver)) == waiver.decode("ascii")
    assert b"2026-09-25" in waiver
    assert b"R247" in waiver
    assert plan.organization_id.encode("ascii") not in waiver
    assert not plan.control_directory.exists()


def test_missing_waiver_refuses_without_network_or_local_claim(monkeypatch, tmp_path):
    plan = _plan(tmp_path)
    fake = FakeQc(plan)
    api = _offline_api(monkeypatch, fake)
    with pytest.raises(subject.FreshSnapshotSubmissionError, match="waiver|authority"):
        subject.prepare_and_launch_once(plan, api)
    assert fake.calls == []
    assert not plan.control_directory.exists()


def test_out_of_scope_waiver_refuses_before_qc(monkeypatch, tmp_path):
    plan = _plan(tmp_path)
    fake = FakeQc(plan)
    api = _offline_api(monkeypatch, fake)
    with pytest.raises(subject.FreshSnapshotSubmissionError, match="waiver"):
        subject.prepare_and_launch_once(
            plan, api, owner_waiver_id=subject.WAIVER_ID + "-OTHER",
        )
    assert fake.calls == []
    assert not plan.control_directory.exists()


def test_exact_waiver_binds_one_input_only_launch(monkeypatch, tmp_path):
    plan = _plan(tmp_path)
    fake = FakeQc(plan)
    api = _offline_api(monkeypatch, fake)
    launch = subject.prepare_and_launch_once(
        plan, api, owner_waiver_id=subject.WAIVER_ID,
    )
    assert launch["owner_launch_authority_mode"] == "exact_exploratory_signature_waiver"
    assert launch["owner_launch_waiver_id"] == subject.WAIVER_ID
    assert [e for e, _ in fake.calls].count("backtests/create") == 1
    assert b"2026-09-25" in subject.render_owner_waiver_payload(plan)


def test_second_and_third_attempts_require_a_versioned_correction_before_qc(monkeypatch, tmp_path):
    for attempt in (2, 3, 4):
        plan = _plan(tmp_path, attempt)
        fake = FakeQc(plan)
        api = _offline_api(monkeypatch, fake)
        with pytest.raises(subject.FreshSnapshotSubmissionError, match="attempt|A1|version"):
            subject.prepare_and_launch_once(plan, api)
        assert fake.calls == []


def test_launch_creates_one_private_project_exact_two_files_and_one_backtest(
    monkeypatch, tmp_path,
):
    plan = _plan(tmp_path)
    fake = FakeQc(plan)
    api = _offline_api(monkeypatch, fake)
    launch = subject.prepare_and_launch_once(plan, api, owner_waiver_id=subject.WAIVER_ID)
    assert launch["project_id"] == 247
    assert launch["backtest_id"] == "backtest-r247"
    assert set(fake.files) == {"fresh_six_universe_snapshot.py", "main.py"}
    assert [e for e, _ in fake.calls].count("projects/create") == 1
    assert [e for e, _ in fake.calls].count("compile/create") == 1
    assert [e for e, _ in fake.calls].count("backtests/create") == 1
    assert [e for e, _ in fake.calls].count("files/read") >= 2
    prior = len(fake.calls)
    with pytest.raises(subject.FreshSnapshotSubmissionError, match="already|spent"):
        subject.prepare_and_launch_once(plan, api, owner_waiver_id=subject.WAIVER_ID)
    assert len(fake.calls) == prior


def test_existing_project_refused_before_mutation(monkeypatch, tmp_path):
    plan = _plan(tmp_path)
    fake = FakeQc(plan)
    fake.project = {"projectId": 999, "name": subject.PROJECT_NAME}
    api = _offline_api(monkeypatch, fake)
    with pytest.raises(subject.FreshSnapshotSubmissionError, match="fresh|project"):
        subject.prepare_and_launch_once(plan, api, owner_waiver_id=subject.WAIVER_ID)
    assert not any(endpoint in {"projects/create", "compile/create", "backtests/create"}
                   for endpoint, _ in fake.calls)


def test_corrupt_source_readback_consumes_attempt_without_compile(monkeypatch, tmp_path):
    plan = _plan(tmp_path)
    fake = FakeQc(plan)
    fake.corrupt_readback = True
    api = _offline_api(monkeypatch, fake)
    with pytest.raises(subject.FreshSnapshotSubmissionError, match="readback|source"):
        subject.prepare_and_launch_once(plan, api, owner_waiver_id=subject.WAIVER_ID)
    assert any(endpoint == "projects/create" for endpoint, _ in fake.calls)
    assert not any(endpoint in {"compile/create", "backtests/create"}
                   for endpoint, _ in fake.calls)
    assert any(plan.control_directory.iterdir())


def test_missing_default_main_refuses_before_file_mutation(monkeypatch, tmp_path):
    plan = _plan(tmp_path)
    fake = FakeQc(plan)
    fake.files.pop("main.py")
    api = _offline_api(monkeypatch, fake)
    with pytest.raises(subject.FreshSnapshotSubmissionError, match="default main"):
        subject.prepare_and_launch_once(plan, api, owner_waiver_id=subject.WAIVER_ID)
    assert not any(endpoint.startswith("files/") and endpoint != "files/read"
                   for endpoint, _ in fake.calls)
    assert not any(endpoint in {"compile/create", "backtests/create"}
                   for endpoint, _ in fake.calls)


def test_status_only_then_one_meta_read_ignores_unrelated_qc_result_fields(
    monkeypatch, tmp_path,
):
    plan = _plan(tmp_path)
    fake = FakeQc(plan)
    api = _offline_api(monkeypatch, fake)
    launch = subject.prepare_and_launch_once(plan, api, owner_waiver_id=subject.WAIVER_ID)
    assert subject.poll_status_once(plan, launch, api) == "Completed."
    assert [e for e, _ in fake.calls].count("backtests/read") == 0
    observed = subject.read_meta_once(plan, launch, api)
    assert observed["schema"] == snapshot.SCHEMA
    assert observed["canonical_sha256"] == "b" * 64
    assert "NEVER RETAIN THIS" not in repr(observed)
    assert [e for e, _ in fake.calls].count("backtests/read") == 1
    with pytest.raises(subject.FreshSnapshotSubmissionError, match="spent|already"):
        subject.read_meta_once(plan, launch, api)
    assert [e for e, _ in fake.calls].count("backtests/read") == 1


def test_invalid_meta_digest_is_refused_after_the_single_read(monkeypatch, tmp_path):
    plan = _plan(tmp_path)
    fake = FakeQc(plan)
    fake.meta["object_store_key"] = snapshot.PREFIX + "2026-09-25/" + "0" * 64 + ".json.gz"
    api = _offline_api(monkeypatch, fake)
    launch = subject.prepare_and_launch_once(plan, api, owner_waiver_id=subject.WAIVER_ID)
    assert subject.poll_status_once(plan, launch, api) == "Completed."
    with pytest.raises(subject.FreshSnapshotSubmissionError, match="digest|key|metadata"):
        subject.read_meta_once(plan, launch, api)
    assert [e for e, _ in fake.calls].count("backtests/read") == 1


def test_oversize_meta_is_refused_after_the_single_read(monkeypatch, tmp_path):
    plan = _plan(tmp_path)
    fake = FakeQc(plan)
    fake.raw_meta = "X" * (subject.MAX_META_BYTES + 1)
    api = _offline_api(monkeypatch, fake)
    launch = subject.prepare_and_launch_once(plan, api, owner_waiver_id=subject.WAIVER_ID)
    assert subject.poll_status_once(plan, launch, api) == "Completed."
    with pytest.raises(subject.FreshSnapshotSubmissionError, match="byte bound"):
        subject.read_meta_once(plan, launch, api)
    assert [e for e, _ in fake.calls].count("backtests/read") == 1


def test_exact_source_pin_detects_local_drift_before_qc(monkeypatch, tmp_path):
    plan = _plan(tmp_path)
    fake = FakeQc(plan)
    api = _offline_api(monkeypatch, fake)
    original = snapshot.main_source
    monkeypatch.setattr(snapshot, "main_source", lambda session: original(session) + "# drift\n")
    with pytest.raises(subject.FreshSnapshotSubmissionError, match="source|pin|identity"):
        subject.prepare_and_launch_once(plan, api, owner_waiver_id=subject.WAIVER_ID)
    assert fake.calls == []
