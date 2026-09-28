"""Offline, behaviorally isolated boundaries for the R247 input-only QC launch."""

from __future__ import annotations

import json
import sys
import types
from datetime import datetime
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
        self.corrupt_after_a2_update = False
        self.a2_main_updated = False
        self.status = "Completed."
        self.a2_status = "Completed."
        self.backtests: list[dict] = []
        self.compile_reads = 0
        self.compile_creates = 0
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
                        "# mutated\n" if name == "main.py" and (
                            self.corrupt_readback or (
                                self.corrupt_after_a2_update and self.a2_main_updated
                            )
                        ) else ""
                    ),
                }
                for name, content in self.files.items()
            ]
        elif endpoint == "files/delete":
            del self.files[payload["name"]]
        elif endpoint in {"files/create", "files/update"}:
            if endpoint == "files/update" and self.backtests:
                self.a2_main_updated = True
            self.files[payload["name"]] = payload["content"]
        elif endpoint == "compile/create":
            self.compile_creates += 1
            compile_id = (
                "compile-r247" if self.compile_creates == 1 else "compile-r247-a2"
            )
            result.update(projectId=247, compileId=compile_id, state="InQueue")
        elif endpoint == "compile/read":
            self.compile_reads += 1
            result.update(
                projectId=247, compileId=payload["compileId"], state="BuildSuccess",
            )
        elif endpoint == "backtests/create":
            backtest_id = (
                "backtest-r247" if not self.backtests else "backtest-r247-a2"
            )
            launched = {
                "projectId": 247, "backtestId": backtest_id,
                "name": payload["backtestName"], "status": "In Queue...",
            }
            self.backtests.append(launched)
            result["backtest"] = launched
        elif endpoint == "backtests/list":
            assert payload["includeStatistics"] is False
            rows = [
                {
                    **launched,
                    "status": (
                        self.status if launched["backtestId"] == "backtest-r247"
                        else self.a2_status
                    ),
                    "created": "2026-09-28 12:00:00",
                    "sharpeRatio": "NEVER RETAIN THIS",
                }
                for launched in self.backtests
            ]
            result.update(count=len(rows), backtests=rows)
        elif endpoint == "backtests/read":
            launched = next(
                row for row in self.backtests
                if row["backtestId"] == payload["backtestId"]
            )
            result["backtest"] = {
                "projectId": 247, "backtestId": launched["backtestId"],
                "name": launched["name"],
                "status": (
                    self.status if launched["backtestId"] == "backtest-r247"
                    else self.a2_status
                ),
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


def _failed_a1(monkeypatch, tmp_path):
    a1 = _plan(tmp_path)
    fake = FakeQc(a1)
    fake.status = "Runtime Error"
    api = _offline_api(monkeypatch, fake)
    launch = subject.prepare_and_launch_once(
        a1, api, owner_waiver_id=subject.WAIVER_ID,
    )
    assert subject.poll_status_once(a1, launch, api) == "Runtime Error"
    return _plan(tmp_path, 2), fake, api, launch


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


def test_unimplemented_third_and_fourth_attempts_require_a_versioned_correction_before_qc(
    monkeypatch, tmp_path,
):
    for attempt in (3, 4):
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


def test_a2_generated_main_changes_only_early_end_guard_and_preserves_target_end(
    monkeypatch,
):
    a1_files = dict(subject._files(1))
    a2_files = dict(subject._files(2))
    assert set(a2_files) == set(a1_files) == {
        "fresh_six_universe_snapshot.py", "main.py",
    }
    assert a2_files["fresh_six_universe_snapshot.py"] == a1_files[
        "fresh_six_universe_snapshot.py"
    ]
    a1_main = a1_files["main.py"].decode("ascii")
    a2_main = a2_files["main.py"].decode("ascii")
    a1_end = "    def on_end_of_algorithm(self):\n        self._snapshot.require_persisted()\n"
    a2_end = (
        "    def on_end_of_algorithm(self):\n"
        "        if self.time.date().isoformat() >= '2026-09-25':\n"
        "            self._snapshot.require_persisted()\n"
    )
    assert a1_main.count(a1_end) == 1
    assert a2_main == a1_main.replace(a1_end, a2_end)

    qc_imports = types.ModuleType("AlgorithmImports")
    qc_imports.QCAlgorithm = type("QCAlgorithm", (), {})
    monkeypatch.setitem(sys.modules, "AlgorithmImports", qc_imports)
    monkeypatch.setitem(sys.modules, "fresh_six_universe_snapshot", snapshot)
    namespace: dict[str, object] = {}
    exec(compile(a2_main, "R247-A2-main.py", "exec"), namespace)
    algorithm = namespace["ARV2FreshSixInput"]()
    calls = []

    class MissingSnapshot(Exception):
        pass

    def require_persisted():
        calls.append("required")
        raise MissingSnapshot

    algorithm._snapshot = types.SimpleNamespace(require_persisted=require_persisted)
    algorithm.time = datetime(2026, 9, 24, 23, 59)
    algorithm.on_end_of_algorithm()
    assert calls == []
    for ended_at in (datetime(2026, 9, 25), datetime(2026, 9, 26)):
        algorithm.time = ended_at
        with pytest.raises(MissingSnapshot):
            algorithm.on_end_of_algorithm()
    assert calls == ["required", "required"]


def test_a2_preview_and_waiver_bind_distinct_main_and_same_runtime(
    monkeypatch, tmp_path,
):
    a1 = subject.preview_plan(_plan(tmp_path))
    a2 = subject.preview_plan(_plan(tmp_path, 2))
    assert a2["attempt"] == 2
    assert a2["project_name"] == a1["project_name"]
    assert a2["backtest_name"] == subject.BACKTEST_NAME_A2
    assert a2["source_manifest_sha256"] != a1["source_manifest_sha256"]
    assert a2["source_files"][0] == a1["source_files"][0]
    assert a2["source_files"][1]["sha256"] != a1["source_files"][1]["sha256"]
    a2_plan, fake, _, _ = _failed_a1(monkeypatch, tmp_path)
    before = len(fake.calls)
    waiver = json.loads(subject.render_owner_waiver_payload(a2_plan))
    assert len(fake.calls) == before
    assert waiver["attempt"] == 2
    assert waiver["owner_launch_waiver_id"] == subject.WAIVER_ID_A2
    assert waiver["source_manifest_sha256"] == a2["source_manifest_sha256"]
    assert waiver["maximum_backtest_submissions_this_waiver"] == 1
    assert waiver["mutating_endpoint_budget"] == {
        "files/update": 1, "compile/create": 1, "backtests/create": 1,
        "projects/create": 0, "files/create": 0, "files/delete": 0,
    }


def test_a2_reuses_failed_a1_project_updates_only_main_and_launches_once(
    monkeypatch, tmp_path,
):
    a2, fake, api, a1_launch = _failed_a1(monkeypatch, tmp_path)
    before = len(fake.calls)
    launch = subject.prepare_and_launch_once(
        a2, api, owner_waiver_id=subject.WAIVER_ID_A2,
    )
    new_calls = fake.calls[before:]
    endpoints = [endpoint for endpoint, _ in new_calls]
    assert launch["attempt"] == 2
    assert launch["project_id"] == a1_launch["project_id"] == 247
    assert launch["backtest_name"] == subject.BACKTEST_NAME_A2
    assert launch["backtest_id"] != a1_launch["backtest_id"]
    assert launch["source_manifest_sha256"] != a1_launch["source_manifest_sha256"]
    assert launch["owner_launch_waiver_id"] == subject.WAIVER_ID_A2
    assert endpoints.count("files/update") == 1
    assert [payload["name"] for endpoint, payload in new_calls
            if endpoint == "files/update"] == ["main.py"]
    assert endpoints.count("compile/create") == 1
    assert endpoints.count("backtests/create") == 1
    assert not set(endpoints) & {"projects/create", "files/create", "files/delete"}
    assert endpoints.count("files/read") >= 2
    assert set(fake.files) == {"fresh_six_universe_snapshot.py", "main.py"}
    assert fake.files["main.py"].encode("ascii") == dict(subject._files(2))["main.py"]

    assert subject.poll_status_once(a2, launch, api) == "Completed."
    observed = subject.read_meta_once(a2, launch, api)
    assert observed["canonical_sha256"] == "b" * 64
    assert "NEVER RETAIN THIS" not in repr(observed)
    assert [endpoint for endpoint, _ in fake.calls].count("backtests/read") == 1
    with pytest.raises(subject.FreshSnapshotSubmissionError, match="spent|already"):
        subject.read_meta_once(a2, launch, api)
    after = len(fake.calls)
    with pytest.raises(subject.FreshSnapshotSubmissionError, match="already|spent"):
        subject.prepare_and_launch_once(
            a2, api, owner_waiver_id=subject.WAIVER_ID_A2,
        )
    assert len(fake.calls) == after


def test_a2_wrong_waiver_refuses_before_qc_and_claim(monkeypatch, tmp_path):
    a2, fake, api, _ = _failed_a1(monkeypatch, tmp_path)
    before = len(fake.calls)
    with pytest.raises(subject.FreshSnapshotSubmissionError, match="waiver"):
        subject.prepare_and_launch_once(a2, api, owner_waiver_id=subject.WAIVER_ID)
    assert len(fake.calls) == before
    assert not subject._path(a2, "claim").exists()


def test_a2_without_failed_a1_refuses_without_qc_or_claim(monkeypatch, tmp_path):
    a2 = _plan(tmp_path, 2)
    fake = FakeQc(a2)
    api = _offline_api(monkeypatch, fake)
    with pytest.raises(subject.FreshSnapshotSubmissionError, match="A1|control"):
        subject.prepare_and_launch_once(
            a2, api, owner_waiver_id=subject.WAIVER_ID_A2,
        )
    assert fake.calls == []
    assert not subject._path(a2, "claim").exists()


def test_a2_requires_prior_runtime_error_before_any_mutation(monkeypatch, tmp_path):
    a1 = _plan(tmp_path)
    fake = FakeQc(a1)
    api = _offline_api(monkeypatch, fake)
    launch = subject.prepare_and_launch_once(
        a1, api, owner_waiver_id=subject.WAIVER_ID,
    )
    assert subject.poll_status_once(a1, launch, api) == "Completed."
    a2 = _plan(tmp_path, 2)
    before = len(fake.calls)
    with pytest.raises(subject.FreshSnapshotSubmissionError, match="A1|Runtime Error|terminal"):
        subject.prepare_and_launch_once(
            a2, api, owner_waiver_id=subject.WAIVER_ID_A2,
        )
    assert not {endpoint for endpoint, _ in fake.calls[before:]} & {
        "files/update", "compile/create", "backtests/create",
    }
    assert not subject._path(a2, "claim").exists()


def test_a2_refuses_unexpected_cloud_run_before_claim(monkeypatch, tmp_path):
    a2, fake, api, _ = _failed_a1(monkeypatch, tmp_path)
    fake.backtests.append({
        "projectId": 247, "backtestId": "unexpected-cloud-run",
        "name": "unrelated run", "status": "In Queue...",
    })
    before = len(fake.calls)
    with pytest.raises(subject.FreshSnapshotSubmissionError, match="inventory|status"):
        subject.prepare_and_launch_once(
            a2, api, owner_waiver_id=subject.WAIVER_ID_A2,
        )
    assert not {endpoint for endpoint, _ in fake.calls[before:]} & {
        "files/update", "compile/create", "backtests/create",
    }
    assert not subject._path(a2, "claim").exists()


def test_a2_refuses_changed_a1_cloud_source_before_claim_or_update(monkeypatch, tmp_path):
    a2, fake, api, _ = _failed_a1(monkeypatch, tmp_path)
    fake.files["main.py"] += "# changed after A1\n"
    before = len(fake.calls)
    with pytest.raises(subject.FreshSnapshotSubmissionError, match="A1|source|readback"):
        subject.prepare_and_launch_once(
            a2, api, owner_waiver_id=subject.WAIVER_ID_A2,
        )
    assert not {endpoint for endpoint, _ in fake.calls[before:]} & {
        "files/update", "compile/create", "backtests/create",
    }
    assert not subject._path(a2, "claim").exists()


def test_a2_changed_upload_readback_spends_claim_without_compile(monkeypatch, tmp_path):
    a2, fake, api, _ = _failed_a1(monkeypatch, tmp_path)
    fake.corrupt_after_a2_update = True
    before = len(fake.calls)
    with pytest.raises(subject.FreshSnapshotSubmissionError, match="readback|source"):
        subject.prepare_and_launch_once(
            a2, api, owner_waiver_id=subject.WAIVER_ID_A2,
        )
    endpoints = [endpoint for endpoint, _ in fake.calls[before:]]
    assert endpoints.count("files/update") == 1
    assert "compile/create" not in endpoints
    assert "backtests/create" not in endpoints
    assert subject._path(a2, "claim").exists()
    after = len(fake.calls)
    with pytest.raises(subject.FreshSnapshotSubmissionError, match="already|spent"):
        subject.prepare_and_launch_once(
            a2, api, owner_waiver_id=subject.WAIVER_ID_A2,
        )
    assert len(fake.calls) == after


def test_a2_completed_without_snapshot_meta_is_not_accepted(monkeypatch, tmp_path):
    a2, fake, api, _ = _failed_a1(monkeypatch, tmp_path)
    launch = subject.prepare_and_launch_once(
        a2, api, owner_waiver_id=subject.WAIVER_ID_A2,
    )
    assert subject.poll_status_once(a2, launch, api) == "Completed."
    fake.raw_meta = ""
    with pytest.raises(subject.FreshSnapshotSubmissionError, match="metadata|byte bound"):
        subject.read_meta_once(a2, launch, api)
    assert [endpoint for endpoint, _ in fake.calls].count("backtests/read") == 1
    with pytest.raises(subject.FreshSnapshotSubmissionError, match="spent|already"):
        subject.read_meta_once(a2, launch, api)
