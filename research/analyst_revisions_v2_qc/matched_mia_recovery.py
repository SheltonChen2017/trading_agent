"""Read one independently launched Mia recovery; never add a Codex attempt.

The current-source API is not a historical snapshot-content API. A prelaunch
source attestation, matching current bytes and modification times, establishes
the narrower provenance available here. The three failed Codex receipts remain
unchanged. Only three bounded custom statistics are retained from the result.
"""

import dataclasses
import hashlib
from datetime import datetime

from . import six_universe_matched_study as study
from . import six_universe_relaxed_submission as adapter
from . import six_universe_settlement_submission as common


PROJECT_ID = 37017548
FAILED_A3_ID = "5e2255a7bb0e28f8cb404907551393a2"
SCHEMA = "arv2-r225-independent-mia-recovery-v1"
_FIELDS = frozenset({"schema", "candidate_id", "project_id", "backtest_id",
    "backtest_name", "snapshot_id", "created", "source_attested_at", "source_files"})


def _time(value):
    if type(value) is not str:
        adapter._fail("Mia recovery timestamp changed")
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError:
        adapter._fail("Mia recovery timestamp changed")
    # QC files/list timestamps share the documented offset-free time basis.
    if stamp.tzinfo is not None:
        adapter._fail("Mia recovery timestamp basis changed")
    return stamp


def _identity(plan, evidence, expected_evidence_sha256):
    if (type(plan) is not adapter.RelaxedQcPlan or plan.family != "matched_study"
            or plan.candidate_id != "R225" or type(plan.attempt) is not int
            or plan.attempt != 3):
        adapter._fail("Mia recovery requires exhausted R225 A3, not a new attempt")
    if (type(evidence) is not dict or set(evidence) != _FIELDS
            or type(expected_evidence_sha256) is not str
            or not adapter.cap._HEX.fullmatch(expected_evidence_sha256)
            or adapter._sha(evidence) != expected_evidence_sha256
            or evidence["schema"] != SCHEMA or evidence["candidate_id"] != "R225"
            or type(evidence["project_id"]) is not int or evidence["project_id"] != PROJECT_ID
            or type(evidence["backtest_id"]) is not str
            or not adapter.cap._ID.fullmatch(evidence["backtest_id"])
            or type(evidence["backtest_name"]) is not str or not evidence["backtest_name"]
            or type(evidence["snapshot_id"]) is not int or evidence["snapshot_id"] <= 0
            or _time(evidence["source_attested_at"]) > _time(evidence["created"])):
        adapter._fail("Mia recovery frozen identity changed")
    prior_ids = set()
    for slot in range(1, 4):
        prior_plan = dataclasses.replace(plan, attempt=slot)
        launch = common._read(adapter._path(prior_plan, "launch"))
        adapter._receipt(prior_plan, launch)
        terminal = common._read(adapter._path(prior_plan, "terminal"))
        expected = {"candidate_id": "R225", "attempt": slot, "project_id": PROJECT_ID,
            "backtest_id": launch["backtest_id"], "status": "Runtime Error"}
        if terminal != expected or launch["project_id"] != PROJECT_ID:
            adapter._fail("Mia recovery Codex failure census changed")
        prior_ids.add(launch["backtest_id"])
    if launch["backtest_id"] != FAILED_A3_ID or evidence["backtest_id"] in prior_ids:
        adapter._fail("Mia recovery cannot relabel a failed Codex run")
    source = evidence["source_files"]
    if (type(source) is not list or len(source) != 17
            or any(type(row) is not list or len(row) != 3
                or type(row[0]) is not str or not adapter.cap._PATH.fullmatch(row[0])
                or type(row[1]) is not str or not adapter.cap._HEX.fullmatch(row[1])
                or type(row[2]) is not int or not 0 < row[2] <= 64000 for row in source)
            or len({row[0] for row in source}) != 17 or source != sorted(source)):
        adapter._fail("Mia recovery source inventory changed")
    baseline = launch["source_files"]
    if ({row[0] for row in source} != {row[0] for row in baseline}
            or [row for row in source if row[0] != "main.py"]
                != [row for row in baseline if row[0] != "main.py"]
            or [row for row in source if row[0] == "main.py"]
                == [row for row in baseline if row[0] == "main.py"]):
        adapter._fail("Mia recovery must change only the attested main.py")
    return {"schema": SCHEMA, "candidate_id": "R225", "origin": "independent_Mia_recovery",
        "project_id": PROJECT_ID, "backtest_id": evidence["backtest_id"],
        "snapshot_id": evidence["snapshot_id"], "evidence_sha256": expected_evidence_sha256,
        "original_failed_A3_backtest_id": FAILED_A3_ID, "status": "Completed."}


