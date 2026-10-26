"""Offline isolation tests for the prospective captured-clock source pair."""

from __future__ import annotations

import gzip
import json
import sys
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import pytest

from research.analyst_revisions_v2_qc import fresh_six_universe_captured_clock as subject
from research.analyst_revisions_v2_qc import fresh_six_universe_clock_successor as r279_a1
from research.analyst_revisions_v2_qc import fresh_six_universe_clock_successor_a2 as r279_a2
from research.analyst_revisions_v2_qc import fresh_six_universe_snapshot_submission as r247


def _row(sid, *, cap=None, weight=None, end_time=None):
    return SimpleNamespace(
        symbol=SimpleNamespace(id=sid, value=sid),
        market_cap=cap,
        weight=weight,
        end_time=end_time or datetime(2026, 9, 28, 7),
    )


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


class _ConflictStore(_Store):
    def contains_key(self, _key):
        return True

    def read_bytes(self, _key):
        return b"different bytes at the content-addressed key"


class _FixedAlgorithm:
    def __init__(self, when=None, store=None):
        self.time = when or datetime(2026, 9, 28, 8, 30)
        self.object_store = store or _Store()
        self.statistics = {}

    def set_summary_statistic(self, key, value):
        self.statistics[key] = value


class _AdvancingAlgorithm:
    def __init__(self, values):
        self._clock_values = list(values)
        self.clock_read_count = 0
        self.object_store = _Store()
        self.statistics = {}

    @property
    def time(self):
        value = self._clock_values[self.clock_read_count]
        self.clock_read_count += 1
        return value

    def set_summary_statistic(self, key, value):
        self.statistics[key] = value


class _QcDatetime(datetime):
    """Representative Python-bridge datetime subtype."""


def _runtime(files):
    namespace = {}
    raw = dict(files)["fresh_six_universe_snapshot.py"]
    exec(compile(raw, "fresh_six_universe_snapshot.py", "exec"), namespace)
    return namespace


def _populate(namespace, algorithm):
    capture = namespace["FreshSixUniverseSnapshot"](algorithm, "2026-09-28")
    capture.accept("FUNDAMENTALS", [_row("SID-1", cap=100)])
    for ticker in namespace["ETFS"]:
        capture.accept(ticker, [_row("SID-1", weight=1)])
    return capture


def _algorithm_from_projected_source(files, values):
    """Load the generated class without importing QC or calling a service."""
    runtime_namespace = _runtime(files)
    runtime_module = ModuleType("fresh_six_universe_snapshot")
    runtime_module.__dict__.update(runtime_namespace)
    algorithm_imports = ModuleType("AlgorithmImports")
    algorithm_imports.QCAlgorithm = _AdvancingAlgorithm
    main_namespace = {}
    with patch.dict(
        sys.modules,
        {
            "AlgorithmImports": algorithm_imports,
            "fresh_six_universe_snapshot": runtime_module,
        },
    ):
        raw = dict(files)["main.py"]
        exec(compile(raw, "main.py", "exec"), main_namespace)
    algorithm_class = main_namespace["ARV2FreshSixInput"]
    algorithm = algorithm_class(values)
    algorithm._snapshot = _populate(runtime_namespace, algorithm)
    return algorithm_class, algorithm, runtime_namespace


def _manifest(files):
    return subject._digest(subject._canonical(subject._inventory(files)))


def test_projection_authenticates_exact_r279_a2_and_changes_only_clock_flow():
    parent = tuple(r279_a2._files())
    files = subject.project_source_files()
    before = dict(parent)
    after = dict(files)
    assert subject.PARENT_SOURCE_MANIFEST_SHA256 == r279_a2.SOURCE_MANIFEST_SHA256
    assert subject.PARENT_RUNTIME_SHA256 == r279_a2.RUNTIME_SHA256
    assert subject.PARENT_MAIN_SHA256 == r279_a1.MAIN_SHA256
    assert _manifest(parent) == subject.PARENT_SOURCE_MANIFEST_SHA256
    assert _manifest(files) == subject.SOURCE_MANIFEST_SHA256
    assert subject._digest(after["fresh_six_universe_snapshot.py"]) == subject.RUNTIME_SHA256
    assert subject._digest(after["main.py"]) == subject.MAIN_SHA256
    assert after["fresh_six_universe_snapshot.py"].count(
        b"def persist_at_decision(self, firing_time):"
    ) == 1
    assert b"decision = _clock_text(firing_time)" in after[
        "fresh_six_universe_snapshot.py"
    ]
    assert b"decision = _callback_time(self.algorithm)" not in after[
        "fresh_six_universe_snapshot.py"
    ]
    callback = after["main.py"].split(b"    def _at_decision(self):\n", 1)[1].split(
        b"\n    def on_end_of_algorithm", 1
    )[0]
    assert callback.count(b"self.time") == 1
    assert b"persist_at_decision(firing_time)" in callback
    assert b"_clock_text(firing_time)[:10]" in callback
    assert before == dict(r279_a2._files())


