from __future__ import annotations

import ast
import hashlib
import json
from datetime import datetime
from pathlib import Path

import pytest

from research.analyst_revisions_v2_qc import pit_market_cap_membership_probe as v2_core
from research.analyst_revisions_v2_qc import pit_market_cap_membership_probe_v3 as core
from research.analyst_revisions_v2_qc import (
    pit_market_cap_membership_probe_runtime_v3 as runtime,
)
from tests.analyst_revisions_v2 import (
    test_qc_pit_market_cap_membership_probe_core as v2_fixtures,
)


REPOSITORY_ROOT = Path(__file__).parents[2]
V2_RUNTIME_PATH = (
    REPOSITORY_ROOT
    / "research"
    / "analyst_revisions_v2_qc"
    / "pit_market_cap_membership_probe_runtime.py"
)
V3_RUNTIME_PATH = (
    REPOSITORY_ROOT
    / "research"
    / "analyst_revisions_v2_qc"
    / "pit_market_cap_membership_probe_runtime_v3.py"
)


def _plan_and_projection():
    plan = core.build_pit_market_cap_membership_probe_plan_bytes(
        decision_sessions=v2_fixtures.SAMPLED_CANARY_SESSIONS,
        calculation_session="2026-09-15",
    )
    projection = core.build_pit_market_cap_membership_probe_qc_projection(
        plan_bytes=plan,
        runtime_source_bytes=V3_RUNTIME_PATH.read_bytes(),
    )
    return plan, projection


def _constants(projection):
    literal = projection.source_files[0].content.decode("ascii").split(
        "_C = json.loads(", 1
    )[1].split(")\n", 1)[0]
    return json.loads(ast.literal_eval(literal))


def _execute(monkeypatch):
    plan, projection = _plan_and_projection()
    fundamentals, constituents = v2_fixtures._fixture_rows()
    algorithm = v2_fixtures._Algorithm(
        projection.plan_object_store_key,
        plan,
        fundamentals,
        constituents,
    )
    monkeypatch.setattr(runtime, "CONTRACT_SHA256", core.CONTRACT_SHA256)
    runtime.execute_pit_market_cap_membership_probe(
        algorithm, _constants(projection)
    )
    pointer_bytes = algorithm.object_store.values[projection.terminal_pointer_key]
    pointer = json.loads(pointer_bytes)
    receipt_bytes = algorithm.object_store.values[pointer["receipt_key"]]
    reviewed_receipt = core.load_reviewed_pit_market_cap_membership_probe_receipt(
        plan_bytes=plan,
        projection=projection,
        terminal_pointer_bytes=pointer_bytes,
        receipt_bytes=receipt_bytes,
    )
    reviewed_attestation = (
        core.load_reviewed_pit_market_cap_membership_coverage_attestation(
            plan_bytes=plan,
            projection=projection,
            summary_bytes=algorithm._arv2_pit_coverage_summary.encode("ascii"),
        )
    )
    return (
        plan,
        projection,
        algorithm,
        json.loads(receipt_bytes),
        reviewed_receipt,
        reviewed_attestation,
    )


class _CountingIterable:
    def __init__(self, stop_after: int):
        self.stop_after = stop_after
        self.consumed = 0

    def __iter__(self):
        while self.consumed < self.stop_after:
            self.consumed += 1
            yield object()
        raise AssertionError("iterator was consumed beyond cap plus one")


class _CountingHistory:
    def __init__(self, stop_after: int):
        self.items_iterable = _CountingIterable(stop_after)

    def items(self):
        return self.items_iterable


def test_v3_lineage_is_fresh_and_preserves_exact_r082_v2_identities():
    v2_plan, v2_projection = v2_fixtures._plan_and_projection()
    assert hashlib.sha256(V2_RUNTIME_PATH.read_bytes()).hexdigest() == (
        "31cb92156b4cd5eaab8553e76f7f4002accde10e7ffe7eeabe0b57b369bb78cf"
    )
    assert hashlib.sha256(v2_plan).hexdigest() == (
        "b40f838ef3a6ddfd98f7b70f90d0e763c5736b2fbdeffe24886101d367cca833"
    )
    assert v2_projection.plan_sha256 == (
        "b38bf0a84b2b660b60c80a667344da44d265c51ddc1bc22bd999c2079b118762"
    )
    assert v2_projection.projection_sha256 == (
        "9f8d519fac6af6238e4440f1fd57b93c180e7f5fd2204c404dd61d45916d2c8f"
    )
    assert v2_projection.project_source_set_sha256 == (
        "f531416b629032d513605fffee951b52f94201eaf8ad4bce73dc741648d7ec78"
    )
    assert v2_projection.source_files[0].content_sha256 == (
        "0d4dcb0f9742915510e29c53823e889e707683cb520808fe759561675f1d4b73"
    )
    assert v2_projection.source_files[1].content_sha256 == (
        "8525dda0a5f683e4e31fe9ca71a290e8550117d20dedaa57f895c62422f0eab8"
    )
    assert v2_core.PROJECT_NAME.endswith("R082 - 20260917")
    assert v2_core.CONTRACT_SCHEMA.endswith("-v2")

    v3_plan, v3_projection = _plan_and_projection()
    assert core.CONTRACT_SCHEMA.endswith("-v3")
    assert core.PLAN_SCHEMA.endswith("-v3")
    assert core.RECEIPT_SCHEMA.endswith("-v3")
    assert core.ATTESTATION_SCHEMA.endswith("-v3")
    assert "R082" not in core.PROJECT_NAME
    assert v3_plan != v2_plan
    assert v3_projection.projection_sha256 != v2_projection.projection_sha256
    assert tuple(item.project_path for item in v3_projection.source_files) == (
        "main.py",
        "pit_market_cap_membership_probe_runtime_v3.py",
    )