def _path(plan, suffix):
    if suffix not in {"read-claim", "raw-custom", "result"}:
        adapter._fail("Mia recovery artifact name changed")
    # Reuse the existing private-directory enforcement, but never an A3 path.
    return adapter._path(plan, "claim").parent / f"R225-MIA-recovery-{suffix}.json"


def _source(plan, evidence, api):
    adapter._project(plan, api, PROJECT_ID)
    rows = common._post(api, "files/read", {"projectId": PROJECT_ID}).get("files")
    if type(rows) is not list or len(rows) != 17:
        adapter._fail("Mia recovery current source census changed")
    observed = []
    for row in rows:
        if (type(row) is not dict or row.get("projectId") != PROJECT_ID
                or type(row.get("name")) is not str or type(row.get("content")) is not str):
            adapter._fail("Mia recovery current source identity changed")
        try:
            raw = row["content"].encode("ascii")
        except UnicodeError:
            adapter._fail("Mia recovery source is not ASCII")
        if not 0 < len(raw) <= 64000:
            adapter._fail("Mia recovery source file exceeds the frozen projection bound")
        if _time(row.get("modified")) > _time(evidence["created"]):
            adapter._fail("Mia recovery current source was modified after run creation")
        observed.append([row["name"], hashlib.sha256(raw).hexdigest(), len(raw)])
    if sorted(observed) != evidence["source_files"]:
        adapter._fail("Mia recovery current source bytes changed")


def _run_matches(row, evidence, *, listing):
    identity = (type(row) is dict and row.get("projectId") == PROJECT_ID
        and row.get("backtestId") == evidence["backtest_id"]
        and row.get("name") == evidence["backtest_name"] and row.get("status") == "Completed.")
    if not identity:
        return False
    # Listing pins these fields before the read. The result endpoint does not
    # promise both fields; check them if supplied, never infer their contents.
    return ((not listing and "snapshotId" not in row or
            type(row.get("snapshotId")) is int and row["snapshotId"] == evidence["snapshot_id"])
        and (not listing and "created" not in row or row.get("created") == evidence["created"]))


def read_result_once(plan, evidence, expected_evidence_sha256, api):
    """Read-only QC import, with an atomic claim before the sole outcome read."""
    identity = _identity(plan, evidence, expected_evidence_sha256)
    if _path(plan, "read-claim").exists():
        adapter._fail("Mia recovery sole result read is already spent")
    common._client(api)
    _source(plan, evidence, api)
    listing = common._post(api, "backtests/list", {
        "projectId": PROJECT_ID, "includeStatistics": False})
    rows = listing.get("backtests")
    if (type(rows) is not list or listing.get("count", len(rows)) != len(rows)
            or any(type(row) is not dict for row in rows)):
        adapter._fail("Mia recovery run inventory changed")
    matches = [row for row in rows if row.get("backtestId") == evidence["backtest_id"]]
    if len(matches) != 1 or not _run_matches(matches[0], evidence, listing=True):
        adapter._fail("Mia recovery terminal run identity changed")
    common._write(_path(plan, "read-claim"), identity)
    response = common._post(api, "backtests/read", {
        "projectId": PROJECT_ID, "backtestId": evidence["backtest_id"]}).get("backtest")
    if not _run_matches(response, evidence, listing=False):
        adapter._fail("Mia recovery outcome run identity changed; sole read remains spent")
    statistics = response.get("statistics")
    names = adapter._candidate(plan)["statistic_names"]
    if (type(statistics) is not dict or sorted(key for key in statistics
            if type(key) is str and key.startswith("ARV2_SIX_GATE_ORDER_")) != sorted(names)):
        adapter._fail("Mia recovery custom statistic inventory changed")
    retained = {name: statistics[name] for name in names}
    for value in retained.values():
        adapter._statistic(value)
    adapter._write_artifact(_path(plan, "raw-custom"), {**identity, "statistics": retained})
    result = study.parse_order(plan, retained)
    adapter._write_artifact(_path(plan, "result"), {**identity, "parsed_result": result})
    return result


def authenticated_cached_result(plan, evidence, expected_evidence_sha256):
    """Reparse retained bounded statistics; never make another QC request."""
    identity = _identity(plan, evidence, expected_evidence_sha256)
    if common._read(_path(plan, "read-claim")) != identity:
        adapter._fail("Mia recovery cached read claim changed")
    raw = adapter._read_artifact(_path(plan, "raw-custom"))
    saved = adapter._read_artifact(_path(plan, "result"))
    if (set(raw) != set(identity) | {"statistics"}
            or {key: raw[key] for key in identity} != identity
            or set(saved) != set(identity) | {"parsed_result"}
            or {key: saved[key] for key in identity} != identity):
        adapter._fail("Mia recovery cached identity changed")
    result = study.parse_order(plan, raw["statistics"])
    if saved["parsed_result"] != result:
        adapter._fail("Mia recovery cached result differs from authenticated statistics")
    return result
