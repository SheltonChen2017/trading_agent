"""Bounded read-only collection of exactly one owner-scoped Mia recovery job.

No imports perform I/O. This module has no cloud write, compile, launch,
packet/provider read or attempt-reservation action. Fresh source-bound access
and the look claim precede Mia execution. UI claims are cooperative captured
provenance, not cryptographic cloud execution or canonical custody attestation.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

from . import matched_driver as driver, operations_v2 as ops

CANDIDATE = "TPR-MATCHED-ON-BASE-v1"
PROJECT_ID = 37547067
CONFIG_HASH = "53f1c149cbe6d6e733409c15ac34dd051f93da2a18fe24a951aa5be62afe5b52"
PRIOR_CODEX_JOBS = frozenset({"8cab89fbac806255f1685e0b0c39e3ee",
                            "95f205174fb735bf4e9a865931c00f5f",
                            "a0f26651b7bcc0a5b8fc52a9d0be27eb"})
MODULE_PATH = "research/target_price_revisions_qc/mia_recovery.py"
NOTEBOOK_HASH = "af27200522531d426185f4daa25d23610c164134e3ab7fdf38919616d0d5b344"
OLD_NOTEBOOK_HASH = "212a51a9f8eb8c29ef77442c5b3db3cc0fe308d7c18f9f2c6ecf7ed86186778e"
READ_ENDPOINTS = frozenset({"files/read", "compile/read", "backtests/read",
                           "backtests/read/log", "backtests/orders/read"})
MANIFEST_KEYS = frozenset({"schema", "operations_manifest", "project_id", "candidate_id",
    "reviewed_preview_sha256", "source_hashes", "notebook_sha256", "original_notebook_sha256",
    "config_sha256", "max_mia_jobs", "codex_attempts_consumed", "private_packet_key"})
PREVIEW_KEYS = frozenset({"schema", "project_id", "candidate_id", "files", "original_notebook_content"})
CLAIM_KEYS = frozenset({"schema", "project_id", "candidate_id", "compile_id", "backtest_id",
                        "source_hashes", "at", "launch_via_mia"})


def _preview(raw, expected_hash, rendered):
    if not ops._hash(expected_hash) or ops.digest(raw) != expected_hash:
        raise ops.Refusal("reviewed preview identity refused")
    value = ops._json(raw)
    if (type(value) is not dict or set(value) != PREVIEW_KEYS
            or value["schema"] != "tpr-mia-reviewed-cloud-preview-v1"
            or value["project_id"] != PROJECT_ID or type(value["project_id"]) is not int
            or value["candidate_id"] != CANDIDATE or type(value["files"]) is not dict
            or set(value["files"]) != ops.SOURCE_FILES | {"research.ipynb"}
            or any(type(text) is not str or not 0 < len(text.encode()) <= 60000
                   for text in value["files"].values())
            or type(value["original_notebook_content"]) is not str):
        raise ops.Refusal("closed reviewed source preview refused")
    files = value["files"]
    original = next(row for row in rendered["cases"] if row["candidate_id"] == CANDIDATE)
    if any(files[name] != original["files"][name] for name in ops.SOURCE_FILES - {"main.py"}):
        raise ops.Refusal("Mia may change only the reviewed main source")
    if files["main.py"] == original["files"]["main.py"]:
        raise ops.Refusal("instrumented Mia main must be distinct from executed v3")
    for name in ops.SOURCE_FILES:
        driver.bundle._source(files[name])
    old, current = value["original_notebook_content"], files["research.ipynb"]
    if (ops.digest(old.encode()) != OLD_NOTEBOOK_HASH
            or ops.digest(current.encode()) != NOTEBOOK_HASH):
        raise ops.Refusal("known original and current notebook identities required")
    # A formatting-only change must preserve every JSON value and the original
    # frozen byte encoding; source rows are never executed while comparing.
    body = ops._json(current)
    if (ops._json(old) != body or
            (json.dumps(body, indent=1, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n") != old):
        raise ops.Refusal("notebook change is not the exact proven formatting-only delta")
    return value, {name: ops.digest(files[name].encode()) for name in ops.SOURCE_FILES}


def validate_manifest(value, expected_hash):
    if (type(value) is not dict or set(value) != MANIFEST_KEYS
            or not ops._hash(expected_hash) or ops.digest(ops.canonical(value)) != expected_hash
            or value["schema"] != "tpr-mia-readonly-recovery-manifest-v1"
            or type(value["project_id"]) is not int or value["project_id"] != PROJECT_ID
            or value["candidate_id"] != CANDIDATE
            or value["config_sha256"] != CONFIG_HASH
            or type(value["max_mia_jobs"]) is not int or value["max_mia_jobs"] != 1
            or type(value["codex_attempts_consumed"]) is not int or value["codex_attempts_consumed"] != 3
            or value["notebook_sha256"] != NOTEBOOK_HASH
            or value["original_notebook_sha256"] != OLD_NOTEBOOK_HASH
            or not ops._hash(value["reviewed_preview_sha256"])
            or value["private_packet_key"] != f"tpr-matched/{ops.STUDY}/{ops.PACKET_HASH}.json"):
        raise ops.Refusal("closed Mia recovery manifest refused")
    manifest, candidates = ops.validate_manifest(value["operations_manifest"],
                                                ops.digest(ops.canonical(value["operations_manifest"])))
    on = candidates[CANDIDATE]
    if (value["source_hashes"] != on["source_hashes"] or value["config_sha256"] != on["config_sha256"]
            or MODULE_PATH not in manifest["repository_source_hashes"]
            or "research/target_price_revisions_qc/matched_audit_v3.py" not in manifest["repository_source_hashes"]):
        raise ops.Refusal("Mia collector and reviewed source binding required")
    return deepcopy(value)


class ReadOnlyOperations(ops.Operations):
    """Transport-level denylist complement: only the five own read endpoints."""
    def _request(self, endpoint, payload, **kwargs):
        if endpoint not in READ_ENDPOINTS:
            raise ops.Refusal("Mia collector transport is read-only")
        return super()._request(endpoint, payload, **kwargs)


class Recovery:
    def __init__(self, manifest, *, manifest_sha256, _fixture_root=None, _fixture_transport=None):
        self.manifest = validate_manifest(manifest, manifest_sha256)
        self.manifest_sha256 = manifest_sha256
        self.ops = ReadOnlyOperations(self.manifest["operations_manifest"],
            manifest_sha256=ops.digest(ops.canonical(self.manifest["operations_manifest"])),
            _fixture_root=_fixture_root, _fixture_transport=_fixture_transport)
        self.prefix = "mia." + self.ops.operation

    def _access(self):
        context = self.ops._access()
        claim = self.ops._value(CANDIDATE + ".mia-recovery.spent.json")
        if (claim.get("recovery_manifest_sha256") != self.manifest_sha256
                or claim.get("candidate_id") != CANDIDATE or claim.get("project_id") != PROJECT_ID
                or type(claim.get("codex_attempts_consumed")) is not int or claim["codex_attempts_consumed"] != 3
                or type(claim.get("max_mia_jobs")) is not int or claim["max_mia_jobs"] != 1):
            raise ops.Refusal("single Mia recovery look belongs to a different scope")
        project = self.ops._project(CANDIDATE)
        if (project["project_id"] != PROJECT_ID or project.get("owner") is not True
                or project.get("max_file_size", 0) < 60000):
            raise ops.Refusal("existing owner-private recovery project refused")
        return context, project

    def _request(self, endpoint, payload):
        _, project = self._access()
        if (endpoint not in READ_ENDPOINTS or type(payload) is not dict
                or payload.get("projectId") != PROJECT_ID):
            raise ops.Refusal("read request outside own recovery project")
        return self.ops._request(endpoint, payload, project=project)

    def verify_sources(self, label):
        self._access()
        if not ops._name(label, 80):
            raise ops.Refusal("source verification label refused")
        response = self._request("files/read", {"projectId": PROJECT_ID})
        wire = self.prefix + "." + label + ".source-wire.json"
        self.ops.exclusive(wire, response)
        rows = response.get("files")
        if type(rows) is not list or len(rows) != 5:
            raise ops.Refusal("reviewed cloud file inventory changed")
        files = {}
        for row in rows:
            if (type(row) is not dict or row.get("name") not in ops.SOURCE_FILES | {"research.ipynb"}
                    or row["name"] in files or type(row.get("content")) is not str
                    or len(row["content"].encode()) > 60000):
                raise ops.Refusal("cloud source row shape changed")
            files[row["name"]] = row["content"]
        hashes = {name: ops.digest(files[name].encode()) for name in ops.SOURCE_FILES}
        if (hashes != self.manifest["source_hashes"] or
                ops.digest(files["research.ipynb"].encode()) != self.manifest["notebook_sha256"]):
            raise ops.Refusal("reviewed Mia cloud source or notebook changed")
        config = self.ops._config(CANDIDATE, files["matched_config.py"])
        receipt = {"at": ops.utc(), "source_hashes": hashes, "config_sha256": self.manifest["config_sha256"],
                   "notebook_sha256": self.manifest["notebook_sha256"], "equal": True,
                   "cloud_wire_sha256": ops.digest(ops.canonical(response)),
                   "recovery_manifest_sha256": self.manifest_sha256}
        sha = self.ops.exclusive(self.prefix + "." + label + ".source-verification.json", receipt)
        return {**receipt, "sha256": sha}, config

    def verify_compile(self, compile_id):
        self._access()
        if not ops._name(compile_id, 200):
            raise ops.Refusal("explicit Mia compile identity required")
        claim_name = self.prefix + ".compile.claim.json"
        if (self.ops.root / claim_name).exists():
            if self.ops._value(claim_name).get("compile_id") != compile_id:
                raise ops.Refusal("cannot replace Mia compile identity")
        else:
            self.ops.exclusive(claim_name, {"compile_id": compile_id, "at": ops.utc(),
                "recovery_manifest_sha256": self.manifest_sha256})
        number = self.ops._seq(self.prefix + ".compile.", ".spent.json")
        if number > 5:
            raise ops.Refusal("five explicit compile verification rounds consumed")
        label = f"compile.{number:04d}"
        self.ops.exclusive(self.prefix + "." + label + ".spent.json", {"at": ops.utc(), "read_only": True})
        before, _ = self.verify_sources(label + ".before")
        response = self._request("compile/read", {"projectId": PROJECT_ID, "compileId": compile_id})
        response_file = self.prefix + "." + label + ".wire.json"
        response_hash = self.ops.exclusive(response_file, response)
        if (response.get("compileId") != compile_id or
                response.get("projectId", PROJECT_ID) != PROJECT_ID):
            raise ops.Refusal("Mia compile response identity differs")
        after, _ = self.verify_sources(label + ".after")
        if response.get("state") == "BuildSuccess" and not (self.ops.root / (self.prefix + ".compile.verified.json")).exists():
            self.ops.exclusive(self.prefix + ".compile.verified.json", {
                "compile_id": compile_id, "project_id": PROJECT_ID, "state": "BuildSuccess",
                "compile_response_file": response_file, "compile_response_sha256": response_hash,
                "source_hashes": self.manifest["source_hashes"],
                "source_before_sha256": before["sha256"], "source_after_sha256": after["sha256"],
                "recovery_manifest_sha256": self.manifest_sha256, "at": ops.utc()})
        self.index(self.prefix + "." + label)
        return {"compile_id": compile_id, "state": response.get("state"), "new_codex_attempts": 0}

    def _compile(self):
        verified = self.ops._value(self.prefix + ".compile.verified.json")
        claim = self.ops._value(self.prefix + ".compile.claim.json")
        response_file = verified.get("compile_response_file")
        if (type(response_file) is not str or not response_file.startswith(self.prefix + ".compile.")
                or not response_file.endswith(".wire.json")):
            raise ops.Refusal("own immutable compile response path required")
        raw = self.ops.read_private(response_file)
        response = ops._json(raw)
        if (verified.get("recovery_manifest_sha256") != self.manifest_sha256
                or verified.get("source_hashes") != self.manifest["source_hashes"]
                or verified.get("compile_id") != claim.get("compile_id")
                or verified.get("state") != "BuildSuccess" or verified.get("project_id") != PROJECT_ID
                or ops.digest(raw) != verified.get("compile_response_sha256")
                or response.get("state") != "BuildSuccess"
                or response.get("compileId") != verified["compile_id"]
                or response.get("projectId", PROJECT_ID) != PROJECT_ID):
            raise ops.Refusal("source-bound Mia BuildSuccess verification required")
        return verified

    def _recheck_compile(self, label):
        verified = self._compile()
        response = self._request("compile/read", {"projectId": PROJECT_ID, "compileId": verified["compile_id"]})
        self.ops.exclusive(self.prefix + "." + label + ".compile-wire.json", response)
        if (response.get("compileId") != verified["compile_id"] or response.get("state") != "BuildSuccess"
                or response.get("projectId", PROJECT_ID) != PROJECT_ID):
            raise ops.Refusal("Mia compile source binding changed")
        return verified

    def bind_job(self, backtest_id, *, ui_claim=None, ui_claim_sha256=None):
        self._access()
        verified = self._compile()
        if not ops._name(backtest_id, 200) or backtest_id in PRIOR_CODEX_JOBS:
            raise ops.Refusal("explicit Mia backtest identity required")
        name = self.prefix + ".job.json"
        if (self.ops.root / name).exists():
            bound = self.ops._value(name)
            if (bound.get("backtest_id") != backtest_id or bound.get("compile_id") != verified["compile_id"]
                    or bound.get("recovery_manifest_sha256") != self.manifest_sha256):
                raise ops.Refusal("Mia job identity may be bound only once")
            return bound
        if not ops._name(ui_claim, 220) or not ops._hash(ui_claim_sha256):
            raise ops.Refusal("captured trusted UI job claim required before first read")
        raw = self.ops.read_private(ui_claim)
        value = ops._json(raw)
        if (ops.digest(raw) != ui_claim_sha256 or type(value) is not dict or set(value) != CLAIM_KEYS
                or value["schema"] != "tpr-mia-ui-job-claim-v1" or value["launch_via_mia"] is not True
                or type(value["project_id"]) is not int or value["project_id"] != PROJECT_ID
                or value["candidate_id"] != CANDIDATE or value["compile_id"] != verified["compile_id"]
                or value["backtest_id"] != backtest_id or value["source_hashes"] != self.manifest["source_hashes"]
                or not ops._clock(self.ops.manifest["created_utc"]) <= ops._clock(value["at"]) <=
                       ops._clock(self.ops.manifest["expires_utc"])):
            raise ops.Refusal("Mia UI job/source/clock claim differs")
        bound = {"project_id": PROJECT_ID, "compile_id": verified["compile_id"], "backtest_id": backtest_id,
            "candidate_id": CANDIDATE, "ui_claim": ui_claim, "ui_claim_sha256": ui_claim_sha256,
            "source_hashes": self.manifest["source_hashes"], "recovery_manifest_sha256": self.manifest_sha256,
            "at": ops.utc(), "new_codex_attempts": 0, "mia_recovery_look": 1}
        self.ops.exclusive(name, bound)
        return bound

    def _result(self, response, job):
        result = response.get("backtest")
        if (type(result) is not dict or result.get("backtestId") != job["backtest_id"]
                or result.get("projectId", PROJECT_ID) != PROJECT_ID
                or result.get("compileId", job["compile_id"]) != job["compile_id"]):
            raise ops.Refusal("Mia result does not match captured own UI job")
        # Missing compileId is not inferred from arbitrary results: immutable
        # captured UI claim plus matching reviewed BuildSuccess is prerequisite.
        if ops.digest(self.ops.read_private(job["ui_claim"])) != job["ui_claim_sha256"]:
            raise ops.Refusal("captured UI claim changed")
        safe = {key: value for key, value in result.items() if key != "charts"}
        if type(result.get("charts")) is dict:
            safe["charts"] = {key: value for key, value in result["charts"].items()
                              if key in {"Strategy Equity", "Drawdown", "Portfolio Turnover"}}
        return {"success": True, "backtest": safe}

    def poll(self, backtest_id, **claim):
        job = self.bind_job(backtest_id, **claim)
        number = self.ops._seq(self.prefix + ".poll.", ".spent.json")
        label = f"poll.{number:04d}"
        self.ops.exclusive(self.prefix + "." + label + ".spent.json", {"at": ops.utc(), "read_only": True})
        self.verify_sources(label + ".before")
        response = self._request("backtests/read", {"projectId": PROJECT_ID, "backtestId": backtest_id})
        self.ops.exclusive(self.prefix + "." + label + ".result-wire.json", response)
        result = self._result(response, job)
        self.ops.exclusive(self.prefix + "." + label + ".result.json", result)
        self.verify_sources(label + ".after")
        self.index(self.prefix + "." + label)
        body = result["backtest"]
        return {"backtest_id": backtest_id, "completed": body.get("completed") is True,
                "terminal": body.get("completed") is True or bool(body.get("error")),
                "status": body.get("status"), "error": bool(body.get("error")), "new_development_looks": 0}

    def collect(self, backtest_id, **claim):
        job = self.bind_job(backtest_id, **claim)
        number = self.ops._seq(self.prefix + ".collection.", ".spent.json")
        if number > 5:
            raise ops.Refusal("five explicit same-job collection rounds consumed")
        prefix = self.prefix + f".collection.{number:04d}"
        self.ops.exclusive(prefix + ".spent.json", {"at": ops.utc(), "read_only": True,
            "backtest_id": backtest_id, "new_development_looks": 0, "new_codex_attempts": 0})
        errors, pages, logs = [], [], []
        result, source, config = None, None, None
        stage = "source_compile"
        try:
            self._recheck_compile(f"collection.{number:04d}.before")
            source, config = self.verify_sources(f"collection.{number:04d}.before")
            stage = "result"
            payload = {"projectId": PROJECT_ID, "backtestId": backtest_id}
            response = self._request("backtests/read", payload)
            self.ops.exclusive(prefix + ".result-wire.json", response)
            result = self._result(response, job)
            self.ops.exclusive(prefix + ".result.json", result)
            body = result["backtest"]
            if body.get("completed") is not True and not body.get("error"):
                raise ops.Refusal("Mia result not terminal; explicit recollection only")
            stage = "orders"
            start, total, orders = 0, None, []
            while total is None or start < total:
                wire = self._request("backtests/orders/read", {**payload, "start": start, "end": start + 99})
                self.ops.exclusive(f"{prefix}.orders.{start:05d}.wire.json", wire)
                page = {**wire, "start": start, "end": start + 99}
                self.ops.exclusive(f"{prefix}.orders.{start:05d}.json", page)
                values, reported = wire.get("orders"), wire.get("length")
                if (type(values) is not list or type(reported) is not int or not 0 <= reported <= 10000
                        or total is not None and total != reported or len(values) > 99
                        or not values and start < reported):
                    raise ops.Refusal("complete Mia order pagination required")
                total = reported
                orders.extend(values)
                pages.append(page)
                start += 99
            ids = [row.get("id") for row in orders if type(row) is dict]
            if (len(orders) != total or len(ids) != total or len(set(ids)) != total
                    or any(type(value) is not int for value in ids)):
                raise ops.Refusal("Mia order identity census differs")
            stage = "logs"
            start, total = 0, None
            while total is None or start < total:
                wire = self._request("backtests/read/log", {**payload, "start": start, "end": start + 200,
                                                          "query": "MATCHED_"})
                self.ops.exclusive(f"{prefix}.logs.{start:05d}.wire.json", wire)
                values, reported = wire.get("logs"), wire.get("length")
                if (type(values) is not list or type(reported) is not int or not 0 <= reported <= 4000
                        or total is not None and total != reported or len(values) > 200
                        or any(type(line) is not str or len(line) > 8192 or "MATCHED_" not in line for line in values)
                        or not values and start < reported):
                    raise ops.Refusal("complete own aggregate log pagination required")
                total = reported
                logs.extend(values)
                start += 200
            if len(logs) != total:
                raise ops.Refusal("Mia aggregate log census differs")
            stage = "source_after"
            self.verify_sources(f"collection.{number:04d}.after")
            self._recheck_compile(f"collection.{number:04d}.after")
        except Exception:
            errors.append("collection_failed_or_incomplete; no implicit retry")
            self.ops.exclusive(prefix + ".error.json", {"at": ops.utc(), "stage": stage,
                "status": "failed_or_incomplete", "automatic_retry": False})
        completion = {"schema": "tpr-mia-collection-v1", "candidate_id": CANDIDATE, "project_id": PROJECT_ID,
            "compile_id": job["compile_id"], "backtest_id": backtest_id, "collection_round": number,
            "collection_errors": errors, "read_only": True, "new_development_looks": 0,
            "new_codex_attempts": 0, "canonical_admission": False}
        if not errors:
            from .matched_audit_v3 import audit_result
            logs_response = {"success": True, "logs": logs, "length": len(logs)}
            receipt = {"candidate_id": CANDIDATE, "project_id": PROJECT_ID, "compile_id": job["compile_id"],
                "backtest_id": backtest_id, "config_sha256": self.manifest["config_sha256"],
                "packet_sha256": ops.PACKET_HASH, "freeze_sha256": ops.FREEZE_HASH,
                "source_hashes": self.manifest["source_hashes"], "exact_cloud_readback": True,
                "build_success": True, "source_verification_sha256": source["sha256"],
                "evidence_hashes": {"result": ops.digest(ops.canonical(result)),
                    "logs": ops.digest(ops.canonical(logs_response)),
                    "order_pages": [ops.digest(ops.canonical(page)) for page in pages]}}
            self.ops.exclusive(prefix + ".source-receipt.json", receipt)
            self.ops.exclusive(prefix + ".logs.combined.json", logs_response)
            try:
                evidence = audit_result(result, logs_response, pages, receipt, config)
                evidence["mia_recovery_look"] = 1
                evidence["collection_round"] = number
                self.ops.exclusive(prefix + ".interpreted.json", evidence)
                completion["audit"] = evidence
            except Exception:
                completion["collection_errors"] = ["pure_accounting_audit_refused"]
                self.ops.exclusive(prefix + ".audit-error.json", {"status": "audit_refused", "canonical_admission": False})
        self.ops.exclusive(prefix + ".completion.json", completion)
        self.index(prefix)
        return completion

    def index(self, prefix):
        """Index only this operation's own generated metadata, never old inputs."""
        files = []
        names = {self.prefix + ".manifest.json", self.prefix + ".preview.json",
                 self.prefix + ".bundle.json", "access." + self.ops.operation + ".json",
                 CANDIDATE + ".mia-recovery.spent.json"}
        for path in sorted(self.ops.root.iterdir()):
            if path.name.startswith(self.prefix + ".") or path.name in names:
                files.append({"name": path.name, "sha256": ops.digest(self.ops.read_private(path.name)),
                              "bytes": path.stat().st_size})
            elif path.name.startswith("request.") and path.name.endswith(".json") and ".terminal." not in path.name:
                metadata = self.ops._value(path.name)
                if metadata.get("manifest_sha256") == self.ops.manifest_sha256:
                    for name in (path.name, path.name[:-5] + ".terminal.json"):
                        if (self.ops.root / name).exists():
                            raw = self.ops.read_private(name)
                            files.append({"name": name, "sha256": ops.digest(raw), "bytes": len(raw)})
        self.ops.exclusive(prefix + ".evidence-index.json", {"schema": "tpr-mia-evidence-index-v1",
            "at": ops.utc(), "recovery_manifest_sha256": self.manifest_sha256, "files": files})


