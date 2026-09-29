"""R268 A2 order-run drift diagnosis, bound to the spent A1 source.

The rendered QC source keeps A1's targets, orders, split authority, profile,
and validity rule. It adds a redacted rejection statistic to the original
three order statistics so a completed valid A2 can still be authenticated.
"""

import ast
import dataclasses
import hashlib
import json
from datetime import date

from . import accepted_risk_six_universe_order_qc_projection as base
from . import eight_universe_qcom_admitted_projection as renderer
from . import eight_universe_study as study
from . import six_universe_relaxed_submission as adapter
from . import six_universe_settlement_submission as common


MANIFEST_SCHEMA = "arv2-eight-r268-a2-holding-drift-diagnostic-manifest-v1"
PROJECTION_SCHEMA = "arv2-eight-r268-a2-holding-drift-diagnostic-projection-v1"
DIAGNOSTIC_SCHEMA = "arv2-eight-r268-a2-holding-drift-rejections-v1"
STATISTIC_NAME = "ARV2_EIGHT_GATE_ORDER_DRIFT_REJECTIONS"
CLASSIFICATIONS = frozenset({
    "missing_same_session_split_record",
    "split_adjusted_quantity_mismatch",
})
_TILT = "accepted_risk_six_universe_order_tilt_qc_runtime.py"
_BRIDGE = "accepted_risk_six_universe_order_bridge_qc_runtime.py"
_A1_MANIFEST_SHA256 = adapter.FROZEN_EIGHT_UNIVERSE_MANIFEST_SHA256


def _fail(message):
    adapter._fail(message)


def _a1_row():
    return adapter._eight_universe_manifest()["candidates"][0]


def _method(tree, class_name, method_name):
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)
               and node.name == class_name]
    if len(classes) != 1:
        _fail("R268 A2 source class anchor changed")
    methods = [node for node in classes[0].body if isinstance(node, ast.FunctionDef)
               and node.name == method_name]
    if len(methods) != 1:
        _fail("R268 A2 source method anchor changed")
    return classes[0], methods[0]


_DRIFT_METHOD = '''
def _holding_drift_replan(self, plan, observed_cash, observed_quantities, actual_time):
    # Call the unchanged A1 authority first. Classification is observational.
    result = super()._holding_drift_replan(
        plan, observed_cash, observed_quantities, actual_time)
    if result is not None:
        return result
    session = actual_time.date().isoformat()
    expected = dict(plan.starting_quantities)
    changed = tuple(sorted(
        security_id for security_id in set(expected) | set(observed_quantities)
        if expected.get(security_id, 0) != observed_quantities.get(security_id, 0)
    ))
    records = self._split_records_by_session.get(session, {})
    missing_ids = tuple(security_id for security_id in changed
                        if security_id not in records)
    if missing_ids:
        classification = "missing_same_session_split_record"
        rejected_count = len(missing_ids)
        private = getattr(self, "_r268_a2_missing_ids", None)
        if private is None:
            private = {}
            self._r268_a2_missing_ids = private
        if session in private:
            _base._error("R268 A2 missing-split session repeated")
        private[session] = missing_ids
    else:
        rejected_count = sum(
            _base.Decimal(expected.get(security_id, 0))
            / _base.Decimal(records[security_id]["split_factor"])
            != _base.Decimal(observed_quantities.get(security_id, 0))
            for security_id in changed
        )
        classification = "split_adjusted_quantity_mismatch"
    if not changed or not rejected_count:
        _base._error("R268 A2 drift rejection does not match A1 authority")
    prior = getattr(self, "_r268_a2_drift_rejections", None)
    if prior is None:
        prior = []
        self._r268_a2_drift_rejections = prior
    prior.append({
        "execution_session": session,
        "classification": classification,
        "changed_holding_count": len(changed),
        "rejected_holding_count": rejected_count,
    })
    return None
'''


def _render_tilt(source):
    tree = ast.parse(source)
    driver, original = _method(tree, "AcceptedRiskSixUniverseOrderTiltQcDriver",
                               "_bridge_expected_statistic_names")
    if (len(original.body) != 1 or not isinstance(original.body[0], ast.Return)
            or not isinstance(original.body[0].value, ast.Call)
            or not isinstance(original.body[0].value.func, ast.Name)
            or original.body[0].value.func.id != "expected_tilt_custom_statistic_names"):
        _fail("R268 A2 statistic inventory anchor changed")
    inventory = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name == "expected_tilt_custom_statistic_names"]
    if (len(inventory) != 1 or len(inventory[0].body) != 2
            or not isinstance(inventory[0].body[-1], ast.Return)
            or not isinstance(inventory[0].body[-1].value, ast.Call)):
        _fail("R268 A2 public statistic inventory anchor changed")
    inventory[0].body[-1].value = ast.Tuple(
        elts=[ast.Constant(name) for name in sorted((*study.STATISTIC_NAMES,
                                                     STATISTIC_NAME))],
        ctx=ast.Load())
    if any(isinstance(node, ast.FunctionDef) and node.name == "_holding_drift_replan"
           for node in driver.body):
        _fail("R268 A2 would replace an existing drift authority")
    driver.body.append(ast.parse(_DRIFT_METHOD).body[0])
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