def test_projection_leaves_all_five_historical_manifests_and_bytes_unchanged():
    historical = [tuple(r247._files(attempt)) for attempt in (1, 2, 3)]
    historical.extend((tuple(r279_a1._files()), tuple(r279_a2._files())))
    expected = (
        r247.SOURCE_MANIFEST_SHA256,
        r247.SOURCE_MANIFEST_SHA256_A2,
        r247.SOURCE_MANIFEST_SHA256_A3,
        r279_a1.SOURCE_MANIFEST_SHA256,
        r279_a2.SOURCE_MANIFEST_SHA256,
    )
    frozen_bytes = tuple(historical)
    observed = tuple(_manifest(files) for files in historical)
    subject.project_source_files()
    assert observed == expected
    assert frozen_bytes == tuple(
        [tuple(r247._files(attempt)) for attempt in (1, 2, 3)]
        + [tuple(r279_a1._files()), tuple(r279_a2._files())]
    )


def test_advancing_scheduled_clock_is_red_historically_and_green_when_captured():
    # Seven source callbacks read 08:30. The scheduled callback then sees
    # 09:20, while a forbidden second property read would see 10:00.
    values = [datetime(2026, 9, 28, 8, 30)] * 7 + [
        datetime(2026, 9, 28, 9, 20),
        datetime(2026, 9, 28, 10),
    ]
    old_class, old_algorithm, old_runtime = _algorithm_from_projected_source(
        tuple(r279_a2._files()), values,
    )
    with pytest.raises(
        old_runtime["FreshSixUniverseSnapshotError"], match="decision cutoff changed",
    ):
        old_class._at_decision(old_algorithm)
    assert old_algorithm.clock_read_count == 9
    assert not old_algorithm.object_store.values
    assert not old_algorithm.statistics

    new_class, new_algorithm, _new_runtime = _algorithm_from_projected_source(
        subject.project_source_files(), values,
    )
    new_class._at_decision(new_algorithm)
    assert new_algorithm.clock_read_count == 8
    assert len(new_algorithm.object_store.values) == 1
    assert set(new_algorithm.statistics) == {"ARV2_FRESH_SIX_INPUT_META"}


def test_callback_rejects_invalid_captured_clock_before_date_selection():
    values = [datetime(2026, 9, 28, 8, 30)] * 7 + ["not-a-datetime"]
    algorithm_class, algorithm, runtime = _algorithm_from_projected_source(
        subject.project_source_files(), values,
    )
    with pytest.raises(
        runtime["FreshSixUniverseSnapshotError"], match="callback clock is unavailable",
    ):
        algorithm_class._at_decision(algorithm)
    assert algorithm.clock_read_count == 8
    assert not algorithm.object_store.values
    assert not algorithm.statistics


def test_clock_normalization_preserves_subtype_zone_and_frozen_second_resolution():
    runtime = _runtime(subject.project_source_files())
    algorithm = _FixedAlgorithm()
    capture = _populate(runtime, algorithm)
    # 13:20 UTC is 09:20 New York. Fractions retain the predecessor's
    # explicit timespec="seconds" contract; this is not subsecond strictness.
    firing_time = _QcDatetime(
        2026, 9, 28, 13, 20, 0, 999_999, tzinfo=timezone.utc,
    )
    receipt = capture.persist_at_decision(firing_time)
    body = json.loads(gzip.decompress(
        algorithm.object_store.values[receipt["object_store_key"]]
    ))
    assert body["qc_decision_time_ny"] == "2026-09-28T09:20:00-04:00"
    assert body["qc_callback_is_vendor_availability_time"] is False
    assert body["point_in_time_vendor_availability_proven"] is False
    assert body["decision_ready"] is False
    assert body["order_and_outcome_access"] is False


@pytest.mark.parametrize(
    "firing_time,reason",
    [
        ("2026-09-28T09:20:00", "callback clock is unavailable"),
        (datetime(2026, 9, 28, 9, 20, 1), "decision cutoff changed"),
        (datetime(2026, 9, 29, 9, 20), "decision cutoff changed"),
    ],
)
def test_invalid_or_late_captured_decision_clock_refuses_before_write(
    firing_time, reason,
):
    runtime = _runtime(subject.project_source_files())
    algorithm = _FixedAlgorithm()
    capture = _populate(runtime, algorithm)
    with pytest.raises(runtime["FreshSixUniverseSnapshotError"], match=reason):
        capture.persist_at_decision(firing_time)
    assert not algorithm.object_store.values
    assert not algorithm.statistics


