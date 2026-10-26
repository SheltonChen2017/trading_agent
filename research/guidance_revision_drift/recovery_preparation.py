"""Offline custody of one exhausted legacy cycle, never recovery authority.

The retained operational JSONL is not a typed CycleJournal. Its caller-retained
raw hash detects alteration, not provenance or rollback if that anchor is also
lost. IDs, statuses and the historical waiver are supplied observations. New
package/review identities cannot erase the three failures or enable a launch.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from data.hashing import hash_bytes, hash_payload
from research.guidance_revision_drift.contracts import CandidateError, CANDIDATE_SHA256, _decode
from research.guidance_revision_drift.evaluation import (
    EvaluationError, FIXTURE_SHA256, _clock, _fields, _hash, _identifier, _version,
)
from research.guidance_revision_drift.persistence import canonical_object, decode_object


HISTORICAL_CYCLE_ID = "GDR-base372-approved-20261008"
HISTORICAL_PUBLICATION_COMMIT = "75ea62804ed9da5d0935cd74470ffe7ef7ad8b5f"
MAX_LEGACY_BYTES = 262_144
MAX_LEGACY_RECORDS = 512
MAX_LEGACY_LINE_BYTES = 65_536
RECOVERY_IDENTITY_FIELDS = frozenset({
    "source_manifest_sha256", "project_sha256", "bundle_sha256", "runtime_source_sha256",
    "native_audit_source_sha256", "fixture_sha256", "candidate_sha256",
})
_CONTEXT_FIELDS = {"bundle_sha256", "candidate_sha256", "fixture_sha256", "runtime_source_sha256"}
_COMMON = {"at", "kind"}
# This is the closed legacy file's observed vocabulary, not an extensible event
# writer. Ancillary events are retained in full bytes, never silently removed.
_FIELDS = {
    "authorization": {"cycle", "empirical_allowed", "external_human_authorization",
        "installations_allowed", "maximum_unsuccessful_attempts", "producing_source_commit",
        "projectId", "project_sha256", "real_data_allowed", "review_commit",
        "review_waived_by_owner", "runtime_context", "source_commit", "source_manifest_sha256"},
    "compile_intent": {"attempt", "project_sha256", "source_manifest_sha256"},
    "compile_ack": {"attempt", "compileId", "signature", "signatureOrder", "state"},
    "compile_observation": {"attempt", "compileId", "errors", "logs", "state"},
    "run_intent": {"attempt", "backtestName", "compileId"},
    "run_ack": {"attempt", "backtestId", "status"},
    "run_observation": {"attempt", "backtestId", "completed", "error", "hasInitializeError",
        "progress", "serverStatistics", "stacktrace", "status"},
    "terminal": {"attempt", "backtestId", "status", "unsuccessful"},
    "source_epoch": {"attempt", "external_owner_waiver_retained", "project_sha256",
        "runtime_context", "source_commit", "source_manifest_sha256"},
    "attempt_ceiling": {"candidate_edits_stopped", "manual_relaunch_allowed", "unsuccessful"},
    "response": {"endpoint", "file", "http_status", "raw_response_sha256"},
    "cloud_exact": {"cloud_edits", "label", "project_sha256", "python_files", "source_manifest_sha256"},
    "coding_ide_running_handoff": {"codeRunning", "mia_status", "previous_native_attempt", "previous_native_terminal"},
    "file_write_ack": {"name"}, "file_write_intent": {"endpoint", "name", "sha256"},
    "mia_diagnostic_complete": {"launches", "proposed_normalization_accepted", "recommendation", "source_edits"},
    "mia_diagnostic_request": {"failed_attempts", "launches_prohibited", "mode", "projectId", "source_edits_prohibited"},
    "node_observation": {"autoSelectNode", "available", "nodes"},
    "project_config": {"leanEnvironment", "leanPinnedToMaster", "leanVersionId", "maxFileSize", "projectId", "versions"},
    "source_inventory": {"files", "folder", "label"},
    "ui_build_observation": {"backtest_launched", "cause", "displayed_id", "engine", "full_compile_id", "state"},
}


def _git_sha(value: object) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise EvaluationError("exact supplied commit SHA required")
    return value


def _context(body: object) -> dict:
    _fields(body, _CONTEXT_FIELDS)
    for value in body.values():
        _hash(value)
    if body["candidate_sha256"] != CANDIDATE_SHA256 or body["fixture_sha256"] != FIXTURE_SHA256:
        raise EvaluationError("historical closure requires the original fixed synthetic candidate/fixture")
    return dict(body)


def _legacy_records(raw: bytes, retained: str) -> list[dict]:
    _hash(retained)
    if type(raw) is not bytes or not raw or len(raw) > MAX_LEGACY_BYTES:
        raise EvaluationError("bounded complete legacy event bytes required")
    if hash_bytes(raw) != retained:
        raise EvaluationError("legacy events differ from caller-retained raw SHA-256")
    if not raw.endswith(b"\n") or b"\r" in raw:
        raise EvaluationError("complete LF-delimited historical events required")
    lines = raw[:-1].split(b"\n")
    if not 1 <= len(lines) <= MAX_LEGACY_RECORDS:
        raise EvaluationError("bounded historical event count required")
    rows, previous_at = [], None
    for line in lines:
        if not line or len(line) > MAX_LEGACY_LINE_BYTES:
            raise EvaluationError("nonempty bounded historical line required")
        try:
            row = _decode(line)
        except CandidateError as exc:
            raise EvaluationError("strict historical JSON object required") from exc
        kind = row.get("kind")
        if type(kind) is not str or kind not in _FIELDS:
            raise EvaluationError("unknown historical event kind")
        fields = _COMMON | _FIELDS[kind]
        if kind == "project_config" and "codeRunning" in row:
            fields = fields | {"codeRunning"}
        if kind == "response" and ("retention" in row or "retained_sha256" in row):
            fields = fields | {"retention", "retained_sha256"}
            _hash(row.get("retained_sha256"))
        _fields(row, fields)
        instant = _clock(row["at"])
        if previous_at is not None and instant < previous_at:
            raise EvaluationError("historical observation timestamps regressed")
        previous_at = instant
        rows.append(row)
    return rows


def _receipt(rows: list[dict], index: int, endpoint: str) -> dict:
    if index == 0:
        raise EvaluationError("historical platform observation lacks retained response")
    response = rows[index - 1]
    if (response["kind"] != "response" or response["endpoint"] != endpoint
            or type(response["http_status"]) is not int or response["http_status"] != 200
            or type(response["file"]) is not str
            or re.fullmatch(r"[0-9a-f]{32}\.json", response["file"]) is None):
        raise EvaluationError("historical platform observation differs from response lineage")
    return {"raw_response_sha256": _hash(response["raw_response_sha256"]),
            "observed_at": response["at"], "response_file": response["file"]}


def _replay(rows: list[dict]) -> dict:
    attempts, authorization, epoch, ceiling = [], None, None, None
    compile_ids, run_ids = set(), set()
    create_responses = {"compile/create": 0, "backtests/create": 0}
    order = ("compile_ack", "compile_observation", "run_intent", "run_ack", "run_observation", "terminal")
    for index, event in enumerate(rows):
        kind = event["kind"]
        if ceiling is not None and (kind in {"file_write_ack", "file_write_intent"}
                or (kind == "response" and event["endpoint"] in create_responses)):
            raise EvaluationError("historical ceiling cannot be followed by edits or launch responses")
        if kind == "response" and event["endpoint"] in create_responses:
            create_responses[event["endpoint"]] += 1
        if kind == "authorization":
            if authorization is not None or attempts or event["cycle"] != HISTORICAL_CYCLE_ID:
                raise EvaluationError("one exact historical cycle anchor required")
            if (type(event["maximum_unsuccessful_attempts"]) is not int
                    or event["maximum_unsuccessful_attempts"] != 3
                    or event["review_commit"] is not None or event["review_waived_by_owner"] is not True
                    or any(event[name] is not False for name in
                           ("empirical_allowed", "installations_allowed", "real_data_allowed"))
                    or type(event["projectId"]) is not int or not 1 <= event["projectId"] < 2 ** 63):
                raise EvaluationError("historical waiver/closed permissions cannot be replaced")
            _git_sha(event["producing_source_commit"])
            authorization = event
            epoch = event
        elif kind == "source_epoch":
            if (authorization is None or not attempts or attempts[-1]["status"] != "failed"
                    or type(event["attempt"]) is not int or event["attempt"] != len(attempts) + 1
                    or event["attempt"] > 3 or event["external_owner_waiver_retained"] is not True
                    or epoch is not attempts[-1]["_epoch"]):
                raise EvaluationError("historical source epoch is missing, duplicated or reordered")
            if _context(event["runtime_context"]) != _context(authorization["runtime_context"]):
                raise EvaluationError("historical runtime candidate/fixture changed")
            epoch = event
        elif kind == "compile_intent":
            if (authorization is None or ceiling is not None or len(attempts) >= 3
                    or type(event["attempt"]) is not int or event["attempt"] != len(attempts) + 1
                    or (attempts and attempts[-1]["status"] != "failed")
                    or (attempts and epoch is attempts[-1]["_epoch"])):
                raise EvaluationError("exactly three ordered failed historical launch intents required")
            for name in ("source_manifest_sha256", "project_sha256"):
                if _hash(event[name]) != _hash(epoch[name]):
                    raise EvaluationError("launch intent differs from its exact historical source epoch")
            attempts.append({"attempt": event["attempt"], "source_commit": _git_sha(epoch["source_commit"]),
                "source_manifest_sha256": event["source_manifest_sha256"], "project_sha256": event["project_sha256"],
                "runtime_context": _context(epoch["runtime_context"]), "intent_at": event["at"],
                "status": "pending", "_epoch": epoch, "_stage": 0,
                "review_commit": None, "binding_version": None})
        elif kind in order:
            if (not attempts or ceiling is not None or type(event["attempt"]) is not int
                    or event["attempt"] != len(attempts)):
                raise EvaluationError("historical observation has no matching launch intent")
            row = attempts[-1]
            if row["_stage"] >= len(order) or kind != order[row["_stage"]]:
                raise EvaluationError("historical compile/run/terminal observation duplicated or reordered")
            row["_stage"] += 1
            if kind == "compile_ack":
                compile_id = _identifier(event["compileId"])
                if compile_id in compile_ids or event["state"] != "InQueue":
                    raise EvaluationError("compile acknowledgement reused or invalid")
                compile_ids.add(compile_id)
                row["compile_id"] = compile_id
                row["compile_request_receipt"] = _receipt(rows, index, "compile/create")
            elif kind == "compile_observation":
                if (event["compileId"] != row["compile_id"] or event["state"] != "BuildSuccess"
                        or event["errors"] is not None):
                    raise EvaluationError("historical successful compile lineage differs")
                row["compile_status"] = event["state"]
                row["compile_output_receipt"] = _receipt(rows, index, "compile/read")
            elif kind == "run_intent":
                if event["compileId"] != row["compile_id"]:
                    raise EvaluationError("historical run differs from successful compile")
                row["run_intent_at"] = event["at"]
            elif kind == "run_ack":
                run_id = _identifier(event["backtestId"])
                if run_id in run_ids or event["status"] != "In Queue...":
                    raise EvaluationError("run acknowledgement reused or invalid")
                run_ids.add(run_id)
                row["run_id"] = run_id
                row["run_request_receipt"] = _receipt(rows, index, "backtests/create")
            elif kind == "run_observation":
                if (event["backtestId"] != row["run_id"] or event["status"] != "Runtime Error"
                        or event["hasInitializeError"] is not True
                        or type(event["completed"]) is not bool or type(event["error"]) is not str
                        or not event["error"] or type(event["serverStatistics"]) is not dict):
                    raise EvaluationError("historical native initialization failure required")
                engine = event["serverStatistics"].get("LEAN Version")
                _version(engine)
                row["engine_observed"] = engine
                row["run_status"] = event["status"]
                row["run_output_receipt"] = _receipt(rows, index, "backtests/read")
                row["run_observed_at"] = event["at"]
            else:
                if (event["backtestId"] != row["run_id"] or event["status"] != "Runtime Error"
                        or event["unsuccessful"] is not True):
                    raise EvaluationError("historical terminal failure lineage differs")
                row["status"], row["terminal_at"] = "failed", event["at"]
        elif kind == "attempt_ceiling":
            if (ceiling is not None or len(attempts) != 3 or any(row["status"] != "failed" for row in attempts)
                    or type(event["unsuccessful"]) is not int or event["unsuccessful"] != 3
                    or event["candidate_edits_stopped"] is not True or event["manual_relaunch_allowed"] is not False):
                raise EvaluationError("exact exhausted historical ceiling required")
            ceiling = event
    if authorization is None or ceiling is None or any(count != 3 for count in create_responses.values()):
        raise EvaluationError("complete closed historical cycle and ceiling required")
    for row in attempts:
        del row["_epoch"], row["_stage"]
    return {"cycle_id": HISTORICAL_CYCLE_ID, "publication_commit": HISTORICAL_PUBLICATION_COMMIT,
        "project_id": authorization["projectId"], "historical_review_commit": None,
        "historical_review_waiver_observed": True, "historical_binding_version": None,
        "attempts": attempts, "unsuccessful_attempts": len(attempts), "remaining_manual_attempts": 0,
        "ceiling_observed_at": ceiling["at"], "typed_journal_custody_verified": False,
        "external_provenance_verified": False, "owner_authorization_verified": False,
        "native_runtime_verified": False, "qc_upload_allowed": False, "qc_launch_allowed": False}


@dataclass(frozen=True, slots=True)
class HistoricalCycleClosure:
    """Raw, immutable legacy custody tied to a separately retained byte hash."""

    events_bytes: bytes
    expected_events_sha256: str
    publication_commit: str = HISTORICAL_PUBLICATION_COMMIT

    def __post_init__(self):
        if self.publication_commit != HISTORICAL_PUBLICATION_COMMIT:
            raise EvaluationError("historical publication anchor cannot be replaced")
        _replay(_legacy_records(self.events_bytes, self.expected_events_sha256))

    def to_dict(self) -> dict:
        self.__post_init__()
        result = _replay(_legacy_records(self.events_bytes, self.expected_events_sha256))
        return {"schema": "gdr.synthetic.historical-cycle-closure.v1", **result,
                "events_sha256": self.expected_events_sha256, "events_bytes": len(self.events_bytes)}

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_dict())


@dataclass(frozen=True, slots=True)
class RecoveryPreparation:
    """Supplied package identity only, not file or independent-review proof.

    No current source files, commits or external review are inspected here.
    Prior review metadata is retained without claiming it reviews this package.
    """

    history: HistoricalCycleClosure
    recovery_manifest_bytes: bytes
    source_commit: str
    prior_review_commit: str
    prior_review_record_sha256: str

    def __post_init__(self):
        if type(self.history) is not HistoricalCycleClosure:
            raise EvaluationError("exact exhausted historical closure required")
        self.history.__post_init__()
        try:
            manifest = decode_object(self.recovery_manifest_bytes)
        except ValueError as exc:
            raise EvaluationError("canonical recovery identity object required") from exc
        _fields(manifest, set(RECOVERY_IDENTITY_FIELDS))
        for value in manifest.values():
            _hash(value)
        if manifest["candidate_sha256"] != CANDIDATE_SHA256 or manifest["fixture_sha256"] != FIXTURE_SHA256:
            raise EvaluationError("recovery cannot replace fixed candidate/fixture")
        _git_sha(self.source_commit)
        _git_sha(self.prior_review_commit)
        _hash(self.prior_review_record_sha256)

    @classmethod
    def from_manifest(cls, history: HistoricalCycleClosure, manifest: dict, *, source_commit: str,
                      prior_review_commit: str, prior_review_record_sha256: str):
        try:
            raw = canonical_object(manifest)
        except ValueError as exc:
            raise EvaluationError("strict canonical recovery identity object required") from exc
        return cls(history, raw, source_commit, prior_review_commit, prior_review_record_sha256)

    def to_dict(self) -> dict:
        self.__post_init__()
        return {"schema": "gdr.synthetic.recovery-preparation.v1", "history": self.history.to_dict(),
            "history_sha256": self.history.sha256, "recovery_manifest": decode_object(self.recovery_manifest_bytes),
            "recovery_manifest_sha256": hash_bytes(self.recovery_manifest_bytes),
            "source_commit": self.source_commit, "prior_review_commit": self.prior_review_commit,
            "prior_review_record_sha256": self.prior_review_record_sha256,
            "recovery_review_pending": True, "remaining_manual_attempts": 0,
            "typed_journal_custody_verified": False, "external_provenance_verified": False,
            "owner_authorization_verified": False, "qc_upload_allowed": False, "qc_launch_allowed": False,
            "launch_allowed": False, "economic_acceptance": False, "market_evidence": False}

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_dict())
