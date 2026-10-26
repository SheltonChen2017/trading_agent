"""Injected-client same-project R298 reconciliation; not an operational caller.

The parent must authenticate the frozen projection, organization and original
attempt, bind reviewed/run-frozen source, and supply an exclusive fsync journal.
No credentials, disk, network, retries, replacement project, or strategy changes
are implemented here. Successful reconciliation does not diagnose the old error.
"""
import hashlib
import json
import re


PROJECT_ID = 38364439
PROJECT_NAME = "ARV2 R298 NEWRULE SIX OFF 2021 OCT2026"
PROJECTION_SHA256 = "f67148cd717e207be9d44f088749c0443bb696d9c4f38f512eb6cbf483fd9662"
SOURCE_NAMES = frozenset((
    "accepted_risk_preliminary_rating_policy.py",
    "accepted_risk_preliminary_rating_evaluator.py",
    "accepted_risk_order_level_core.py",
    "accepted_risk_order_level_forced_exit.py",
    "accepted_risk_order_level_input_runtime.py",
    "accepted_risk_preliminary_qc_figi.py",
    "accepted_risk_preopen_rating_score.py",
    "newrule_comparison_targets.py", "newrule_comparison_qc_runtime.py",
    "newrule_legacy_primitives.py", "main.py"))
ENDPOINTS = frozenset(("projects/read", "backtests/list", "files/read",
    "files/create", "files/update", "compile/create", "compile/read",
    "projects/nodes/read", "backtests/create"))
DEFAULT_MAIN = b'''# region imports
from AlgorithmImports import *
# endregion

class BasicTemplateAlgorithm(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2021, 1, 1)
        self.set_cash(100000)

        self.add_equity("SPY", Resolution.DAILY)

    def on_data(self, data: Slice):
        if not self.portfolio.invested:
            self.set_holdings("SPY", 1)
'''


class RecoveryError(ValueError):
    """Finite local category, never a provider error body or authenticated cause."""


def _require(condition, code):
    if not condition:
        raise RecoveryError(code)


def _canonical(value):
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=True,
            separators=(",", ":"), allow_nan=False).encode("ascii") + b"\n"
    except (TypeError, ValueError, UnicodeError):
        raise RecoveryError("json_shape") from None


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _cloud_id(value):
    _require(type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value), "cloud_id")
    return value


