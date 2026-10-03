"""One-use private QC boundary for R267's input-only eight-ETF diagnostic.

No operation runs on import. The three-attempt ledger and result-read claim
are durable before any corresponding QC mutation. The QC API can return
ordinary outcome fields, but this boundary retains and reports only the ten
frozen input-count statistics; no portfolio or order field is parsed.
"""

import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from . import accepted_risk_eight_universe_input_qc_projection as source
from . import accepted_risk_eight_universe_input_qc_runtime as runtime
from . import six_universe_coverage_submission as common


class EightInputQcSubmissionError(ValueError):
    """An R267 identity, QC transport or one-use bound failed closed."""


_MANIFEST_PATH = Path(__file__).resolve().with_name("eight_universe_input_r267_candidate.json")
_MANIFEST_SHA256 = "2951a4bc31288a6f214364cd0e4126b95a020e0efa2099335089001c9bc5b8cb"
_ORG = re.compile(r"[0-9a-f]{32}\Z")
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
_DEFAULT_FILES = frozenset({"main.py", "research.ipynb"})


def _fail(message):
    raise EightInputQcSubmissionError(message)


def _canonical(value):
    return common._canonical(value)


def _sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _manifest():
    raw = _MANIFEST_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != _MANIFEST_SHA256:
        _fail("R267 candidate manifest bytes changed")
    value = json.loads(raw.decode("ascii"))
    # The checked-in one-line key order is fixed by the raw SHA above.  It is
    # deliberately not rewritten by a serializer at read time.
    if type(value) is not dict or not raw.endswith(b"\n") or raw.count(b"\n") != 1:
        _fail("R267 candidate manifest shape changed")
    return value


@dataclass(frozen=True, slots=True)
class EightInputQcPlan:
    candidate_id: str
    attempt: int
    project_name: str
    backtest_name: str
    organization_id: str
    control_directory: Path
    projection_sha256: str
    profile_sha256: str


def build_plan(organization_id, control_directory, attempt=1):
    manifest = _manifest()
    if (
        type(organization_id) is not str or not _ORG.fullmatch(organization_id)
        or not isinstance(control_directory, Path) or not control_directory.is_absolute()
        or type(attempt) is not int or not 1 <= attempt <= source.MAXIMUM_QC_ATTEMPTS
    ):
        _fail("R267 exact destination or attempt changed")
    suffix = "" if attempt == 1 else f" A{attempt}"
    return EightInputQcPlan(
        source.CANDIDATE_ID, attempt,
        manifest["project_name"],
        manifest["backtest_name"] + suffix,
        organization_id, control_directory,
        manifest["projection_sha256"], manifest["profile_sha256"],
    )