_PAYLOAD_FUNCTION = '''
def _r268_a2_diagnostic_payload(driver, aggregate):
    execution = aggregate.get("execution")
    rejections = getattr(driver, "_r268_a2_drift_rejections", [])
    private = getattr(driver, "_r268_a2_missing_ids", {})
    if (type(execution) is not dict or type(rejections) is not list
            or type(private) is not dict):
        _error("R268 A2 drift execution census changed")
    skipped = execution.get("holding_drift_skipped_rebalance_count")
    if (type(skipped) is not int or not 0 <= skipped <= 261
            or len(rejections) != skipped
            or any(type(item) is not dict
                   or set(item) != {"execution_session", "classification",
                                    "changed_holding_count", "rejected_holding_count"}
                   for item in rejections)
            or len({item["execution_session"] for item in rejections}) != skipped
            or rejections != sorted(rejections,
                                    key=lambda item: item["execution_session"]) 
            or skipped and aggregate.get("run_valid") is not False):
        _error("R268 A2 drift rejection accounting changed")
    rows = []
    missing_sessions = set()
    for item in rejections:
        late = 0
        session = item["execution_session"]
        if item["classification"] == "missing_same_session_split_record":
            ids = private.get(session)
            if (type(ids) is not tuple
                    or len(ids) != item["rejected_holding_count"]):
                _error("R268 A2 private missing-split census changed")
            missing_sessions.add(session)
            later_records = driver._split_records_by_session.get(session, {})
            late = sum(security_id in later_records for security_id in ids)
        rows.append({**item, "late_split_record_count": late})
    if set(private) != missing_sessions:
        _error("R268 A2 private missing-split sessions changed")
    payload = {
        "schema": "arv2-eight-r268-a2-holding-drift-rejections-v1",
        "candidate_id": "R268",
        "attempt": 2,
        "a1_manifest_sha256": "b6802d0d7cffdc459db5e73de7ccd1e237ea0eaa412c4c44d182f759677e7b51",
        "a1_projection_sha256": "A1_PROJECTION_SHA256",
        "profile_sha256": aggregate["profile_sha256"],
        "run_valid": aggregate["run_valid"],
        "holding_drift_skip_count": skipped,
        "rejections": rows,
    }
    if len(_base._canonical(payload)) > 8192:
        _error("R268 A2 redacted drift statistic exceeded its bound")
    return payload
'''


