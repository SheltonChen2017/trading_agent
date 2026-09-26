"""Bounded exploratory QC launches from a committed, byte-pinned manifest.

Research-only owner signature waiver; no live, broker or deployment capability.
Each candidate has three atomic attempt slots, one project, and one result read
per launch. Existing historical candidate registries remain untouched.
"""

import dataclasses
import hashlib
import json
import os
from pathlib import Path
import stat
import time

from . import six_universe_cap90_submission as cap
from . import six_universe_recent_settlement_submission as recent
from . import six_universe_settlement_submission as common


FROZEN_MANIFEST_SHA256 = "70cd295d6883f32d387c5de1ccb2827dae8fb8f07e70d9dbd55bab34351d39c6"
PREDECESSOR_MANIFEST_SHA256 = None  # Stage-one R209 manifest, retained unchanged.
MANIFEST_PATH = Path(__file__).with_name("six_universe_relaxed_candidates.json")
_TERMINAL = {"Completed.", "Runtime Error", "BuildError"}
_GEOMETRY = ("2025-08-01", "2026-09-25", 290, 61)
_TICKERS = ("SPY", "QQQ", "SOXX", "XLV", "REMX", "XLE")


class RelaxedQcSubmissionError(ValueError):
    pass


def _fail(message):
    raise RelaxedQcSubmissionError(message)


def _sha(value):
    return hashlib.sha256(common._canonical(value)).hexdigest()


def _manifest():
    raw = MANIFEST_PATH.read_bytes()
    if (type(FROZEN_MANIFEST_SHA256) is not str
            or hashlib.sha256(raw).hexdigest() != FROZEN_MANIFEST_SHA256):
        _fail("relaxed family is not the frozen manifest")
    value = json.loads(raw)
    if (type(value) is not dict or type(value.get("candidates")) is not list
            or len(value["candidates"]) not in {1, 11}):
        _fail("relaxed family manifest shape changed")
    ids = [row.get("candidate_id") for row in value["candidates"] if type(row) is dict]
    if ids not in (["R209"], ["R" + str(number) for number in range(209, 220)]):
        _fail("relaxed family candidate census changed")
    return value


@dataclasses.dataclass(frozen=True)
class RelaxedQcPlan:
    candidate_id: str
    organization_id: str = dataclasses.field(repr=False)
    control_directory: Path
    attempt: int = 1


def _candidate(plan):
    if (type(plan) is not RelaxedQcPlan or type(plan.attempt) is not int
            or not 1 <= plan.attempt <= 3
            or type(plan.organization_id) is not str
            or not cap._ORG.fullmatch(plan.organization_id)
            or not isinstance(plan.control_directory, Path)
            or not plan.control_directory.is_absolute()):
        _fail("relaxed plan or three-attempt bound changed")
    rows = [row for row in _manifest()["candidates"]
            if row["candidate_id"] == plan.candidate_id]
    if len(rows) != 1:
        _fail("relaxed candidate is not frozen")
    return rows[0]


def build_plan(candidate_id, organization_id, control_directory, attempt=1):
    plan = RelaxedQcPlan(candidate_id, organization_id, Path(control_directory), attempt)
    _candidate(plan)
    return plan


def _path(plan, suffix, *, attempt=None):
    _candidate(plan)
    if suffix not in {"claim", "project", "launch", "terminal", "read-claim", "raw-custom", "result"}:
        _fail("relaxed control suffix changed")
    root = plan.control_directory
    root.mkdir(mode=0o700, parents=False, exist_ok=True)
    info = root.stat(follow_symlinks=False)
    if (not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700
            or info.st_uid != os.getuid()):
        _fail("relaxed control directory is not private")
    slot = plan.attempt if attempt is None else attempt
    stem = plan.candidate_id if suffix == "project" else f"{plan.candidate_id}-A{slot}"
    return root / f"{stem}-{suffix}.json"


