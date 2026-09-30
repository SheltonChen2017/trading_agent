"""Offline, guard-specific R279 A2 same-project key correction tests."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import fresh_six_universe_clock_successor as a1
from research.analyst_revisions_v2_qc import fresh_six_universe_clock_successor_a2 as subject
from research.analyst_revisions_v2_qc import fresh_six_universe_snapshot as snapshot


ORG = "a" * 32


def _plan(tmp_path, attempt):
    return a1.FreshClockPlan(ORG, tmp_path / "private-control", attempt)


class _Qc:
    def __init__(self):
        self.calls = []
        self.project = None
        self.files = {"main.py": "# default\n", "research.ipynb": "{}"}
        self.runs = []
        self.status_by_id = {}
        self.meta = {
            "schema": snapshot.SCHEMA,
            "object_store_key": snapshot.PREFIX + "2026-09-28/" + "b" * 64 + ".gz",
            "canonical_sha256": "b" * 64,
            "compressed_sha256": "c" * 64,
            "canonical_byte_count": 20_000,
            "compressed_byte_count": 5_000,
        }
        self.corrupt_a2_readback = False
        self.public_on_a2_read = False

    def __call__(self, _api, endpoint, payload):
        self.calls.append((endpoint, payload))
        response = {"success": True}
        if endpoint == "projects/read":
            response["projects"] = [] if self.project is None else [{
                **self.project, "public": self.public_on_a2_read,
            }]
        elif endpoint == "projects/create":
            self.project = {
                "projectId": subject.PROJECT_ID,
                "name": payload["name"], "organizationId": payload["organizationId"],
                "language": "Py", "owner": True, "codeRunning": False,
                "public": False, "collaborators": [{"owner": True}],
            }
            response["projects"] = [self.project]
        elif endpoint == "files/read":
            response["files"] = [{
                "projectId": subject.PROJECT_ID, "name": name,
                "content": source + (
                    "#corrupt" if self.corrupt_a2_readback
                    and name == "fresh_six_universe_snapshot.py" else ""
                ),
            } for name, source in self.files.items()]
        elif endpoint == "files/delete":
            del self.files[payload["name"]]
        elif endpoint in {"files/create", "files/update"}:
            self.files[payload["name"]] = payload["content"]
        elif endpoint == "compile/create":
            response.update(compileId=f"compile-{len(self.runs) + 1}", projectId=subject.PROJECT_ID)
        elif endpoint == "compile/read":
            response.update(
                compileId=payload["compileId"], projectId=subject.PROJECT_ID,
                state="BuildSuccess",
            )
        elif endpoint == "backtests/create":
            run_id = (
                subject.PREDECESSOR_BACKTEST_ID if not self.runs else "a2-backtest-id"
            )
            run = {
                "projectId": subject.PROJECT_ID,
                "backtestId": run_id, "name": payload["backtestName"],
                "status": "In Queue...",
            }
            self.runs.append(run)
            self.status_by_id[run_id] = "In Queue..."
            response["backtest"] = run
        elif endpoint == "backtests/list":
            assert payload["includeStatistics"] is False
            response.update(count=len(self.runs), backtests=[
                {**row, "status": self.status_by_id[row["backtestId"]],
                 "Net Profit": "NEVER RETAIN"} for row in self.runs
            ])
        elif endpoint == "backtests/read":
            run = next(row for row in self.runs if row["backtestId"] == payload["backtestId"])
            response["backtest"] = {
                **run, "status": self.status_by_id[run["backtestId"]],
                "statistics": {
                    a1.META_NAME: a1._canonical(self.meta).decode("ascii"),
                    "Net Profit": "NEVER RETAIN",
                }, "orders": ["NEVER RETAIN"], "logs": ["NEVER RETAIN"],
            }
        return response


def _failed_a1(monkeypatch, tmp_path):
    fake = _Qc()
    monkeypatch.setattr(a1, "_post", fake)
    monkeypatch.setattr(a1, "_client", lambda _api: None)
    api = object()
    prior_plan = _plan(tmp_path, 1)
    prior = a1.prepare_and_launch_once(prior_plan, api, owner_waiver_id=a1.WAIVER_ID)
    fake.status_by_id[prior["backtest_id"]] = "Runtime Error"
    assert a1.poll_status_once(prior_plan, prior, api) == "Runtime Error"
    return fake, api


def test_a2_changes_only_unsupported_two_dot_key_and_pins_exact_source(tmp_path):
    before = dict(a1._files())
    after = dict(subject._files())
    old = snapshot.PREFIX + a1.DECISION_SESSION + "/" + "b" * 64 + ".json.gz"
    new = snapshot.PREFIX + a1.DECISION_SESSION + "/" + "b" * 64 + ".gz"
    assert subject._LEAN_KEY_RE.fullmatch(old) is None
    assert subject._LEAN_KEY_RE.fullmatch(new) is not None
    assert after["main.py"] == before["main.py"]
    assert after["fresh_six_universe_snapshot.py"] == before[
        "fresh_six_universe_snapshot.py"
    ].replace(subject._OLD_ANCHOR, subject._NEW_ANCHOR)
    assert before["fresh_six_universe_snapshot.py"].count(subject._OLD_ANCHOR) == 1
    assert a1._digest(after["fresh_six_universe_snapshot.py"]) == subject.RUNTIME_SHA256
    assert before == dict(a1._files())
    preview = subject.preview_plan(_plan(tmp_path, 2))
    assert preview["source_manifest_sha256"] == subject.SOURCE_MANIFEST_SHA256
    assert preview["predecessor_source_manifest_sha256"] == a1.SOURCE_MANIFEST_SHA256
    assert preview["project_id"] == subject.PROJECT_ID
    assert preview["implemented_attempts"] == [1, 2]
    assert not _plan(tmp_path, 2).control_directory.exists()


def test_a2_reverting_the_key_fix_reddens_before_any_qc(monkeypatch, tmp_path):
    monkeypatch.setattr(subject, "_NEW_ANCHOR", subject._OLD_ANCHOR)
    with pytest.raises(subject.FreshClockA2Error, match="anchor changed"):
        subject.preview_plan(_plan(tmp_path, 2))
    assert not _plan(tmp_path, 2).control_directory.exists()


def test_projected_runtime_persists_under_lean_key_grammar_where_a1_refuses():
    class GrammarStore:
        def __init__(self):
            self.values = {}

        def contains_key(self, key):
            return key in self.values

        def save_bytes(self, key, value):
            if subject._LEAN_KEY_RE.fullmatch(key) is None:
                raise ValueError("LocalObjectStore: path is not supported")
            self.values[key] = value
            return True

        def read_bytes(self, key):
            return self.values[key]

    def run(source):
        namespace = {}
        exec(compile(source, "fresh_six_universe_snapshot.py", "exec"), namespace)
        stats = {}
        store = GrammarStore()
        algo = SimpleNamespace(
            time=datetime(2026, 9, 28, 8, 30), object_store=store,
            set_summary_statistic=lambda key, value: stats.setdefault(key, value),
        )
        capture = namespace["FreshSixUniverseSnapshot"](algo, a1.DECISION_SESSION)
        def row(sid, *, cap=None, weight=None):
            return SimpleNamespace(
                symbol=SimpleNamespace(id=sid, value=sid),
                market_cap=cap, weight=weight,
                end_time=datetime(2026, 9, 28, 7),
            )
        capture.accept("FUNDAMENTALS", [row("SID-1", cap=100)])
        for ticker in snapshot.ETFS:
            capture.accept(ticker, [row("SID-1", weight=1)])
        algo.time = datetime(2026, 9, 28, 9, 20)
        return capture, store, stats

    prior = dict(a1._files())["fresh_six_universe_snapshot.py"]
    broken, prior_store, prior_stats = run(prior)
    with pytest.raises(ValueError, match="path is not supported"):
        broken.persist_at_decision()
    assert not prior_store.values and not prior_stats

    corrected = dict(subject._files())["fresh_six_universe_snapshot.py"]
    capture, store, stats = run(corrected)
    receipt = capture.persist_at_decision()
    assert receipt["object_store_key"].endswith(".gz")
    assert subject._LEAN_KEY_RE.fullmatch(receipt["object_store_key"]) is not None
    assert store.values[receipt["object_store_key"]]
    assert a1.META_NAME in stats


def test_a2_reuses_failed_a1_private_project_once_and_reads_only_meta(monkeypatch, tmp_path):
    fake, api = _failed_a1(monkeypatch, tmp_path)
    plan = _plan(tmp_path, 2)
    initial_mutations = [e for e, _ in fake.calls if e in {
        "projects/create", "files/update", "files/create", "compile/create", "backtests/create",
    }]
    launch = subject.prepare_and_launch_once(plan, api, owner_waiver_id=subject.WAIVER_ID)
    assert launch["project_id"] == subject.PROJECT_ID
    assert launch["predecessor_backtest_id"] == subject.PREDECESSOR_BACKTEST_ID
    assert launch["source_manifest_sha256"] == subject.SOURCE_MANIFEST_SHA256
    later_mutations = [e for e, _ in fake.calls if e in {
        "projects/create", "files/update", "files/create", "compile/create", "backtests/create",
    }][len(initial_mutations):]
    assert later_mutations == ["files/update", "compile/create", "backtests/create"]
    assert fake.files["main.py"].encode("ascii") == dict(a1._files())["main.py"]
    assert fake.files["fresh_six_universe_snapshot.py"].encode("ascii") == dict(subject._files())[
        "fresh_six_universe_snapshot.py"
    ]
    with pytest.raises(subject.FreshClockA2Error, match="already claimed"):
        subject.prepare_and_launch_once(plan, api, owner_waiver_id=subject.WAIVER_ID)
    fake.status_by_id[launch["backtest_id"]] = "Completed."
    assert subject.poll_status_once(plan, launch, api) == "Completed."
    assert subject.read_meta_once(plan, launch, api) == fake.meta
    assert [e for e, _ in fake.calls].count("backtests/read") == 1
    with pytest.raises(a1.FreshClockSubmissionError, match="spent"):
        subject.read_meta_once(plan, launch, api)
    assert [e for e, _ in fake.calls].count("backtests/read") == 1


@pytest.mark.parametrize("corruption", ["public", "source", "extra-run"])
def test_a2_refuses_changed_predecessor_before_claim_or_upload(monkeypatch, tmp_path, corruption):
    fake, api = _failed_a1(monkeypatch, tmp_path)
    if corruption == "public":
        fake.public_on_a2_read = True
    elif corruption == "source":
        fake.corrupt_a2_readback = True
    else:
        fake.runs.append({
            "projectId": subject.PROJECT_ID, "backtestId": "unexpected",
            "name": "unrelated", "status": "In Queue...",
        })
        fake.status_by_id["unexpected"] = "In Queue..."
    plan = _plan(tmp_path, 2)
    before = len(fake.calls)
    with pytest.raises(a1.FreshClockSubmissionError):
        subject.prepare_and_launch_once(plan, api, owner_waiver_id=subject.WAIVER_ID)
    assert not subject._path(plan, "claim").exists()
    assert not any(e in {"files/update", "compile/create", "backtests/create"}
                   for e, _ in fake.calls[before:])


def test_a2_runtime_error_refuses_result_read_and_old_two_dot_meta_refuses(monkeypatch, tmp_path):
    fake, api = _failed_a1(monkeypatch, tmp_path)
    plan = _plan(tmp_path, 2)
    launch = subject.prepare_and_launch_once(plan, api, owner_waiver_id=subject.WAIVER_ID)
    fake.status_by_id[launch["backtest_id"]] = "Runtime Error"
    assert subject.poll_status_once(plan, launch, api) == "Runtime Error"
    with pytest.raises(subject.FreshClockA2Error, match="did not complete"):
        subject.read_meta_once(plan, launch, api)
    assert [e for e, _ in fake.calls].count("backtests/read") == 0

    second_root = tmp_path / "second"
    second_root.mkdir()
    second_fake, second_api = _failed_a1(monkeypatch, second_root)
    second_plan = _plan(second_root, 2)
    second_launch = subject.prepare_and_launch_once(
        second_plan, second_api, owner_waiver_id=subject.WAIVER_ID,
    )
    second_fake.status_by_id[second_launch["backtest_id"]] = "Completed."
    assert subject.poll_status_once(second_plan, second_launch, second_api) == "Completed."
    second_fake.meta["object_store_key"] = second_fake.meta["object_store_key"][:-3] + ".json.gz"
    with pytest.raises(subject.FreshClockA2Error, match="identity, digest"):
        subject.read_meta_once(second_plan, second_launch, second_api)
    assert [e for e, _ in second_fake.calls].count("backtests/read") == 1
    assert not subject._path(second_plan, "result-valid").exists()


def test_a2_rejects_wrong_attempt_or_waiver_without_qc(tmp_path):
    for attempt in (1, 3, 4):
        with pytest.raises(subject.FreshClockA2Error, match="plan identity"):
            subject.preview_plan(_plan(tmp_path, attempt))
    with pytest.raises(subject.FreshClockA2Error, match="waiver"):
        subject._authority(_plan(tmp_path, 2), "wrong")
    assert not _plan(tmp_path, 2).control_directory.exists()