def _render_bridge(source, a1_projection_sha256):
    tree = ast.parse(source)
    _, method = _method(tree, "BridgeAdmissionMixin", "on_end_of_algorithm")
    assignments = [node for node in method.body if isinstance(node, ast.Assign)
                   and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                   and node.targets[0].id == "statistics"]
    if len(assignments) != 1 or not isinstance(assignments[0].value, ast.Dict):
        _fail("R268 A2 bridge emission anchor changed")
    original_keys = [key.value for key in assignments[0].value.keys
                     if isinstance(key, ast.Constant)]
    if original_keys != ["ARV2_EIGHT_GATE_ORDER_META",
                         "ARV2_EIGHT_GATE_ORDER_AGGREGATES",
                         "ARV2_EIGHT_GATE_ORDER_DIAGNOSTICS"]:
        # The generated A1 dictionary can use named constants for the first two.
        if len(assignments[0].value.keys) != 3 or original_keys != [
                "ARV2_EIGHT_GATE_ORDER_DIAGNOSTICS"]:
            _fail("R268 A2 A1 statistic inventory changed")
    assignments[0].value.keys.append(ast.Constant(STATISTIC_NAME))
    assignments[0].value.values.append(ast.parse(
        '_base._canonical(_r268_a2_diagnostic_payload(self, aggregate)).decode("ascii")',
        mode="eval").body)
    payload = ast.parse(_PAYLOAD_FUNCTION.replace("A1_PROJECTION_SHA256",
                                                  a1_projection_sha256)).body[0]
    tree.body.append(payload)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def build_projection(package):
    """Return only R268 A2's 17-file, observational order source."""
    a1, profile = renderer.build_eight_universe_projection(package, "ar_off", "R268")
    row = _a1_row()
    if (a1.projection_sha256 != row["projection_sha256"]
            or a1.profile_sha256 != row["profile_sha256"]
            or profile["profile_sha256"] != row["profile_sha256"]):
        _fail("R268 A2 A1 source or strategy profile changed")
    sources = {}
    for item in a1.source_files:
        source = item.source_bytes.decode("ascii")
        if item.project_path == _TILT:
            source = _render_tilt(source)
        elif item.project_path == _BRIDGE:
            source = _render_bridge(source, a1.projection_sha256)
        sources[item.project_path] = source
    files = tuple(sorted((base._source_file(path, source.encode("ascii"))
                          for path, source in sources.items()),
                         key=lambda item: item.project_path))
    if (len(files) != 17
            or tuple(item.project_path for item in files) !=
               tuple(item.project_path for item in a1.source_files)
            or any(
            old.content_sha256 != new.content_sha256
            for old, new in zip(a1.source_files, files)
            if old.project_path not in {_TILT, _BRIDGE})):
        _fail("R268 A2 changed a non-diagnostic A1 source file")
    for item in files:
        base._audit_source(item.project_path, item.source_bytes)
    total = sum(item.byte_count for item in files)
    if total + base.MINIMUM_REVIEW_MARGIN_BYTES > base.MAXIMUM_TOTAL_SOURCE_BYTES:
        _fail("R268 A2 source closure exceeded QC budget")
    projection = dataclasses.replace(
        a1, schema=PROJECTION_SCHEMA,
        variant=a1.variant + "_a2_redacted_drift_diagnostic_v1",
        source_files=files, total_source_byte_count=total)
    record = {key: value for key, value in projection.to_record().items()
              if key not in ("projection_id", "projection_sha256")}
    digest = hashlib.sha256(base._canonical(record)).hexdigest()
    projection = dataclasses.replace(
        projection, projection_sha256=digest,
        projection_id="arv2-eight-r268-a2-drift-diagnostic-projection-" + digest[:24])
    return projection, profile


def freeze_manifest(package):
    """Compute the attempt-specific manifest for review before any QC I/O."""
    projection, _ = build_projection(package)
    a1 = _a1_row()
    files = [[item.project_path, item.content_sha256, item.byte_count]
             for item in projection.source_files]
    row = {**a1,
           "projection_schema": projection.schema,
           "projection_sha256": projection.projection_sha256,
           "source_files_sha256": hashlib.sha256(common._canonical(files)).hexdigest(),
           "source_file_count": len(files),
           "total_source_bytes": projection.total_source_byte_count,
           "statistic_names": [*study.STATISTIC_NAMES, STATISTIC_NAME]}
    return validate_manifest({
        "schema": MANIFEST_SCHEMA,
        "a1_manifest_sha256": _A1_MANIFEST_SHA256,
        "a1_projection_sha256": a1["projection_sha256"],
        "a1_profile_sha256": a1["profile_sha256"],
        "package_sha256": projection.package_sha256,
        "activation_manifest_sha256": projection.activation_manifest_sha256,
        "candidates": [row],
    })


def validate_manifest(value):
    """A2 may change only diagnostic source bytes and its statistic inventory."""
    a1 = _a1_row()
    if (type(value) is not dict
            or set(value) != {"schema", "a1_manifest_sha256",
                              "a1_projection_sha256", "a1_profile_sha256",
                              "package_sha256", "activation_manifest_sha256",
                              "candidates"}
            or value["schema"] != MANIFEST_SCHEMA
            or value["a1_manifest_sha256"] != _A1_MANIFEST_SHA256
            or value["a1_projection_sha256"] != a1["projection_sha256"]
            or value["a1_profile_sha256"] != a1["profile_sha256"]
            or value["package_sha256"] != adapter._eight_universe_manifest()["package_sha256"]
            or value["activation_manifest_sha256"] !=
               adapter._eight_universe_manifest()["activation_manifest_sha256"]
            or type(value["candidates"]) is not list
            or len(value["candidates"]) != 1
            or type(value["candidates"][0]) is not dict):
        _fail("R268 A2 manifest or A1 ancestry changed")
    row = value["candidates"][0]
    allowed = {"projection_schema", "projection_sha256", "source_files_sha256",
               "source_file_count", "total_source_bytes", "statistic_names"}
    if (set(row) != set(a1) or any(row[key] != a1[key] for key in a1
                                   if key not in allowed)
            or row["projection_schema"] != PROJECTION_SCHEMA
            or row["statistic_names"] != [*study.STATISTIC_NAMES, STATISTIC_NAME]
            or type(row["source_file_count"]) is not int
            or row["source_file_count"] != 17
            or type(row["total_source_bytes"]) is not int
            or not 0 < row["total_source_bytes"] + 32_768 <= 448 * 1024
            or any(type(row[key]) is not str or adapter.cap._HEX.fullmatch(row[key]) is None
                   for key in ("projection_sha256", "source_files_sha256"))
            or row["projection_sha256"] == a1["projection_sha256"]
            or row["source_files_sha256"] == a1["source_files_sha256"]):
        _fail("R268 A2 diagnostic source or A1 strategy fields changed")
    return value


