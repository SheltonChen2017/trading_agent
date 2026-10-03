"""Isolating, offline tests for the separately versioned R279 A1 clock probe."""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import fresh_six_universe_clock_successor as subject
from research.analyst_revisions_v2_qc import fresh_six_universe_snapshot as snapshot
from research.analyst_revisions_v2_qc import fresh_six_universe_snapshot_submission as r247


ORG = "a" * 32


def _plan(tmp_path, attempt=1):
    return subject.FreshClockPlan(ORG, tmp_path / "private-control", attempt)


class _Store:
    def __init__(self):
        self.values = {}

    def contains_key(self, key):
        return key in self.values

    def save_bytes(self, key, value):
        self.values[key] = value
        return True

    def read_bytes(self, key):
        return self.values[key]


def _row(sid, *, cap=None, weight=None):
    return SimpleNamespace(
        symbol=SimpleNamespace(id=sid, value=sid), market_cap=cap,
        weight=weight, end_time=datetime(2026, 9, 28, 7),
    )


def test_a1_is_exactly_pinned_a3_runtime_with_one_clock_only_subscription(tmp_path):
    prior = dict(r247._files(3))
    files = dict(subject._files())
    main = files["main.py"].decode("ascii")
    assert files["fresh_six_universe_snapshot.py"] == prior["fresh_six_universe_snapshot.py"]
    assert prior == dict(r247._files(3))  # derivation never mutates R247
    assert "2026-09-25" not in main
    assert "2026-09-28" in main
    assert main.count("self.add_equity(") == 1
    assert "'SPY', Resolution.MINUTE, fill_forward=True," in main
    assert "extended_market_hours=True" in main
    assert "self.time_rules.at(9, 20)" in main
    assert "self._snapshot.persist_at_decision()" in main
    assert "self._snapshot.require_persisted()" in main
    for forbidden in (
        "self.history", "on_data", "market_order", "set_holdings",
        "self.portfolio", "self.securities[", "self._clock_symbol.price",
    ):
        assert forbidden not in main.lower()
    preview = subject.preview_plan(_plan(tmp_path))
    assert preview["source_manifest_sha256"] == subject.SOURCE_MANIFEST_SHA256
    assert preview["source_files"] == [
        {"path": path, "sha256": subject._digest(raw), "bytes": len(raw)}
        for path, raw in subject._files()
    ]
    assert preview["maximum_attempts_same_project"] == 3
    assert preview["implemented_attempts"] == [1]


@pytest.mark.parametrize("removed", [
    "Resolution.MINUTE", "extended_market_hours=True", "fill_forward=True",
    "self.time_rules.at(9, 20)",
])
def test_clock_subscription_and_exact_cutoff_are_each_source_pinned(monkeypatch, removed):
    original = subject._derived_files

    def changed():
        return tuple((name, raw.replace(removed.encode(), b"REMOVED", 1)
                      if name == "main.py" else raw) for name, raw in original())

    monkeypatch.setattr(subject, "_derived_files", changed)
    with pytest.raises(subject.FreshClockSubmissionError, match="source bytes changed"):
        subject._files()


def test_target_session_requires_exact_0920_and_seven_valid_sources():
    store = _Store()
    stats = {}
    algorithm = SimpleNamespace(
        time=datetime(2026, 9, 28, 8, 30), object_store=store,
        set_summary_statistic=lambda key, value: stats.setdefault(key, value),
    )
    capture = snapshot.FreshSixUniverseSnapshot(algorithm, subject.DECISION_SESSION)
    capture.accept("FUNDAMENTALS", [_row("SID-1", cap=100)])
    for ticker in snapshot.ETFS:
        capture.accept(ticker, [_row("SID-1", weight=1)])
    algorithm.time = datetime(2026, 9, 28, 10)
    with pytest.raises(snapshot.FreshSixUniverseSnapshotError, match="cutoff changed"):
        capture.persist_at_decision()
    assert store.values == {} and stats == {}
    algorithm.time = datetime(2026, 9, 28, 9, 20)
    receipt = capture.persist_at_decision()
    assert receipt["schema"] == snapshot.SCHEMA
    assert set(json.loads(stats[subject.META_NAME])) == {
        "schema", "object_store_key", "canonical_sha256", "compressed_sha256",
        "canonical_byte_count", "compressed_byte_count",
    }
    assert len(store.values) == 1