def preview(plan, projection):
    manifest = _manifest()
    if type(plan) is not EightInputQcPlan or type(projection) is not source.EightUniverseInputQcProjection:
        _fail("R267 plan or source type changed")
    suffix = "" if plan.attempt == 1 else f" A{plan.attempt}"
    if (
        plan.candidate_id != source.CANDIDATE_ID
        or type(plan.attempt) is not int or not 1 <= plan.attempt <= 3
        or plan.project_name != manifest["project_name"]
        or plan.backtest_name != manifest["backtest_name"] + suffix
        or type(plan.organization_id) is not str or not _ORG.fullmatch(plan.organization_id)
        or not isinstance(plan.control_directory, Path) or not plan.control_directory.is_absolute()
        or plan.projection_sha256 != projection.projection_sha256
        or plan.profile_sha256 != projection.profile_sha256
        or projection.projection_sha256 != manifest["projection_sha256"]
        or projection.profile_sha256 != manifest["profile_sha256"]
        or projection.package_sha256 != manifest["package_sha256"]
        or projection.package_lineage_sha256 != manifest["package_lineage_sha256"]
        or projection.activation_manifest_sha256 != manifest["activation_manifest_sha256"]
        or projection.total_source_byte_count != manifest["total_source_byte_count"]
        or len(projection.source_files) != manifest["source_file_count"]
        or list(projection.statistic_names) != manifest["statistic_names"]
        or projection.to_record()["projection_sha256"] != projection.projection_sha256
        or _sha({key: value for key, value in projection.to_record().items()
                 if key not in {"projection_id", "projection_sha256"}})
        != projection.projection_sha256
    ):
        _fail("R267 source or manifest authority changed")
    if manifest.get("input_only") is not True or any(
        manifest.get(flag) is not False
        for flag in ("outcome_access", "price_access", "orders", "deployment", "trading")
    ):
        _fail("R267 capability boundary changed")
    if manifest.get("readiness_gate") != {
        "metric": "relaxed_joint_pass_10_verified3_count",
        "new_universe_ids": ["XLI", "XLF"],
        "minimum_total_per_universe": 26,
        "minimum_each_year_per_universe": 1,
        "years": [2021, 2022, 2023, 2024, 2025],
        "requires_authenticated_261_decision_census": True,
    }:
        _fail("R267 prospective input-readiness gate changed")
    files = projection.source_files
    if (
        len({item.project_path for item in files}) != len(files)
        or sum(item.byte_count for item in files) != projection.total_source_byte_count
        or projection.total_source_byte_count > source.MAXIMUM_TOTAL_SOURCE_BYTES
    ):
        _fail("R267 source closure changed")
    for item in files:
        if (
            type(item.source_bytes) is not bytes
            or not 0 < len(item.source_bytes) <= source.MAXIMUM_SOURCE_FILE_BYTES
            or item.byte_count != len(item.source_bytes)
            or item.content_sha256 != hashlib.sha256(item.source_bytes).hexdigest()
        ):
            _fail("R267 file bytes changed")
        source._six._audit_source(item.project_path, item.source_bytes)
    return {
        "candidate_id": plan.candidate_id, "attempt": plan.attempt,
        "project_name": plan.project_name,
        "projection_sha256": projection.projection_sha256,
        "profile_sha256": projection.profile_sha256,
        "source_file_count": len(files),
        "statistic_names": list(projection.statistic_names),
        "maximum_attempts": source.MAXIMUM_QC_ATTEMPTS,
        "quantconnect_io_performed": False,
    }


def _path(plan, suffix, attempt=None):
    return common._path(plan, suffix, attempt)


def _post(api, endpoint, payload):
    return common._post(api, endpoint, payload)


def _claim(plan, identity):
    for ordinal in range(1, 4):
        claim = _path(plan, "claim", ordinal)
        terminal = _path(plan, "terminal", ordinal)
        if ordinal < plan.attempt:
            if not claim.exists() or not terminal.exists():
                _fail("R267 prior attempt is unresolved")
            if common._read_control(terminal).get("status") not in {"BuildError", "Runtime Error"}:
                _fail("R267 prior attempt was not terminally unsuccessful")
        elif claim.exists() or terminal.exists():
            _fail("R267 attempt already exists")
    common._write_once(_path(plan, "claim"), {
        "candidate_id": plan.candidate_id, "attempt": plan.attempt,
        "project_name": plan.project_name,
        "projection_sha256": identity["projection_sha256"],
        "profile_sha256": identity["profile_sha256"],
    })


def _project(response, plan):
    rows = response.get("projects")
    if type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict:
        _fail("R267 QC project response changed")
    row = rows[0]
    project_id = row.get("projectId")
    if (
        type(project_id) is not int or project_id <= 0
        or row.get("name") != plan.project_name
        or row.get("organizationId") != plan.organization_id
        or row.get("language") != "Py"
    ):
        _fail("R267 QC project identity changed")
    return project_id