def preview(plan, projection):
    row, family = _candidate(plan), _manifest()
    for key in ("projection_sha256", "profile_id", "profile_sha256"):
        if getattr(projection, key, None) != row[key]:
            _fail("relaxed projection or profile changed")
    if (projection.schema != row["projection_schema"]
            or projection.package_sha256 != family["package_sha256"]
            or projection.activation_manifest_sha256 != family["activation_manifest_sha256"]
            or (row["kind"] == "order" and projection.role != row["role"])):
        _fail("relaxed projection role or input changed")
    record = projection.to_record()
    semantic = {key: value for key, value in record.items()
                if key not in {"projection_id", "projection_sha256"}}
    if _sha(semantic) != row["projection_sha256"]:
        _fail("relaxed projection is not self authenticating")
    files = []
    for item in projection.source_files:
        raw, path = item.source_bytes, item.project_path
        if (type(raw) is not bytes or not 0 < len(raw) <= 64_000
                or type(path) is not str or not cap._PATH.fullmatch(path)
                or Path(path).is_absolute() or ".." in Path(path).parts
                or item.byte_count != len(raw)
                or hashlib.sha256(raw).hexdigest() != item.content_sha256):
            _fail("relaxed source file changed")
        try:
            text = raw.decode("ascii")
            compile(text, path, "exec")
            compile("from AlgorithmImports import *\n" + text, path, "exec")
        except (SyntaxError, UnicodeError):
            _fail("relaxed source is not prelude safe")
        files.append([path, item.content_sha256, len(raw)])
    names = [item[0] for item in files]
    total = sum(item[2] for item in files)
    if (names != sorted(set(names)) or "main.py" not in names
            or len(files) != row["source_file_count"]
            or total != row["total_source_bytes"]
            or projection.total_source_byte_count != total
            or _sha(files) != row["source_files_sha256"]
            or total + 32_768 > (448 * 1024 if row["kind"] == "order" else 320 * 1024)):
        _fail("relaxed source closure or size changed")
    return {"candidate_id": plan.candidate_id, "attempt": plan.attempt,
            "manifest_sha256": FROZEN_MANIFEST_SHA256, "candidate_sha256": _sha(row),
            "projection_sha256": row["projection_sha256"],
            "profile_id": row["profile_id"], "profile_sha256": row["profile_sha256"],
            "package_sha256": family["package_sha256"],
            "activation_manifest_sha256": family["activation_manifest_sha256"],
            "source_files": files, "authority": "owner_exploratory_signature_waiver"}


def _require_inputs(plan):
    family = _manifest()
    control = Path(family["input_control_directory"])
    prior_plan = recent.build_plan("R203", plan.organization_id, control)
    if (prior_plan.package_sha256 != family["package_sha256"]
            or prior_plan.activation_manifest_sha256 != family["activation_manifest_sha256"]):
        _fail("relaxed uploaded input binding changed")
    recent.require_uploaded_inputs(prior_plan)


def _project(plan, api, project_id):
    rows = common._post(api, "projects/read", {"projectId": project_id}).get("projects")
    candidate = _candidate(plan)
    if type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict:
        _fail("relaxed exact project unavailable")
    row = rows[0]
    collaborators = row.get("collaborators")
    if (row.get("projectId") != project_id or row.get("name") != candidate["project_name"]
            or row.get("organizationId") != plan.organization_id
            or row.get("language") != "Py" or row.get("owner") is not True
            or row.get("codeRunning") is not False
            or row.get("public", False) is not False
            or type(collaborators) is not list or len(collaborators) > 1
            or any(type(item) is not dict or item.get("owner") is not True
                   for item in collaborators)):
        _fail("relaxed project is not exact private owned and idle")


def _files(plan, api, project_id, identity):
    rows = common._post(api, "files/read", {"projectId": project_id}).get("files")
    if type(rows) is not list or len(rows) != len(identity["source_files"]):
        _fail("relaxed current source inventory changed")
    observed = []
    for row in rows:
        if (type(row) is not dict or row.get("projectId") != project_id
                or type(row.get("name")) is not str or type(row.get("content")) is not str):
            _fail("relaxed current source identity changed")
        try:
            raw = row["content"].encode("ascii")
        except UnicodeError:
            _fail("relaxed current source is not ASCII")
        observed.append([row["name"], hashlib.sha256(raw).hexdigest(), len(raw)])
    if sorted(observed) != identity["source_files"]:
        _fail("relaxed current source bytes changed")