def test_a2_a3_and_wrong_waiver_refuse_before_any_client_or_control(tmp_path):
    for attempt in (2, 3, 4):
        with pytest.raises(subject.FreshClockSubmissionError, match="A1 only"):
            subject.preview_plan(_plan(tmp_path, attempt))
    with pytest.raises(subject.FreshClockSubmissionError, match="waiver"):
        subject._authority(_plan(tmp_path), "wrong")
    assert not (_plan(tmp_path).control_directory).exists()


class _FakeQc:
    def __init__(self):
        self.calls = []
        self.project_id = 279
        self.project = None
        self.files = {"main.py": "# default\n", "research.ipynb": "{}"}
        self.backtests = []
        self.status = "Completed."
        self.corrupt_readback = False
        self.project_public_on_read = False
        self.meta = {
            "schema": snapshot.SCHEMA,
            "object_store_key": snapshot.PREFIX + "2026-09-28/" + "b" * 64 + ".json.gz",
            "canonical_sha256": "b" * 64,
            "compressed_sha256": "c" * 64,
            "canonical_byte_count": 20_000,
            "compressed_byte_count": 5_000,
        }

    def __call__(self, _api, endpoint, payload):
        self.calls.append((endpoint, payload))
        response = {"success": True}
        if endpoint == "projects/read":
            response["projects"] = [] if self.project is None else [
                {**self.project, "public": self.project_public_on_read}]
        elif endpoint == "projects/create":
            self.project = {
                "projectId": self.project_id, "name": payload["name"],
                "organizationId": payload["organizationId"], "language": "Py",
                "owner": True, "codeRunning": False, "public": False,
                "collaborators": [{"owner": True}],
            }
            response["projects"] = [self.project]
        elif endpoint == "files/read":
            response["files"] = [
                {"projectId": self.project_id, "name": name,
                 "content": value + ("#corrupt" if self.corrupt_readback
                                        and name == "main.py" else "")}
                for name, value in self.files.items()
            ]
        elif endpoint == "files/delete":
            del self.files[payload["name"]]
        elif endpoint in {"files/update", "files/create"}:
            self.files[payload["name"]] = payload["content"]
        elif endpoint == "compile/create":
            response.update(compileId="compile-r279", projectId=self.project_id)
        elif endpoint == "compile/read":
            response.update(
                compileId=payload["compileId"], projectId=self.project_id,
                state="BuildSuccess",
            )
        elif endpoint == "backtests/create":
            launched = {
                "projectId": self.project_id, "backtestId": "backtest-r279",
                "name": payload["backtestName"], "status": "In Queue...",
            }
            self.backtests.append(launched)
            response["backtest"] = launched
        elif endpoint == "backtests/list":
            assert payload["includeStatistics"] is False
            response.update(count=len(self.backtests), backtests=[
                {**row, "status": self.status, "Net Profit": "NEVER RETAIN"}
                for row in self.backtests
            ])
        elif endpoint == "backtests/read":
            response["backtest"] = {
                **self.backtests[0], "status": self.status,
                "statistics": {
                    subject.META_NAME: subject._canonical(self.meta).decode("ascii"),
                    "Net Profit": "NEVER RETAIN",
                },
                "orders": ["NEVER RETAIN"], "logs": ["NEVER RETAIN"],
            }
        return response


def _offline(monkeypatch, fake):
    api = object()
    def check_client(observed):
        assert observed is api

    monkeypatch.setattr(subject, "_client", check_client)
    monkeypatch.setattr(subject, "_post", fake)
    return api