def launch(plan, projection, api):
    """Spend one attempt in the same private project, attest source, then run."""
    identity = preview(plan, projection)
    common._client(api)
    _post(api, "authenticate", {})
    inventory = _post(api, "projects/read", {}).get("projects")
    if type(inventory) is not list or any(type(row) is not dict for row in inventory):
        _fail("R267 project inventory changed")
    matches = [row for row in inventory if row.get("name") == plan.project_name]
    if plan.attempt == 1:
        if matches:
            _fail("R267 project name is not fresh")
    else:
        prior_project = common._read_control(_path(plan, "project", 1))
        if (
            prior_project.get("candidate_id") != plan.candidate_id
            or prior_project.get("project_name") != plan.project_name
            or prior_project.get("projection_sha256") != plan.projection_sha256
            or type(prior_project.get("project_id")) is not int
            or prior_project["project_id"] <= 0
            or len(matches) != 1
            or matches[0].get("projectId") != prior_project["project_id"]
        ):
            _fail("R267 prior private project identity changed")
    _claim(plan, identity)
    if plan.attempt == 1:
        project_id = _project(_post(api, "projects/create", {
            "name": plan.project_name, "language": "Py",
            "organizationId": plan.organization_id,
        }), plan)
    else:
        project_id = prior_project["project_id"]
    project = _post(api, "projects/read", {"projectId": project_id})
    if _project(project, plan) != project_id:
        _fail("R267 project readback changed")
    row = project["projects"][0]
    collaborators = row.get("collaborators")
    if (
        row.get("owner") is not True or row.get("codeRunning") is not False
        or type(collaborators) is not list or len(collaborators) > 1
        or any(type(item) is not dict or item.get("owner") is not True for item in collaborators)
    ):
        _fail("R267 project is not private and idle")
    if plan.attempt == 1:
        common._write_once(_path(plan, "project", 1), {
            "candidate_id": plan.candidate_id, "project_id": project_id,
            "project_name": plan.project_name,
            "projection_sha256": plan.projection_sha256,
        })
    initial = _post(api, "files/read", {"projectId": project_id}).get("files")
    expected_paths = {item.project_path for item in projection.source_files}
    allowed_paths = _DEFAULT_FILES if plan.attempt == 1 else expected_paths | {"research.ipynb"}
    if type(initial) is not list or any(
        type(item) is not dict or item.get("name") not in allowed_paths
        or type(item.get("content")) is not str
        or ("projectId" in item and item["projectId"] != project_id)
        for item in initial
    ) or len({item["name"] for item in initial}) != len(initial):
        _fail("R267 project file inventory changed")
    names = {item["name"]: item["content"] for item in initial}
    if "research.ipynb" in names:
        _post(api, "files/delete", {"projectId": project_id, "name": "research.ipynb"})
    for item in projection.source_files:
        expected = item.source_bytes.decode("ascii")
        if names.get(item.project_path) == expected:
            continue
        endpoint = "files/update" if item.project_path in names else "files/create"
        _post(api, endpoint, {
            "projectId": project_id, "name": item.project_path,
            "content": expected,
        })
    readback = _post(api, "files/read", {"projectId": project_id}).get("files")
    if type(readback) is not list or len(readback) != len(projection.source_files):
        _fail("R267 source readback count changed")
    observed = {}
    for item in readback:
        if (
            type(item) is not dict or type(item.get("name")) is not str
            or type(item.get("content")) is not str
            or item.get("projectId") != project_id or item["name"] in observed
        ):
            _fail("R267 source readback identity changed")
        observed[item["name"]] = item["content"]
    if set(observed) != {item.project_path for item in projection.source_files}:
        _fail("R267 source readback path changed")
    for item in projection.source_files:
        try:
            content = observed[item.project_path].encode("ascii")
        except UnicodeError:
            _fail("R267 source readback is not ASCII")
        if content != item.source_bytes or hashlib.sha256(content).hexdigest() != item.content_sha256:
            _fail("R267 source readback bytes changed")
    compiled = _post(api, "compile/create", {"projectId": project_id})
    compile_id = compiled.get("compileId")
    if type(compile_id) is not str or not _ID.fullmatch(compile_id):
        _fail("R267 compile identity changed")
    for poll in range(120):
        state = _post(api, "compile/read", {
            "projectId": project_id, "compileId": compile_id,
        })
        if state.get("compileId") != compile_id or state.get("state") not in {
            "InQueue", "Building", "BuildSuccess", "BuildError",
        }:
            _fail("R267 compile state changed")
        if state["state"] in {"BuildSuccess", "BuildError"}:
            break
        if poll < 119:
            time.sleep(2)
    else:
        _fail("R267 compile poll budget exhausted; attempt spent")
    if state["state"] == "BuildError":
        common._write_once(_path(plan, "terminal"), {
            "candidate_id": plan.candidate_id, "attempt": plan.attempt,
            "project_id": project_id, "status": "BuildError",
        })
        _fail("R267 compile failed; attempt spent")
    launched = _post(api, "backtests/create", {
        "projectId": project_id, "compileId": compile_id,
        "backtestName": plan.backtest_name,
    }).get("backtest")
    if type(launched) is not dict:
        _fail("R267 launch response changed")
    backtest_id = launched.get("backtestId")
    if plan.attempt > 1:
        prior_launch_path = _path(plan, "launch", plan.attempt - 1)
        if prior_launch_path.exists() and common._read_control(prior_launch_path).get("backtest_id") == backtest_id:
            _fail("R267 retry reused a prior backtest identity")
    if (
        type(backtest_id) is not str or not _ID.fullmatch(backtest_id)
        or launched.get("projectId") != project_id
        or launched.get("name") != plan.backtest_name
        or launched.get("status") not in {"In Queue...", "In Progress..."}
    ):
        _fail("R267 launch identity changed")
    receipt = {
        "candidate_id": plan.candidate_id, "attempt": plan.attempt,
        "project_id": project_id, "project_name": plan.project_name,
        "compile_id": compile_id, "backtest_id": backtest_id,
        "backtest_name": plan.backtest_name,
        "projection_sha256": plan.projection_sha256,
        "profile_sha256": plan.profile_sha256,
    }
    common._write_once(_path(plan, "launch"), receipt)
    return receipt