def parse_result(plan, statistics):
    """Authenticate full order validity and the separate redacted diagnosis."""
    if (plan.family != "eight_universe" or plan.candidate_id != "R268"
            or plan.attempt != 2 or type(statistics) is not dict
            or set(statistics) != {*study.STATISTIC_NAMES, STATISTIC_NAME}):
        _fail("R268 A2 result attempt or statistic inventory changed")
    a1_plan = dataclasses.replace(plan, attempt=1)
    parsed = study.parse_order(a1_plan, {
        name: statistics[name] for name in study.STATISTIC_NAMES})
    payload = adapter._statistic(statistics[STATISTIC_NAME])
    a1 = _a1_row()
    if (set(payload) != {"schema", "candidate_id", "attempt",
                         "a1_manifest_sha256", "a1_projection_sha256",
                         "profile_sha256", "run_valid",
                         "holding_drift_skip_count", "rejections"}
            or payload["schema"] != DIAGNOSTIC_SCHEMA
            or payload["candidate_id"] != "R268" or payload["attempt"] != 2
            or payload["a1_manifest_sha256"] != _A1_MANIFEST_SHA256
            or payload["a1_projection_sha256"] != a1["projection_sha256"]
            or payload["profile_sha256"] != a1["profile_sha256"]
            or type(payload["run_valid"]) is not bool
            or payload["run_valid"] is not parsed["run_valid"]
            or type(payload["holding_drift_skip_count"]) is not int
            or not 0 <= payload["holding_drift_skip_count"] <= 261
            or type(payload["rejections"]) is not list
            or len(payload["rejections"]) != payload["holding_drift_skip_count"]):
        _fail("R268 A2 redacted diagnosis or A1 lineage changed")
    sessions = []
    for item in payload["rejections"]:
        if (type(item) is not dict
                or set(item) != {"execution_session", "classification",
                                 "changed_holding_count", "rejected_holding_count",
                                 "late_split_record_count"}
                or type(item["execution_session"]) is not str
                or type(item["classification"]) is not str
                or item["classification"] not in CLASSIFICATIONS
                or any(type(item[key]) is not int for key in (
                    "changed_holding_count", "rejected_holding_count",
                    "late_split_record_count"))
                or not 1 <= item["rejected_holding_count"] <= item["changed_holding_count"]
                or not 0 <= item["late_split_record_count"] <= item["rejected_holding_count"]
                or item["classification"] == "split_adjusted_quantity_mismatch"
                   and item["late_split_record_count"] != 0):
            _fail("R268 A2 rejection contains an unrecognized field or count")
        try:
            session = date.fromisoformat(item["execution_session"])
        except ValueError:
            _fail("R268 A2 rejection session is not canonical")
        if (session.isoformat() != item["execution_session"]
                or not date(2021, 1, 4) <= session <= date(2025, 12, 31)):
            _fail("R268 A2 rejection session is outside the order window")
        sessions.append(item["execution_session"])
    if sessions != sorted(set(sessions)):
        _fail("R268 A2 rejection sessions repeat or are unordered")
    if payload["run_valid"] and payload["holding_drift_skip_count"] != 0:
        _fail("R268 A2 valid baseline has a drift rejection")
    raw_aggregate = adapter._statistic(
        statistics[study.STATISTIC_NAMES[1]], eight_aggregate=True)
    raw_execution = raw_aggregate.get("execution")
    if (type(raw_execution) is not dict
            or type(raw_execution.get("holding_drift_skipped_rebalance_count")) is not int
            or payload["holding_drift_skip_count"] !=
               raw_execution["holding_drift_skipped_rebalance_count"]):
        _fail("R268 A2 rejection count disagrees with order execution")
    return {**parsed, "drift_diagnostic": payload}