def prepare(operation, preview, preview_sha256):
    context = driver.preflight()
    if not ops._name(operation, 80) or not ops._name(preview, 220):
        raise ops.Refusal("explicit bounded operation and preview names required")
    private = ops.PRIVATE_PARENT / ops.STUDY
    raw = ops._read(private, preview, 16777216)
    rendered = driver.render_sources()
    value, hashes = _preview(raw, preview_sha256, rendered)
    on = next(row for row in rendered["cases"] if row["candidate_id"] == CANDIDATE)
    on["files"] = {name: value["files"][name] for name in ops.SOURCE_FILES}
    on["source_hashes"] = hashes
    sources = (*driver.REPOSITORY_SOURCES, MODULE_PATH, "research/target_price_revisions_qc/matched_audit_v3.py")
    now = datetime.now(timezone.utc)
    manifest = {"schema": "tpr-qc-operations-manifest-v2", "study_id": ops.STUDY, "operation_id": operation,
        "created_utc": now.isoformat(), "expires_utc": (now + timedelta(hours=48)).isoformat(),
        "baseline_git_head": context["head"], "freeze_sha256": ops.FREEZE_HASH,
        "repository_source_hashes": {path: ops.digest((ops.LANE / path).read_bytes()) for path in sources},
        "input_hashes": {"signal-packet.json": ops.PACKET_HASH, "original-core.py": driver.bundle.CORE_SHA256,
                        "matched-freeze.json": ops.FREEZE_HASH},
        "packet_path": ops.PACKET_PATH, "packet_sha256": ops.PACKET_HASH,
        "candidates": [{key: row[key] for key in ("candidate_id", "config_sha256", "source_hashes")}
                       | {"project_name": row["candidate_id"] + "-private"} for row in rendered["cases"]],
        "max_requests": 1000, "max_response_bytes": 16777216, "request_timeout_seconds": 30,
        "max_attempts_per_candidate": 3, "log_prefix": "MATCHED_"}
    recovery = {"schema": "tpr-mia-readonly-recovery-manifest-v1", "operations_manifest": manifest,
        "project_id": PROJECT_ID, "candidate_id": CANDIDATE, "reviewed_preview_sha256": preview_sha256,
        "source_hashes": hashes, "notebook_sha256": NOTEBOOK_HASH,
        "original_notebook_sha256": OLD_NOTEBOOK_HASH, "config_sha256": on["config_sha256"],
        "max_mia_jobs": 1, "codex_attempts_consumed": 3,
        "private_packet_key": f"tpr-matched/{ops.STUDY}/{ops.PACKET_HASH}.json"}
    digest = ops.digest(ops.canonical(recovery))
    controller = Recovery(recovery, manifest_sha256=digest)
    controller.ops.guard()
    if (controller.ops.root / (CANDIDATE + ".mia-recovery.spent.json")).exists():
        raise ops.Refusal("single Mia recovery look already reserved; no scope-renaming reset")
    # Verify only own prior attempt/upload metadata: never original packet.
    project = controller.ops._project(CANDIDATE)
    if project["project_id"] != PROJECT_ID or project.get("max_file_size", 0) < 60000:
        raise ops.Refusal("existing own project metadata refused")
    for number in (1, 2, 3):
        prior = controller.ops._value(CANDIDATE + f".attempt.{number}.reserved.json")
        if prior.get("attempt") != number or prior.get("project_id") != PROJECT_ID or prior.get("candidate_id") != CANDIDATE:
            raise ops.Refusal("three immutable prior Codex attempts required")
    uploaded = controller.ops._value("packet-upload.completed.json")
    if uploaded.get("key") != recovery["private_packet_key"] or uploaded.get("packet_sha256") != ops.PACKET_HASH:
        raise ops.Refusal("existing exact private packet upload binding required")
    controller.ops.prepare_access()
    controller.ops.exclusive(controller.prefix + ".manifest.json", recovery)
    controller.ops.exclusive(controller.prefix + ".preview.json", raw)
    controller.ops.exclusive(controller.prefix + ".bundle.json", rendered)
    controller.ops.exclusive(CANDIDATE + ".mia-recovery.spent.json", {
        "at": ops.utc(), "recovery_manifest_sha256": digest, "candidate_id": CANDIDATE,
        "project_id": PROJECT_ID, "codex_attempts_consumed": 3, "max_mia_jobs": 1,
        "mia_recovery_look_reserved": not controller.ops.fixture, "original_packet_read": False})
    controller.index(controller.prefix + ".prepared")
    return {"operation": operation, "recovery_manifest_sha256": digest,
            "baseline_git_head": context["head"], "source_hashes": hashes,
            "config_sha256": on["config_sha256"], "new_codex_attempts": 0, "max_mia_jobs": 1}