def poll_status(plan, receipt, api):
    """Status-only bounded poll; never access logs or economic statistics."""
    common._client(api)
    if common._read_control(_path(plan, "launch")) != receipt:
        _fail("R267 launch receipt changed")
    terminal_path = _path(plan, "terminal")
    if terminal_path.exists():
        return common._read_control(terminal_path)["status"]
    result = _post(api, "backtests/list", {
        "projectId": receipt["project_id"], "includeStatistics": False,
    })
    rows = result.get("backtests")
    if type(rows) is not list or result.get("count", len(rows)) != len(rows):
        _fail("R267 status inventory changed")
    matches = [item for item in rows if type(item) is dict and item.get("backtestId") == receipt["backtest_id"]]
    if len(matches) != 1:
        _fail("R267 exact backtest status is absent")
    item = matches[0]
    status = item.get("status")
    if (
        item.get("name") != receipt["backtest_name"]
        or ("projectId" in item and item["projectId"] != receipt["project_id"])
        or status not in {"In Queue...", "In Progress...", "Completed.", "Runtime Error"}
    ):
        _fail("R267 terminal identity changed")
    if status in {"Completed.", "Runtime Error"}:
        common._write_once(terminal_path, {
            "candidate_id": plan.candidate_id, "attempt": plan.attempt,
            "project_id": receipt["project_id"],
            "backtest_id": receipt["backtest_id"], "status": status,
        })
    return status


def _strict_statistic(value):
    if type(value) is not str or not value.isascii():
        _fail("R267 statistic is not ASCII")
    raw = value.encode("ascii")
    if not 0 < len(raw) <= runtime.MAXIMUM_STATISTIC_BYTES:
        _fail("R267 statistic exceeded its byte bound")
    try:
        record = json.loads(value, parse_constant=lambda _: None)
    except ValueError:
        raise EightInputQcSubmissionError("R267 statistic is not JSON") from None
    if type(record) is not dict or _canonical(record) != raw:
        _fail("R267 statistic is not canonical JSON")
    return record


def _checked_overlap_counts(value, *, annual=False):
    template = runtime._empty_overlap()
    if type(value) is not dict or set(value) != set(template) | ({"year"} if annual else set()):
        _fail("R267 overlap field inventory changed")
    if annual and (type(value["year"]) is not int or value["year"] not in runtime.YEARS):
        _fail("R267 overlap year changed")
    for name, example in template.items():
        observed = value[name]
        if type(example) is int:
            if type(observed) is not int or not 0 <= observed <= runtime._six.MAXIMUM_TOTAL_SOURCE_ROWS:
                _fail("R267 overlap count changed")
        elif type(observed) is not dict or set(observed) != set(example) or any(
            type(item) is not int or not 0 <= item <= runtime._six.MAXIMUM_TOTAL_SOURCE_ROWS
            for item in observed.values()
        ):
            _fail("R267 overlap histogram changed")
    if (
        value["unique_positive_sid_sum"] > value["positive_memberships_sum"]
        or value["unique_mapped_security_sum"] > value["mapped_memberships_sum"]
        or value["unique_cap_eligible_security_sum"] > value["cap_eligible_memberships_sum"]
        or value["duplicate_positive_sid_memberships_sum"]
        != value["positive_memberships_sum"] - value["unique_positive_sid_sum"]
        or value["duplicate_cap_eligible_memberships_sum"]
        != value["cap_eligible_memberships_sum"] - value["unique_cap_eligible_security_sum"]
    ):
        _fail("R267 overlap accounting changed")