def _receipt(plan, launch):
    row = _candidate(plan)
    identity = common._read(_path(plan, "claim"))
    family = _manifest()
    accepted_manifests = {FROZEN_MANIFEST_SHA256}
    if plan.candidate_id == "R209" and type(PREDECESSOR_MANIFEST_SHA256) is str:
        accepted_manifests.add(PREDECESSOR_MANIFEST_SHA256)
    if (identity.get("manifest_sha256") not in accepted_manifests
            or identity.get("candidate_sha256") != _sha(row)
            or identity.get("candidate_id") != plan.candidate_id
            or identity.get("attempt") != plan.attempt
            or identity.get("projection_sha256") != row["projection_sha256"]
            or identity.get("profile_id") != row["profile_id"]
            or identity.get("profile_sha256") != row["profile_sha256"]
            or identity.get("package_sha256") != family["package_sha256"]
            or identity.get("activation_manifest_sha256") != family["activation_manifest_sha256"]
            or _sha(identity.get("source_files")) != row["source_files_sha256"]
            or type(launch) is not dict or common._read(_path(plan, "launch")) != launch
            or any(launch.get(key) != value for key, value in identity.items())
            or launch.get("project_name") != row["project_name"]
            or launch.get("backtest_name") != f'{row["backtest_name"]} A{plan.attempt}'
            or type(launch.get("project_id")) is not int
            or type(launch.get("backtest_id")) is not str
            or not cap._ID.fullmatch(launch["backtest_id"])):
        _fail("relaxed launch claim changed")
    return identity


def launch(plan, projection, api):
    """One atomic attempt; subsequent attempts reuse the recorded project."""
    identity, row = preview(plan, projection), _candidate(plan)
    _require_inputs(plan)
    common._client(api)
    if _path(plan, "claim").exists():
        _fail("relaxed attempt is already consumed")
    for slot in range(1, plan.attempt):
        terminal = common._read(_path(plan, "terminal", attempt=slot))
        if (terminal.get("status") not in _TERMINAL
                or terminal.get("status") == "Completed."
                and common._read(_path(plan, "result", attempt=slot)).get("run_valid") is not False):
            _fail("relaxed retry predecessor is not an unsuccessful terminal run")
    common._post(api, "authenticate", {})
    project_path = _path(plan, "project")
    if plan.attempt == 1:
        listing = common._post(api, "projects/read", {}).get("projects")
        if (type(listing) is not list or any(type(item) is not dict
                or item.get("name") == row["project_name"] for item in listing)):
            _fail("relaxed project name is not fresh")
    else:
        receipt = common._read(project_path)
        project_id = receipt["project_id"]
        if receipt.get("candidate_id") != plan.candidate_id:
            _fail("relaxed retry project receipt changed")
        _project(plan, api, project_id)
    common._write(_path(plan, "claim"), identity)  # Atomic O_EXCL before mutation.
    if plan.attempt == 1:
        rows = common._post(api, "projects/create", {"name": row["project_name"],
            "language": "Py", "organizationId": plan.organization_id}).get("projects")
        if (type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict
                or type(rows[0].get("projectId")) is not int or rows[0]["projectId"] <= 0):
            _fail("relaxed created project identity changed; attempt remains spent")
        project_id = rows[0]["projectId"]
        common._write(project_path, {"candidate_id": plan.candidate_id,
            "project_id": project_id, "project_name": row["project_name"]})
        _project(plan, api, project_id)
    initial = common._post(api, "files/read", {"projectId": project_id}).get("files")
    if type(initial) is not list or any(type(item) is not dict for item in initial):
        _fail("relaxed initial source unavailable")
    names = [item.get("name") for item in initial]
    expected = {item.project_path for item in projection.source_files}
    if (len(names) != len(set(names)) or any(name not in expected | {"research.ipynb"}
            for name in names)):
        _fail("relaxed initial source has unrelated files")
    if "research.ipynb" in names:
        common._post(api, "files/delete", {"projectId": project_id, "name": "research.ipynb"})
    for item in projection.source_files:
        common._post(api, "files/update" if item.project_path in names else "files/create",
            {"projectId": project_id, "name": item.project_path,
             "content": item.source_bytes.decode("ascii")})
    _files(plan, api, project_id, identity)
    compile_id = common._post(api, "compile/create", {"projectId": project_id}).get("compileId")
    if type(compile_id) is not str or not cap._ID.fullmatch(compile_id):
        _fail("relaxed compile identity changed; attempt remains spent")
    for poll in range(120):
        response = common._post(api, "compile/read", {"projectId": project_id, "compileId": compile_id})
        state = response.get("state")
        if response.get("compileId") != compile_id or state not in {"InQueue", "Building", "BuildSuccess", "BuildError"}:
            _fail("relaxed compile envelope changed; attempt remains spent")
        if state in {"BuildSuccess", "BuildError"}:
            break
        time.sleep(2)
    else:
        _fail("relaxed compile poll exhausted; attempt remains spent")
    if state == "BuildError":
        common._write(_path(plan, "terminal"), {**identity, "project_id": project_id,
            "compile_id": compile_id, "status": "BuildError"})
        _fail("relaxed compile failed; attempt consumed")
    name = f'{row["backtest_name"]} A{plan.attempt}'
    value = common._post(api, "backtests/create", {"projectId": project_id,
        "compileId": compile_id, "backtestName": name}).get("backtest")
    if (type(value) is not dict or value.get("projectId") != project_id
            or value.get("name") != name or type(value.get("backtestId")) is not str
            or not cap._ID.fullmatch(value["backtestId"])
            or value.get("status") not in {"In Queue...", "In Progress..."}):
        _fail("relaxed launched run identity changed; attempt remains spent")
    receipt = {**identity, "project_id": project_id, "project_name": row["project_name"],
        "compile_id": compile_id, "backtest_id": value["backtestId"], "backtest_name": name}
    common._write(_path(plan, "launch"), receipt)
    return receipt