class RemoteRecovery:
    """All requests require journal(marker, event) BEFORE supplied transport.

    journal must atomically/exclusively consume each intent marker and fsync it,
    or raise; duplicate intents must refuse across processes. Observed markers
    retain endpoint/hash only. This injected seam is NOT a standalone run gate.
    """

    def __init__(self, projection, organization_id, request, journal):
        _require(callable(request) and callable(journal), "callbacks")
        _require(type(organization_id) is str and re.fullmatch(r"[0-9a-f]{32}", organization_id), "organization")
        record = projection.to_record()
        _require(type(record) is dict and record.get("candidate_id") == "R298"
            and projection.projection_sha256 == PROJECTION_SHA256, "projection_binding")
        entries = projection.source_files
        _require(type(entries) is tuple and len(entries) == 11, "source_inventory")
        sources = {}
        for entry in entries:
            name, raw = entry.project_path, entry.source_bytes
            _require(type(name) is str and name in SOURCE_NAMES and name not in sources
                and type(raw) is bytes and 0 < len(raw) <= 64000 and raw.isascii(), "source_binding")
            sources[name] = raw
        _require(set(sources) == SOURCE_NAMES and sum(map(len, sources.values())) <= 448 * 1024, "source_inventory")
        manifest = [{"project_path": entry.project_path, "byte_count": len(entry.source_bytes),
            "content_sha256": _sha(entry.source_bytes)} for entry in entries]
        _require(_canonical(record.get("source_files")) == _canonical(manifest), "source_manifest_binding")
        self._sources = sources
        self._organization = organization_id
        self._request, self._journal = request, journal
        self._used = set()

    def _event(self, marker, event, endpoint, digest):
        try:
            result = self._journal(marker, {"event": event, "endpoint": endpoint, "sha256": digest})
        except Exception:
            raise RecoveryError("journal_failed") from None
        _require(result is None, "journal_result")

    def _rpc(self, marker, endpoint, payload):
        _require(endpoint in ENDPOINTS and marker not in self._used, "duplicate_or_endpoint")
        _require(type(payload) is dict and type(payload.get("projectId")) is int
            and payload["projectId"] == PROJECT_ID, "request_project")
        self._used.add(marker)  # Remains consumed even if the durable seam refuses.
        raw = _canonical(payload)
        self._event(marker, "intent", endpoint, _sha(raw))
        try:
            response = self._request(endpoint, json.loads(raw))
        except Exception:
            raise RecoveryError("request_ambiguous") from None
        _require(type(response) is dict, "response_shape")
        raw = _canonical(response)
        _require(len(raw) <= 1024 * 1024, "response_bound")
        self._event(marker, "observed", endpoint, _sha(raw))
        response = json.loads(raw)
        _require(response.get("success") is True, "response_refused")
        return response

    def _owned(self, prefix):
        rows = self._rpc(prefix + "-project", "projects/read", {"projectId": PROJECT_ID}).get("projects")
        _require(type(rows) is list and len(rows) == 1 and type(rows[0]) is dict, "project_shape")
        row = rows[0]
        collaborators = row.get("collaborators")
        _require(type(row.get("projectId")) is int and row["projectId"] == PROJECT_ID
            and row.get("organizationId") == self._organization and row.get("name") == PROJECT_NAME
            and row.get("language") == "Py" and row.get("owner") is True
            and row.get("public", False) is False and row.get("codeRunning") is False
            and type(collaborators) is list and len(collaborators) <= 1
            and all(type(item) is dict and item.get("owner") is True for item in collaborators), "private_owned_idle_project")
        response = self._rpc(prefix + "-backtests", "backtests/list",
            {"projectId": PROJECT_ID, "includeStatistics": False})
        _require(type(response.get("backtests")) is list and response["backtests"] == []
            and ("count" not in response or (type(response["count"]) is int and response["count"] == 0))
            and ("projectId" not in response or (type(response["projectId"]) is int
                and response["projectId"] == PROJECT_ID)), "prior_backtests")

    def _files(self, marker, *, complete=False):
        rows = self._rpc(marker, "files/read", {"projectId": PROJECT_ID}).get("files")
        _require(type(rows) is list and len(rows) <= 11, "cloud_inventory")
        seen, result = set(), []
        for row in rows:
            _require(type(row) is dict, "cloud_file")
            name, content = row.get("name"), row.get("content")
            _require(type(row.get("projectId")) is int and row["projectId"] == PROJECT_ID
                and type(name) is str and name in SOURCE_NAMES and name not in seen
                and type(content) is str and content.isascii() and len(content) <= 64000, "cloud_file")
            raw = content.encode("ascii")
            _require(raw == self._sources[name] or (not complete and
                (raw in (b"#", b"#\n") or (name == "main.py" and raw == DEFAULT_MAIN))), "unexpected_cloud_content")
            seen.add(name)
            result.append({"name": name, "byte_count": len(raw), "sha256": _sha(raw)})
        _require(not complete or seen == SOURCE_NAMES, "incomplete_cloud_source")
        return {"project_id": PROJECT_ID, "projection_sha256": PROJECTION_SHA256,
            "files": sorted(result, key=lambda row: row["name"])}

    def inspect(self):
        self._owned("inspect")
        return self._files("inspect-files")

    def complete(self, original_inventory):
        """One missing/placeholder completion, never overwrites arbitrary bytes."""
        original = _canonical(original_inventory)  # Copy before any callback.
        self._owned("complete")
        current = self._files("complete-before")
        _require(_canonical(current) == original, "inventory_changed")
        observed = {row["name"]: row for row in current["files"]}
        for index, (name, raw) in enumerate(sorted(self._sources.items())):
            expected = {"name": name, "byte_count": len(raw), "sha256": _sha(raw)}
            if observed.get(name) == expected:
                continue
            # Require the evolving full manifest unchanged immediately before
            # each mutation; response hashes never substitute for file readback.
            before = self._files(f"complete-before-{index:02d}")
            _require(_canonical(before) == _canonical(current), "inventory_changed")
            endpoint = "files/update" if name in observed else "files/create"
            self._rpc(f"complete-write-{index:02d}", endpoint,
                {"projectId": PROJECT_ID, "name": name, "content": raw.decode("ascii")})
            observed[name] = expected
            current = {"project_id": PROJECT_ID, "projection_sha256": PROJECTION_SHA256,
                "files": sorted(observed.values(), key=lambda row: row["name"])}
        final = self._files("complete-final", complete=True)
        _require(_canonical(final) == _canonical(current), "completion_readback")
        return final

    def compile_once(self, completed_inventory):
        supplied = _canonical(completed_inventory)
        self._owned("compile")
        observed = self._files("compile-files", complete=True)
        _require(_canonical(observed) == supplied, "inventory_changed")
        response = self._rpc("compile-create", "compile/create", {"projectId": PROJECT_ID})
        _require(type(response.get("projectId", PROJECT_ID)) is int
            and response.get("projectId", PROJECT_ID) == PROJECT_ID, "compile_project")
        return {"project_id": PROJECT_ID, "compile_id": _cloud_id(response.get("compileId")),
            "projection_sha256": PROJECTION_SHA256, "source_manifest_sha256": _sha(supplied)}

    def _compile_state(self, compile_id, marker):
        compile_id = _cloud_id(compile_id)
        response = self._rpc(marker, "compile/read", {"projectId": PROJECT_ID, "compileId": compile_id})
        _require(response.get("compileId") == compile_id and type(response.get("projectId", PROJECT_ID)) is int
            and response.get("projectId", PROJECT_ID) == PROJECT_ID
            and response.get("state") in ("InQueue", "Building", "BuildSuccess", "BuildError"), "compile_status")
        return response["state"]

    def poll_compile(self, compile_id, poll_index):
        _require(type(poll_index) is int and 0 <= poll_index < 60, "poll_index")
        return {"project_id": PROJECT_ID, "compile_id": _cloud_id(compile_id),
            "state": self._compile_state(compile_id, f"compile-poll-{poll_index:03d}")}

    def launch_once(self, compile_id):
        _require(self._compile_state(compile_id, "launch-compile") == "BuildSuccess", "compile_not_ready")
        self._owned("launch")
        self._files("launch-files", complete=True)
        response = self._rpc("launch-capacity", "projects/nodes/read", {"projectId": PROJECT_ID})
        nodes, auto = response.get("nodes"), response.get("autoSelectNode")
        _require(type(nodes) is dict and type(auto) is bool, "capacity_shape")
        rows = nodes.get("backtest")
        _require(type(rows) is list and len(rows) <= 64 and all(type(row) is dict
            and type(row.get("busy")) is bool and type(row.get("active")) is bool for row in rows), "capacity_nodes")
        available = sum(not row["busy"] and (auto or row["active"]) for row in rows)
        if not available:
            return {"project_id": PROJECT_ID, "state": "wait", "available_count": 0}
        name = f"{PROJECT_NAME} A2 {PROJECTION_SHA256[:8]}"
        row = self._rpc("launch-create", "backtests/create",
            {"projectId": PROJECT_ID, "compileId": compile_id, "backtestName": name}).get("backtest")
        _require(type(row) is dict and type(row.get("projectId")) is int and row["projectId"] == PROJECT_ID
            and row.get("name") == name and row.get("status") in ("In Queue...", "In Progress..."), "created_backtest")
        return {"project_id": PROJECT_ID, "compile_id": compile_id,
            "backtest_id": _cloud_id(row.get("backtestId")), "backtest_name": name,
            "status": row["status"], "projection_sha256": PROJECTION_SHA256}

    def read_status(self, launch_receipt, poll_index):
        """Own launch only, statistics-disabled list; no result/aggregate reader."""
        _require(type(poll_index) is int and 0 <= poll_index < 240, "status_poll_index")
        _require(type(launch_receipt) is dict and set(launch_receipt) == {
            "project_id", "compile_id", "backtest_id", "backtest_name", "status", "projection_sha256"}, "launch_receipt")
        receipt = json.loads(_canonical(launch_receipt))
        _require(type(receipt["project_id"]) is int and receipt["project_id"] == PROJECT_ID
            and receipt["projection_sha256"] == PROJECTION_SHA256
            and receipt["backtest_name"] == f"{PROJECT_NAME} A2 {PROJECTION_SHA256[:8]}"
            and receipt["status"] in ("In Queue...", "In Progress..."), "launch_receipt")
        _cloud_id(receipt["compile_id"])
        _cloud_id(receipt["backtest_id"])
        response = self._rpc(f"status-poll-{poll_index:03d}", "backtests/list",
            {"projectId": PROJECT_ID, "includeStatistics": False})
        rows = response.get("backtests")
        _require(type(rows) is list and len(rows) == 1
            and ("count" not in response or (type(response["count"]) is int and response["count"] == 1))
            and ("projectId" not in response or (type(response["projectId"]) is int
                and response["projectId"] == PROJECT_ID)), "status_inventory")
        row = rows[0]
        _require(type(row) is dict
            and ("projectId" not in row or (type(row["projectId"]) is int and row["projectId"] == PROJECT_ID))
            and row.get("backtestId") == receipt["backtest_id"] and row.get("name") == receipt["backtest_name"]
            and row.get("status") in ("In Queue...", "In Progress...", "Completed.", "Runtime Error"), "backtest_status")
        return {**receipt, "status": row["status"]}