def _checked_sleeve_counts(value, *, annual=False):
    template = runtime._empty_counts()
    old = runtime._six._empty_counts()
    if type(value) is not dict or set(value) != set(template) | ({"year"} if annual else set()):
        _fail("R267 sleeve count field inventory changed")
    core = {key: value[key] for key in old}
    if annual:
        core["year"] = value["year"]
    common._checked_counts(core, annual=annual)
    relaxed = value["relaxed_joint_pass_10_verified3_count"]
    age_bins = value["constituent_callback_age_bins"]
    if (
        type(relaxed) is not int or not 0 <= relaxed <= value["measurable_count"]
        or type(age_bins) is not dict
        or set(age_bins) != set(template["constituent_callback_age_bins"])
        or any(type(number) is not int or not 0 <= number <= value["decision_count"]
               for number in age_bins.values())
        or sum(age_bins.values()) != value["decision_count"]
        or relaxed > age_bins["age_1"] + age_bins["age_2"] + age_bins["age_3"]
                   + age_bins["age_4"] + age_bins["age_5"]
    ):
        _fail("R267 relaxed admission or callback-age count changed")


def parse_counts_response(response, plan, receipt):
    """Parse exactly ten hash-bound count objects; never retain QC outcomes."""
    backtest = response.get("backtest")
    if type(backtest) is not dict or (
        backtest.get("projectId") != receipt["project_id"]
        or backtest.get("backtestId") != receipt["backtest_id"]
        or backtest.get("name") != receipt["backtest_name"]
        or backtest.get("status") != "Completed."
    ):
        _fail("R267 result identity changed")
    statistics = backtest.get("statistics")
    if type(statistics) is not dict:
        _fail("R267 statistics mapping is absent")
    expected = runtime.expected_custom_summary_statistic_names()
    selected = tuple(sorted(
        key for key in statistics if type(key) is str and key.startswith("ARV2_EIGHT_INPUT_")
    ))
    if selected != expected:
        _fail("R267 custom statistic inventory changed")
    parsed = {name: _strict_statistic(statistics[name]) for name in expected}
    meta = parsed[runtime.META_STATISTIC_NAME]
    if (
        set(meta) != {
            "schema", "profile_id", "profile_sha256", "package_id",
            "package_sha256", "activation_manifest_sha256", "symbol_resolution_id",
            "symbol_resolution_sha256", "decision_count", "sleeve_decision_count",
            "callback_source_row_count", "input_path_sha256", "sleeve_sha256s",
            "overlap_sha256", "aggregate_sha256", "raw_rows_or_identifiers_emitted",
            "price_or_return_access", "orders", "backtest_only",
        }
        or meta["schema"] != runtime.META_SCHEMA
        or meta["profile_id"] != runtime._PROFILE["profile_id"]
        or meta["profile_sha256"] != plan.profile_sha256
        or meta["package_sha256"] != _manifest()["package_sha256"]
        or meta["activation_manifest_sha256"] != _manifest()["activation_manifest_sha256"]
        or meta["decision_count"] != runtime.EXPECTED_DECISION_COUNT
        or meta["sleeve_decision_count"] != 8 * runtime.EXPECTED_DECISION_COUNT
        or type(meta["callback_source_row_count"]) is not int
        or not 0 <= meta["callback_source_row_count"] <= runtime._six.MAXIMUM_TOTAL_SOURCE_ROWS
        or any(type(meta[key]) is not str or not _HEX.fullmatch(meta[key]) for key in (
            "symbol_resolution_sha256", "input_path_sha256", "overlap_sha256", "aggregate_sha256"
        ))
        or meta["raw_rows_or_identifiers_emitted"] is not False
        or meta["price_or_return_access"] is not False
        or meta["orders"] is not False
        or meta["backtest_only"] is not True
    ):
        _fail("R267 metadata changed")
    digests = meta["sleeve_sha256s"]
    if type(digests) is not dict or set(digests) != set(runtime.UNIVERSE_IDS):
        _fail("R267 sleeve digest inventory changed")
    sleeves = []
    for ticker in runtime.UNIVERSE_IDS:
        row = parsed[runtime.SLEEVE_STATISTIC_PREFIX + ticker]
        if (
            type(row) is not dict or set(row) != {"schema", "universe_id", "totals", "years"}
            or row["schema"] != runtime.SLEEVE_SCHEMA
            or row["universe_id"] != ticker or digests[ticker] != _sha(row)
        ):
            _fail("R267 sleeve identity or digest changed")
        _checked_sleeve_counts(row["totals"])
        years = row["years"]
        if type(years) is not list or len(years) != len(runtime.YEARS):
            _fail("R267 annual count inventory changed")
        for year, annual in zip(runtime.YEARS, years):
            _checked_sleeve_counts(annual, annual=True)
            if annual["year"] != year:
                _fail("R267 annual count order changed")
        if (
            row["totals"]["decision_count"] != runtime.EXPECTED_DECISION_COUNT
            or sum(item["decision_count"] for item in years) != runtime.EXPECTED_DECISION_COUNT
            or row["totals"]["relaxed_joint_pass_10_verified3_count"]
            != sum(item["relaxed_joint_pass_10_verified3_count"] for item in years)
            or any(
                row["totals"]["constituent_callback_age_bins"][key]
                != sum(item["constituent_callback_age_bins"][key] for item in years)
                for key in runtime._empty_counts()["constituent_callback_age_bins"]
            )
        ):
            _fail("R267 sleeve decision census changed")
        sleeves.append(row)
    overlap = parsed[runtime.OVERLAP_STATISTIC_NAME]
    if type(overlap) is not dict or set(overlap) != {"schema", "totals", "years"} or overlap["schema"] != runtime.OVERLAP_SCHEMA:
        _fail("R267 overlap schema changed")
    _checked_overlap_counts(overlap["totals"])
    if type(overlap["years"]) is not list or len(overlap["years"]) != len(runtime.YEARS):
        _fail("R267 overlap annual inventory changed")
    for year, annual in zip(runtime.YEARS, overlap["years"]):
        _checked_overlap_counts(annual, annual=True)
        if annual["year"] != year:
            _fail("R267 overlap annual order changed")
    if (
        overlap["totals"]["decision_count"] != runtime.EXPECTED_DECISION_COUNT
        or sum(item["decision_count"] for item in overlap["years"]) != runtime.EXPECTED_DECISION_COUNT
        or meta["overlap_sha256"] != _sha(overlap)
        or meta["aggregate_sha256"] != _sha(sleeves + [overlap])
    ):
        _fail("R267 aggregate digest or decision census changed")
    return {"meta": meta, "sleeves": dict(zip(runtime.UNIVERSE_IDS, sleeves)), "overlap": overlap}