def poll_status(plan, launch_receipt, api):
    _receipt(plan, launch_receipt)
    terminal = _path(plan, "terminal")
    if terminal.exists():
        return common._read(terminal)["status"]
    listing = common._post(api, "backtests/list", {"projectId": launch_receipt["project_id"],
        "includeStatistics": False})
    rows = listing.get("backtests")
    if type(rows) is not list or listing.get("count", len(rows)) != len(rows):
        _fail("relaxed status inventory changed")
    matches = [row for row in rows if type(row) is dict
        and row.get("backtestId") == launch_receipt["backtest_id"]]
    if (len(matches) != 1 or matches[0].get("name") != launch_receipt["backtest_name"]
            or matches[0].get("projectId", launch_receipt["project_id"]) != launch_receipt["project_id"]
            or matches[0].get("status") not in {"In Queue...", "In Progress...", "Completed.", "Runtime Error"}):
        _fail("relaxed exact status identity changed")
    status = matches[0]["status"]
    if status in _TERMINAL:
        common._write(terminal, {"candidate_id": plan.candidate_id, "attempt": plan.attempt,
            "project_id": launch_receipt["project_id"], "backtest_id": launch_receipt["backtest_id"],
            "status": status})
    return status


def _statistic(value):
    if type(value) is not str:
        _fail("relaxed custom statistic is not text")
    try:
        raw = value.encode("ascii")
        parsed = json.loads(raw)
    except (UnicodeError, ValueError):
        _fail("relaxed statistic is not ASCII JSON")
    if not 0 < len(raw) <= 8192 or type(parsed) is not dict or common._canonical(parsed) != raw:
        _fail("relaxed custom statistic is not bounded canonical JSON")
    return parsed