def controller_for(operation):
    driver.preflight()
    if not ops._name(operation, 80):
        raise ops.Refusal("explicit operation required")
    raw = ops._read(ops.PRIVATE_PARENT / ops.STUDY, "mia." + operation + ".manifest.json", 16777216)
    result = Recovery(ops._json(raw), manifest_sha256=ops.digest(raw))
    result._access()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "verify-compile", "poll", "collect"))
    parser.add_argument("--operation", required=True)
    parser.add_argument("--preview")
    parser.add_argument("--preview-sha256")
    parser.add_argument("--compile-id")
    parser.add_argument("--backtest-id")
    parser.add_argument("--ui-claim")
    parser.add_argument("--ui-claim-sha256")
    args = parser.parse_args(argv)
    driver.preflight()
    if args.action == "prepare":
        if None in (args.preview, args.preview_sha256):
            parser.error("prepare requires exact reviewed preview and original notebook identities")
        result = prepare(args.operation, args.preview, args.preview_sha256)
    elif args.action == "verify-compile":
        if args.compile_id is None:
            parser.error("--compile-id required")
        result = controller_for(args.operation).verify_compile(args.compile_id)
    else:
        if args.backtest_id is None:
            parser.error("--backtest-id required")
        method = getattr(controller_for(args.operation), args.action)
        result = method(args.backtest_id, ui_claim=args.ui_claim, ui_claim_sha256=args.ui_claim_sha256)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