def read_counts_once(plan, receipt, api):
    common._client(api)
    if common._read_control(_path(plan, "launch")) != receipt:
        _fail("R267 launch receipt changed")
    terminal = common._read_control(_path(plan, "terminal"))
    if terminal.get("status") != "Completed." or terminal.get("backtest_id") != receipt["backtest_id"]:
        _fail("R267 run did not complete exactly")
    common._write_once(_path(plan, "result-read-claim"), {
        "candidate_id": plan.candidate_id, "attempt": plan.attempt,
        "project_id": receipt["project_id"], "backtest_id": receipt["backtest_id"],
    })
    response = _post(api, "backtests/read", {
        "projectId": receipt["project_id"], "backtestId": receipt["backtest_id"],
    })
    counts = parse_counts_response(response, plan, receipt)
    raw_statistics = response["backtest"]["statistics"]
    expected = runtime.expected_custom_summary_statistic_names()
    common._write_once(_path(plan, "raw-custom"), {
        "candidate_id": plan.candidate_id, "attempt": plan.attempt,
        "project_id": receipt["project_id"],
        "backtest_id": receipt["backtest_id"],
        "backtest_name": receipt["backtest_name"],
        "projection_sha256": plan.projection_sha256,
        "profile_sha256": plan.profile_sha256,
        "statistics": {name: raw_statistics[name] for name in expected},
    })
    common._write_once(_path(plan, "result"), counts)
    return counts


__all__ = (
    "EightInputQcPlan", "EightInputQcSubmissionError", "build_plan",
    "preview", "launch", "poll_status", "read_counts_once",
    "parse_counts_response",
)