def _parse_order(plan, statistics):
    row, family = _candidate(plan), _manifest()
    meta_name = next(name for name in row["statistic_names"] if name.endswith("META"))
    agg_name = next(name for name in row["statistic_names"] if name.endswith("AGGREGATES"))
    meta, aggregate = _statistic(statistics[meta_name]), _statistic(statistics[agg_name])
    if (set(meta) != cap._META_FIELDS or meta.get("schema") != row["meta_schema"]
            or meta.get("role") != row["role"]
            or meta.get("profile_id") != row["profile_id"]
            or meta.get("profile_sha256") != row["profile_sha256"]
            or meta.get("package_sha256") != family["package_sha256"]
            or meta.get("activation_manifest_sha256") != family["activation_manifest_sha256"]
            or meta.get("aggregate_schema") != row["summary_schema"]
            or meta.get("aggregate_sha256") != hashlib.sha256(statistics[agg_name].encode("ascii")).hexdigest()
            or meta.get("result_transport") != "two_bounded_custom_summary_statistics"
            or any(meta.get(key) is not False for key in ("raw_provider_rows", "raw_price_rows", "raw_order_rows", "formal", "trading"))
            or meta.get("preliminary") is not True or meta.get("backtest_only") is not True):
        _fail("relaxed outcome metadata or raw-text digest changed")
    fields = cap._AGGREGATE_FIELDS | common._SETTLEMENT_FIELDS | common._TILT_FIELDS
    if (set(aggregate) != fields or aggregate.get("schema") != row["summary_schema"]
            or aggregate.get("role") != row["role"]
            or aggregate.get("profile_id") != row["profile_id"]
            or aggregate.get("profile_sha256") != row["profile_sha256"]
            or aggregate.get("maximum_stock_weight_change_fraction") != row["tilt_fraction"]
            or aggregate.get("matched_baseline_profile_sha256") != row["matched_baseline_profile_sha256"]
            or any(aggregate.get(key) is not False for key in ("formal", "live_orders", "paper_orders", "funded_orders", "deployment", "trading"))
            or any(aggregate.get(key) is not True for key in ("preliminary", "backtest_only", "daily_cash_nonnegative", "settled_cash_nonnegative", "negative_cash_requires_pending_sell_moo"))
            or aggregate.get("admission_leverage") != "2"
            or aggregate.get("target_gross_exposure") != "0.98"
            or aggregate.get("maximum_mean_target_weight_l1_error") != "0.02"
            or aggregate.get("maximum_single_target_weight_l1_error") != "0.05"
            or aggregate.get("cash_observation_granularity") != "daily_close_and_post_order_event_not_continuous_intraday"
            or type(aggregate.get("unexplained_negative_order_event_count")) is not int
            or aggregate["unexplained_negative_order_event_count"] != 0):
        _fail("relaxed aggregate identity or cash policy changed")
    selected = _bounded_order_base(aggregate)
    execution = aggregate["execution"]
    numeric = [aggregate["minimum_end_day_cash"], aggregate["maximum_gross_exposure"],
        execution.get("mean_target_weight_l1_error"), execution.get("maximum_target_weight_l1_error")]
    if any(not cap._finite_decimal(value) for value in numeric):
        _fail("relaxed cash or tracking is not finite")
    from decimal import Decimal
    cash, gross, mean, maximum = map(Decimal, numeric)
    if cash < 0 or gross < 0 or mean < 0 or maximum < 0:
        _fail("relaxed cash or tracking is negative")
    if (aggregate.get("end_day_gross_at_most_one") is not (gross <= 1)
            or aggregate.get("target_tracking_valid") is not (mean <= Decimal("0.02") and maximum <= Decimal("0.05"))
            or type(aggregate.get("run_valid")) is not bool):
        _fail("relaxed exposure or tracking flag is inconsistent")
    if aggregate["run_valid"] and (execution.get("run_valid") is not True
            or execution.get("execution_failure") is not False
            or execution.get("submitted_rebalance_count") != 61
            or execution.get("completed_rebalance_count") != 61
            or execution.get("submitted_order_count") != execution.get("filled_order_count_sum")
            or execution.get("invalid_order_count_sum") != 0 or execution.get("canceled_order_count_sum") != 0
            or aggregate["end_day_gross_at_most_one"] is not True
            or aggregate["target_tracking_valid"] is not True):
        _fail("relaxed valid flag disagrees with order evidence")
    selected.update({key: aggregate[key] for key in common._SETTLEMENT_FIELDS | common._TILT_FIELDS})
    return {"meta": meta, "aggregates": selected, "run_valid": aggregate["run_valid"]}


def _bounded_order_base(aggregate):
    """Reuse legacy shape checks without rewriting frozen status inventories.

    Validate the two new named states explicitly, map only a private temporary
    copy into legacy parser categories, then restore the original diagnostics.
    This is transport validation, not a change to producer selection semantics.
    """
    base = {key: aggregate[key] for key in cap._AGGREGATE_FIELDS}
    temporary = json.loads(common._canonical(base))
    new_status = "PARTIAL_STOCK_EXPOSURE_WITH_ETF_FALLBACK"
    new_reason = "KNOWN_MARKET_CAP_NAME_COUNT_BELOW_MINIMUM"
    def translate(counts, old, new, allowed):
        if not cap._bounded_counts(counts, keys=allowed | {new}):
            _fail("relaxed diagnostic named state or count changed")
        result = dict(counts)
        if new in result:
            result[old] = result.get(old, 0) + result.pop(new)
        return result
    temporary["fallback_counts"] = translate(temporary.get("fallback_counts"),
        "PARTIAL_STOCK_SLOTS_WITH_ETF_FALLBACK", new_status, cap._SELECTION_STATUSES)
    rows = temporary.get("sleeve_diagnostics", {}).get("rows")
    if type(rows) is not list or len(rows) != 6:
        _fail("relaxed sleeve diagnostic rows changed")
    for row in rows:
        if type(row) is not list or len(row) != 12:
            _fail("relaxed sleeve diagnostic row shape changed")
        row[10] = translate(row[10], "MARKET_CAP_WEIGHT_COVERAGE_BELOW_MINIMUM", new_reason,
                            cap._COVERAGE_REASONS)
        row[11] = translate(row[11], "PARTIAL_STOCK_SLOTS_WITH_ETF_FALLBACK", new_status,
                            cap._SELECTION_STATUSES)
    selected = cap._project_aggregate(temporary, expected_geometry=_GEOMETRY)
    selected["fallback_counts"] = dict(base["fallback_counts"])
    for selected_row, original in zip(selected["sleeve_diagnostics"]["rows"], base["sleeve_diagnostics"]["rows"]):
        selected_row[10], selected_row[11] = dict(original[10]), dict(original[11])
    return selected