def test_one_use_a1_launch_exact_private_project_and_single_meta_read(monkeypatch, tmp_path):
    plan = _plan(tmp_path)
    fake = _FakeQc()
    api = _offline(monkeypatch, fake)
    launch = subject.prepare_and_launch_once(
        plan, api, owner_waiver_id=subject.WAIVER_ID,
    )
    assert launch["source_manifest_sha256"] == subject.SOURCE_MANIFEST_SHA256
    assert set(fake.files) == {"main.py", "fresh_six_universe_snapshot.py"}
    assert fake.files["main.py"].encode("ascii") == dict(subject._files())["main.py"]
    endpoints = [endpoint for endpoint, _ in fake.calls]
    assert endpoints.count("projects/create") == 1
    assert endpoints.count("backtests/create") == 1
    assert endpoints.count("backtests/read") == 0
    with pytest.raises(subject.FreshClockSubmissionError, match="claimed"):
        subject.prepare_and_launch_once(plan, api, owner_waiver_id=subject.WAIVER_ID)
    assert subject.poll_status_once(plan, launch, api) == "Completed."
    meta = subject.read_meta_once(plan, launch, api)
    assert meta == fake.meta
    assert [endpoint for endpoint, _ in fake.calls].count("backtests/read") == 1
    with pytest.raises(subject.FreshClockSubmissionError, match="spent"):
        subject.read_meta_once(plan, launch, api)
    assert [endpoint for endpoint, _ in fake.calls].count("backtests/read") == 1


def test_failed_run_has_no_meta_read_and_changed_source_consumes_attempt(monkeypatch, tmp_path):
    plan = _plan(tmp_path)
    fake = _FakeQc()
    api = _offline(monkeypatch, fake)
    launch = subject.prepare_and_launch_once(
        plan, api, owner_waiver_id=subject.WAIVER_ID,
    )
    fake.status = "Runtime Error"
    assert subject.poll_status_once(plan, launch, api) == "Runtime Error"
    with pytest.raises(subject.FreshClockSubmissionError, match="did not complete"):
        subject.read_meta_once(plan, launch, api)
    assert [endpoint for endpoint, _ in fake.calls].count("backtests/read") == 0

    second = subject.FreshClockPlan(ORG, tmp_path / "other-control")
    fake2 = _FakeQc()
    api2 = _offline(monkeypatch, fake2)
    fake2.corrupt_readback = True
    with pytest.raises(subject.FreshClockSubmissionError, match="readback"):
        subject.prepare_and_launch_once(
            second, api2, owner_waiver_id=subject.WAIVER_ID,
        )
    assert subject._path(second, "claim").exists()
    assert not any(endpoint in {"compile/create", "backtests/create"}
                   for endpoint, _ in fake2.calls)


def test_public_project_readback_refuses_before_any_source_upload(monkeypatch, tmp_path):
    fake = _FakeQc()
    fake.project_public_on_read = True
    api = _offline(monkeypatch, fake)
    plan = _plan(tmp_path)
    with pytest.raises(subject.FreshClockSubmissionError, match="project identity"):
        subject.prepare_and_launch_once(plan, api, owner_waiver_id=subject.WAIVER_ID)
    assert subject._path(plan, "claim").exists()
    assert not any(endpoint.startswith("files/") for endpoint, _ in fake.calls)
    assert not any(endpoint in {"compile/create", "backtests/create"}
                   for endpoint, _ in fake.calls)


def test_invalid_custom_statistic_spends_one_read_claim(monkeypatch, tmp_path):
    plan = _plan(tmp_path)
    fake = _FakeQc()
    api = _offline(monkeypatch, fake)
    launch = subject.prepare_and_launch_once(
        plan, api, owner_waiver_id=subject.WAIVER_ID,
    )
    assert subject.poll_status_once(plan, launch, api) == "Completed."
    fake.meta["canonical_sha256"] = "wrong"
    with pytest.raises(subject.FreshClockSubmissionError, match="identity, digest"):
        subject.read_meta_once(plan, launch, api)
    with pytest.raises(subject.FreshClockSubmissionError, match="spent"):
        subject.read_meta_once(plan, launch, api)
    assert [endpoint for endpoint, _ in fake.calls].count("backtests/read") == 1
