"""Pure third-attempt R298 reconciliation; no operational authority or I/O.

The separately frozen caller must authenticate prior effects, source, inputs,
actual exits and its exclusive third-attempt claim. A1 and A2 stay spent. The
old helper is unchanged: its exact-source completion and compile methods are
reused, while organization binding and the A3 name are explicit here. This is
not an independent review, retry command, private-source reader or QC client.
"""
import json
import re

from scripts import arv2_r298_recovery_remote as frozen


PROJECT_ID = frozen.PROJECT_ID
PROJECT_NAME = frozen.PROJECT_NAME
PROJECTION_SHA256 = frozen.PROJECTION_SHA256
SOURCE_NAMES = frozen.SOURCE_NAMES
ENDPOINTS = frozen.ENDPOINTS
ATTEMPT = 3
PROJECTION_CANDIDATE_ID = "arv2-newrule-6-ar0-2026-v1"
BACKTEST_NAME = f"{PROJECT_NAME} A3 {PROJECTION_SHA256[:8]}"
ORGANIZATION_SHA256 = "a2d88859373df0f1fd59ede52b9b3945f847091b5fca3286841241536c38e880"
RecoveryError = frozen.RecoveryError

_require = frozen._require
_canonical = frozen._canonical
_sha = frozen._sha
_cloud_id = frozen._cloud_id

OWNERSHIP_PREDICATES = {
    "owned_project_id": "project_id", "owned_organization": "organization_id",
    "owned_name": "name", "owned_language": "language", "owned_owner": "owner",
    "owned_private": "public", "owned_idle": "code_running",
    "owned_collaborators": "collaborators",
}
FINITE_CODES = frozenset((
    "callbacks", "organization", "projection_binding", "source_inventory",
    "source_binding", "source_manifest_binding", "json_shape", "cloud_id",
    "journal_failed", "journal_result", "duplicate_or_endpoint", "request_project",
    "request_ambiguous", "response_shape", "response_bound", "response_refused",
    "project_shape", "private_owned_idle_project", "prior_backtests",
    "cloud_inventory", "cloud_file", "unexpected_cloud_content",
    "incomplete_cloud_source", "inventory_changed", "completion_readback",
    "compile_project", "compile_status", "poll_index", "compile_not_ready",
    "capacity_shape", "capacity_nodes", "created_backtest", "status_poll_index",
    "launch_receipt", "status_inventory", "backtest_status", "organization_pin",
    *OWNERSHIP_PREDICATES,
))


def finite_error(error):
    """Return only fixed labels, never raw text or a claimed provider cause."""
    code = "unknown"
    if type(error) is RecoveryError:
        args = BaseException.args.__get__(error)
        if (len(args) == 1 and type(args[0]) is str and len(args[0]) <= 96
                and args[0] in FINITE_CODES):
            code = args[0]
    return {"helper_code": code, "predicate": OWNERSHIP_PREDICATES.get(code)}


class FinalRecovery(frozen.RemoteRecovery):
    """Injected request/journal seams only; the caller owns execution gates.

    Organization identity is bound by the fixed historical SHA, not by a dummy
    ID or a newly supplied raw account value. Only the current authenticated
    projects/read response supplies the raw ID, validated and hashed in memory.
    All inherited reconciliation methods use this overridden ownership check.
    """

    def __init__(self, projection, organization_sha256, request, journal):
        _require(callable(request) and callable(journal), "callbacks")
        _require(type(organization_sha256) is str
            and organization_sha256 == ORGANIZATION_SHA256, "organization_pin")
        # R298 is the family cell ID, not the projection's strategy identity.
        # Preserve the true-byte manifest checks and the existing projection
        # SHA; bind its real candidate ID rather than the old fixture's R298.
        record = projection.to_record()
        _require(type(record) is dict and record.get("candidate_id") == PROJECTION_CANDIDATE_ID
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
        self._organization_sha256 = organization_sha256
        self._request, self._journal = request, journal
        self._used = set()

    def _owned(self, prefix):
        rows = self._rpc(prefix + "-project", "projects/read", {"projectId": PROJECT_ID}).get("projects")
        _require(type(rows) is list and len(rows) == 1 and type(rows[0]) is dict, "project_shape")
        row = rows[0]
        _require(type(row.get("projectId")) is int and row["projectId"] == PROJECT_ID, "owned_project_id")
        organization = row.get("organizationId")
        _require(type(organization) is str and re.fullmatch(r"[0-9a-f]{32}", organization)
            and _sha(organization.encode("ascii")) == self._organization_sha256, "owned_organization")
        _require(row.get("name") == PROJECT_NAME, "owned_name")
        _require(row.get("language") == "Py", "owned_language")
        _require(row.get("owner") is True, "owned_owner")
        _require(row.get("public", False) is False, "owned_private")
        _require(row.get("codeRunning") is False, "owned_idle")
        collaborators = row.get("collaborators")
        _require(type(collaborators) is list and len(collaborators) <= 1
            and all(type(item) is dict and item.get("owner") is True for item in collaborators), "owned_collaborators")
        response = self._rpc(prefix + "-backtests", "backtests/list",
            {"projectId": PROJECT_ID, "includeStatistics": False})
        _require(type(response.get("backtests")) is list and response["backtests"] == []
            and ("count" not in response or (type(response["count"]) is int and response["count"] == 0))
            and ("projectId" not in response or (type(response["projectId"]) is int
                and response["projectId"] == PROJECT_ID)), "prior_backtests")

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
        row = self._rpc("launch-create", "backtests/create",
            {"projectId": PROJECT_ID, "compileId": compile_id, "backtestName": BACKTEST_NAME}).get("backtest")
        _require(type(row) is dict and type(row.get("projectId")) is int and row["projectId"] == PROJECT_ID
            and row.get("name") == BACKTEST_NAME and row.get("status") in ("In Queue...", "In Progress..."), "created_backtest")
        return {"project_id": PROJECT_ID, "compile_id": compile_id,
            "backtest_id": _cloud_id(row.get("backtestId")), "backtest_name": BACKTEST_NAME,
            "status": row["status"], "projection_sha256": PROJECTION_SHA256}

    def read_status(self, launch_receipt, poll_index):
        """Own A3 identity only; no statistics, aggregate, result or A2 reader."""
        _require(type(poll_index) is int and 0 <= poll_index < 240, "status_poll_index")
        _require(type(launch_receipt) is dict and set(launch_receipt) == {
            "project_id", "compile_id", "backtest_id", "backtest_name", "status", "projection_sha256"}, "launch_receipt")
        receipt = json.loads(_canonical(launch_receipt))
        _require(type(receipt["project_id"]) is int and receipt["project_id"] == PROJECT_ID
            and receipt["projection_sha256"] == PROJECTION_SHA256
            and receipt["backtest_name"] == BACKTEST_NAME
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