def _parse_coverage(plan, statistics):
    row, family = _candidate(plan), _manifest()
    parsed = {name: _statistic(statistics[name]) for name in row["statistic_names"]}
    meta = parsed["ARV2_SIX_COVERAGE_META"]
    if (meta.get("schema") != row["meta_schema"] or meta.get("profile_id") != row["profile_id"]
            or meta.get("profile_sha256") != row["profile_sha256"]
            or meta.get("package_sha256") != family["package_sha256"]
            or meta.get("activation_manifest_sha256") != family["activation_manifest_sha256"]
            or meta.get("decision_count") != 61 or meta.get("sleeve_decision_count") != 366
            or any(meta.get(key) is not False for key in ("raw_rows_or_identifiers_emitted", "price_or_return_access", "orders"))
            or meta.get("backtest_only") is not True):
        _fail("relaxed coverage metadata changed")
    sleeves = [parsed["ARV2_SIX_COVERAGE_" + ticker] for ticker in _TICKERS]
    digests = meta.get("sleeve_sha256s")
    if type(digests) is not dict or set(digests) != set(_TICKERS):
        _fail("relaxed coverage sleeve digest inventory changed")
    for ticker, sleeve in zip(_TICKERS, sleeves):
        if (sleeve.get("schema") != row["sleeve_schema"] or sleeve.get("universe_id") != ticker
                or digests[ticker] != _sha(sleeve) or sleeve.get("totals", {}).get("decision_count") != 61
                or [year.get("year") for year in sleeve.get("years", [])] != [2025, 2026]
                or sum(year.get("decision_count", 0) for year in sleeve["years"]) != 61):
            _fail("relaxed coverage sleeve digest or census changed")
    if meta.get("aggregate_sha256") != _sha(sleeves):
        _fail("relaxed coverage aggregate digest changed")
    return {"meta": meta, "sleeves": dict(zip(_TICKERS, sleeves)), "run_valid": True}


def read_result_once(plan, launch_receipt, api):
    """One bounded custom-statistic read, never logs, prices or order rows."""
    identity, row = _receipt(plan, launch_receipt), _candidate(plan)
    terminal = common._read(_path(plan, "terminal"))
    expected = {"candidate_id": plan.candidate_id, "attempt": plan.attempt,
        "project_id": launch_receipt["project_id"], "backtest_id": launch_receipt["backtest_id"],
        "status": "Completed."}
    if terminal != expected:
        _fail("relaxed exact run has not completed")
    _project(plan, api, launch_receipt["project_id"])
    _files(plan, api, launch_receipt["project_id"], identity)
    common._write(_path(plan, "read-claim"), expected)
    response = common._post(api, "backtests/read", {"projectId": launch_receipt["project_id"],
        "backtestId": launch_receipt["backtest_id"]}).get("backtest")
    if (type(response) is not dict or response.get("projectId") != launch_receipt["project_id"]
            or response.get("backtestId") != launch_receipt["backtest_id"]
            or response.get("name") != launch_receipt["backtest_name"]
            or response.get("status") != "Completed."):
        _fail("relaxed result identity changed")
    statistics = response.get("statistics")
    prefix = "ARV2_SIX_COVERAGE_" if row["kind"] == "coverage" else "ARV2_SIX_GATE_ORDER_"
    if (type(statistics) is not dict or sorted(key for key in statistics
            if type(key) is str and key.startswith(prefix)) != sorted(row["statistic_names"])):
        _fail("relaxed custom statistic inventory changed")
    retained = {name: statistics[name] for name in row["statistic_names"]}
    # Preserve only allowlisted bounded canonical strings before lineage parse.
    # A future parser correction can recover locally, never consume a second read.
    for value in retained.values():
        _statistic(value)
    common._write(_path(plan, "raw-custom"), {**expected, "statistics": retained})
    result = (_parse_coverage if row["kind"] == "coverage" else _parse_order)(plan, retained)
    common._write(_path(plan, "result"), {**expected, **result,
        "manifest_sha256": FROZEN_MANIFEST_SHA256, "projection_sha256": row["projection_sha256"]})
    return result