def test_v3_history_collection_iterator_stops_at_cap_plus_one():
    history = _CountingHistory(runtime.MAX_COLLECTIONS_PER_CALL + 2)
    with pytest.raises(ValueError, match="exceeded the collection cap"):
        runtime._history_items(history, "hostile history")
    assert history.items_iterable.consumed == runtime.MAX_COLLECTIONS_PER_CALL + 1


@pytest.mark.parametrize(
    "consumer",
    (
        lambda rows: runtime._bounded_collection_rows(rows, "hostile rows"),
        runtime._fundamental_snapshot,
        runtime._constituent_snapshot,
    ),
)
def test_v3_row_iterators_stop_at_cap_plus_one(consumer):
    rows = _CountingIterable(runtime.MAX_COLLECTION_ROWS + 2)
    with pytest.raises(ValueError, match="row bound changed"):
        consumer(rows)
    assert rows.consumed == runtime.MAX_COLLECTION_ROWS + 1


def test_v3_post_open_fundamental_collection_refuses_behaviorally():
    """Pin the guard directly, without building or hash-checking a projection."""

    universe = v2_fixtures._Universe("FUNDAMENTALS")
    post_open = datetime(2025, 1, 6, 9, 30, 0, 1)

    class _Algorithm:
        _arv2_fundamental_universe = universe

        @staticmethod
        def history(observed_universe, _start, _end, *, flatten):
            assert observed_universe is universe
            assert flatten is False
            return v2_fixtures._History(
                {(universe.symbol, post_open): [object()]}
            )

    with pytest.raises(
        ValueError, match="Fundamentals collection was not observed before open"
    ):
        runtime._fundamental_inventory(
            _Algorithm(), datetime(2025, 1, 1), datetime(2025, 1, 7)
        )


def test_v3_emits_collection_availability_names_and_validates_them(monkeypatch):
    _, _, algorithm, receipt, reviewed_receipt, reviewed_attestation = _execute(
        monkeypatch
    )
    serialized = json.dumps(receipt, sort_keys=True)
    summary = json.loads(algorithm._arv2_pit_coverage_summary)

    assert "collection_end_time_local" not in serialized
    assert "collection_end_time_local" not in json.dumps(summary, sort_keys=True)
    assert all(
        set(row["etfs"][ticker])
        >= {"collection_availability_time_local"}
        for row in receipt["session_censuses"]
        for ticker in core.ETFS
    )
    assert all(
        set(summary["availability_extrema"]["etfs"][ticker])
        == {
            "earliest_collection_availability_time_local",
            "latest_collection_availability_time_local",
        }
        for ticker in core.ETFS
    )
    assert core.require_reviewed_pit_market_cap_membership_coverage_receipt(
        reviewed_receipt
    ) is reviewed_receipt
    assert core.require_reviewed_pit_market_cap_membership_coverage_attestation(
        reviewed_attestation
    ) is reviewed_attestation


def test_v3_selected_prior_takes_the_latest_strictly_prior_snapshot():
    """ARV2R93: pin latest-prior selection directly, independent of any hash pin."""

    cutoff = datetime(2025, 1, 6)
    inventory = {
        datetime(2025, 1, 2): ("oldest",),
        datetime(2025, 1, 4): ("latest-prior",),
        datetime(2025, 1, 6): ("at-cutoff",),
        datetime(2025, 1, 8): ("after-cutoff",),
    }

    key, rows = runtime._selected_prior(inventory, cutoff, "ETF history")

    assert key == datetime(2025, 1, 4)
    assert rows == ("latest-prior",)


def test_v3_selected_prior_refuses_when_only_cutoff_or_later_snapshots_exist():
    """A collection at the decision cutoff is not prior evidence."""

    cutoff = datetime(2025, 1, 6)
    inventory = {
        datetime(2025, 1, 6): ("at-cutoff",),
        datetime(2025, 1, 8): ("after-cutoff",),
    }

    with pytest.raises(ValueError, match="has no strictly prior snapshot"):
        runtime._selected_prior(inventory, cutoff, "ETF history")