def test_future_source_or_missing_source_still_refuses_without_persistence():
    runtime = _runtime(subject.project_source_files())
    algorithm = _FixedAlgorithm(datetime(2026, 9, 28, 8, 30))
    capture = runtime["FreshSixUniverseSnapshot"](algorithm, "2026-09-28")
    with pytest.raises(
        runtime["FreshSixUniverseSnapshotError"],
        match="source end time follows QC callback",
    ):
        capture.accept("FUNDAMENTALS", [
            _row("SID-1", cap=100, end_time=datetime(2026, 9, 28, 8, 31)),
        ])
    with pytest.raises(
        runtime["FreshSixUniverseSnapshotError"],
        match="required six-universe source is absent",
    ):
        capture.persist_at_decision(datetime(2026, 9, 28, 9, 20))
    assert not algorithm.object_store.values
    assert not algorithm.statistics


def test_object_store_key_integrity_and_false_authority_flags_are_preserved():
    runtime = _runtime(subject.project_source_files())
    algorithm = _FixedAlgorithm()
    capture = _populate(runtime, algorithm)
    receipt = capture.persist_at_decision(datetime(2026, 9, 28, 9, 20))
    assert receipt["object_store_key"].endswith(".gz")
    assert not receipt["object_store_key"].endswith(".json.gz")
    body = json.loads(gzip.decompress(
        algorithm.object_store.values[receipt["object_store_key"]]
    ))
    assert {
        "qc_callback_is_vendor_availability_time": False,
        "point_in_time_vendor_availability_proven": False,
        "decision_ready": False,
        "order_and_outcome_access": False,
    }.items() <= body.items()

    conflict_algorithm = _FixedAlgorithm(store=_ConflictStore())
    conflict_capture = _populate(runtime, conflict_algorithm)
    with pytest.raises(
        runtime["FreshSixUniverseSnapshotError"],
        match="content-addressed Object Store key conflicts",
    ):
        conflict_capture.persist_at_decision(datetime(2026, 9, 28, 9, 20))
    assert not conflict_algorithm.statistics


def test_parent_byte_anchor_and_projected_hash_drift_each_refuse(monkeypatch):
    parent = tuple(r279_a2._files())
    changed_parent = tuple(
        (path, raw.replace(subject._OLD_DECISION, b"        decision = 'changed'\n"))
        if path == "fresh_six_universe_snapshot.py" else (path, raw)
        for path, raw in parent
    )
    with pytest.raises(
        subject.FreshCapturedClockProjectionError,
        match="persistence decision clock anchor changed",
    ):
        subject._project_authenticated_parent(changed_parent)

    monkeypatch.setattr(
        subject,
        "_load_authenticated_parent_source",
        lambda: tuple(
            (path, raw + b"#changed\n") if path == "main.py" else (path, raw)
            for path, raw in parent
        ),
    )
    with pytest.raises(
        subject.FreshCapturedClockProjectionError, match="parent source identity changed",
    ):
        subject.project_source_files()


def test_projected_output_hash_drift_refuses_and_both_sources_compile(monkeypatch):
    files = subject.project_source_files()
    for path, raw in files:
        compile(raw, path, "exec")
    monkeypatch.setattr(subject, "MAIN_SHA256", "f" * 64)
    with pytest.raises(
        subject.FreshCapturedClockProjectionError,
        match="projected source identity changed",
    ):
        subject.project_source_files()


def test_projector_uses_only_the_parent_loader_and_refuses_malformed_parent(monkeypatch):
    parent = tuple(r279_a2._files())
    monkeypatch.setattr(subject, "_load_authenticated_parent_source", lambda: parent)
    monkeypatch.setattr(
        "builtins.open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("projector performed direct file I/O")
        ),
    )
    assert subject.project_source_files()

    monkeypatch.setattr(subject, "_load_authenticated_parent_source", lambda: None)
    with pytest.raises(
        subject.FreshCapturedClockProjectionError, match="parent source is unavailable",
    ):
        subject.project_source_files()
    monkeypatch.setattr(
        subject,
        "_load_authenticated_parent_source",
        lambda: (("fresh_six_universe_snapshot.py", "not-bytes"),
                 ("main.py", parent[1][1])),
    )
    with pytest.raises(
        subject.FreshCapturedClockProjectionError, match="parent file inventory changed",
    ):
        subject.project_source_files()


def test_preview_is_identity_only_and_exposes_no_transport_or_launch_surface():
    preview = subject.preview_projection()
    assert preview == {
        "schema": subject.SCHEMA,
        "parent_candidate_id": "R279",
        "parent_attempt": 2,
        "decision_session": "2026-09-28",
        "parent_source_manifest_sha256": subject.PARENT_SOURCE_MANIFEST_SHA256,
        "source_manifest_sha256": subject.SOURCE_MANIFEST_SHA256,
        "source_files": subject._inventory(subject.project_source_files()),
        "clock_reads_in_scheduled_callback": 1,
        "quantconnect_io_performed": False,
        "provider_io_performed": False,
        "order_and_outcome_access": False,
    }
    for forbidden in (
        "production_client", "prepare_and_launch_once", "poll_status_once",
        "read_meta_once", "render_owner_waiver_payload",
    ):
        assert not hasattr(subject, forbidden)
