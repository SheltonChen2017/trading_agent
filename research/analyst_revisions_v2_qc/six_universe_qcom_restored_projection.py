"""Prospective QCOM-admitted versions of frozen QCOM-excluded order sources.

This is a source projection only. It cannot launch QC, read outcomes, or turn a
historical sensitivity into a confirmation result. The inverse is deliberately
limited to the exact exclusion introduced by the R231 renderer; coverage,
score-count, tilt, fees, slippage, and order timing remain in the predecessor.
"""

import ast
import dataclasses
import hashlib
import json
import re

from . import accepted_risk_matched_historical_projection as matched
from . import accepted_risk_six_universe_order_qc_projection as base
from . import accepted_risk_six_universe_order_relaxed_qc_projection as relaxed
from . import six_universe_qcom_exclusion_coverage10_projection as coverage10
from . import six_universe_qcom_exclusion_three_name_projection as three_name
from . import six_universe_qcom_entry_only_projection as entry_only


class QcomRestoredProjectionError(ValueError):
    """The frozen predecessor or an exact exclusion-removal anchor changed."""


PREDECESSOR_SHA256 = {
    "R231": "0c6a4c5a7cd3bffacb9d4148b5167fe0d1b38b8617b3c01fd974f2639a76704b",
    "R232": "87c3ecd2a36522f101086afeaf0bf19758757267f59035db2fb169e23bd3e803",
    "R233": "f1a6fb92823dea0c15a70ebef9b5dddebdfb9f5ba58be3e617815659832b02e5",
    "R234": "6637b2fa86e25135446d90af59af44ced2f9cde03d0f4dfa1d2c185d6aade1f9",
    "R235": "06842824c2fee60f447c4e920ee23634917958f94fa2332a9f21ea24eeed0aa1",
    "R236": "cc18bcdda7dc17750c186a403c8ec74568c4a7f71c528bdd4b714c00ef63c17b",
    "R237": "44b7e0dfcd31ecb1698e0b46196ebe4de80ca036d9273516b05f35dd65241f25",
    "R238": "26e4680967e6f4a6bc66b0fe7c3e4198cdab1db2f1a7357878f01952560fd654",
    "R239": "b3037679192d13cd931f22dd27ff7443ea328d17a7bed5d294bed3754f97dc9d",
    "R240": "bf62a1fcf62bee8d63a739d88220a8d8764a30b889baaa1bca0ef025a7264f4f",
    "R241": "ddaf84b437d347f43f789377b9629f90120d8418edfed3e7c596cfecf7e33f18",
    "R242": "829c370e58ebd1d398cc62a0acd5aca29885487f0353a5ff0ab7157afeb58ced",
    "R243": "ca4546db5e649d55da0fa266a8876760d487e7984559fc512d9c64bb0e42277d",
    "R244": "f72bc3f00065d259af10480ce7c2a99f55826da8ab419b50aab6529c7194b10c",
    "R245": "954aeea6c375659d7dfd6d8357cde1a70623287f4cdc7581f4e3a4070a650e35",
    "R246": "711bf00ec5dbefd45fda2e07c603800ec98e134d9e392582547f6f9186c43eff",
}

_GATE = relaxed._GATE_PATH
_ORDER = "accepted_risk_six_universe_order_qc_runtime.py"
_TILT = relaxed._TILT_RUNTIME_PATH
_MAIN = "main.py"
_REMOVAL_PATHS = frozenset({_GATE, _ORDER, _TILT, _MAIN})
_SCOPE = "all_six_stock_sleeves_all_decisions_2021_2025_coverage_denominators_unchanged"
_CANDIDATE_ID = re.compile(r"R[1-9][0-9]{2,3}\Z")


def _fail(message):
    raise QcomRestoredProjectionError(message)


def _function(tree, name):
    found = [node for node in ast.walk(tree)
             if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(found) != 1:
        _fail(f"QCOM-restored function anchor changed: {name}")
    return found[0]


def _assignment(tree, name):
    found = [node for node in tree.body if isinstance(node, ast.Assign)
             and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
             and node.targets[0].id == name]
    if len(found) != 1:
        _fail(f"QCOM-restored assignment anchor changed: {name}")
    return found[0]


def _remove_dict_keys(node, expected):
    if not isinstance(node, ast.Dict):
        _fail("QCOM-restored disclosure is no longer a literal dictionary")
    keys = [key.value if isinstance(key, ast.Constant) else None for key in node.keys]
    if any(keys.count(key) != 1 for key in expected):
        _fail("QCOM-restored exclusion disclosure keys changed")
    for key, expected_value in expected.items():
        index = keys.index(key)
        if ast.dump(node.values[index], include_attributes=False) != ast.dump(
                ast.parse(expected_value, mode="eval").body, include_attributes=False):
            _fail(f"QCOM-restored exclusion disclosure value changed: {key}")
    keep = [index for index, key in enumerate(keys) if key not in expected]
    node.keys[:] = [node.keys[index] for index in keep]
    node.values[:] = [node.values[index] for index in keep]


def _remove_exact_statement(function, source):
    expected = ast.parse(source).body[0]
    found = [node for node in function.body if ast.dump(node, include_attributes=False)
             == ast.dump(expected, include_attributes=False)]
    if len(found) != 1:
        _fail("QCOM-restored runtime exclusion guard changed")
    function.body.remove(found[0])


def strip_qcom_exclusion(path, source, *, security_id):
    """Remove exactly the frozen direct-stock QCOM exclusion, no other rule.

    The returned AST still bears its predecessor's QCOM-excluded versioned
    identities. A separate step versions the future project so a stripped
    source is never confused with the earlier result.
    """
    if type(path) is not str or type(source) is not str or not source.isascii():
        _fail("QCOM-restored source must have an exact ASCII path and body")
    if (type(security_id) is not str or hashlib.sha256(security_id.encode("utf-8")).hexdigest()
            != matched.QCOM_EXCLUSION_SECURITY_ID_SHA256):
        _fail("QCOM-restored security identity changed")
    tree = ast.parse(source)
    if path == _GATE:
        constants = {
            "EXCLUDED_QCOM_SECURITY_ID": security_id,
            "EXCLUDED_QCOM_SECURITY_ID_SHA256": matched.QCOM_EXCLUSION_SECURITY_ID_SHA256,
        }
        for name, expected in constants.items():
            assignment = _assignment(tree, name)
            if not isinstance(assignment.value, ast.Constant) or assignment.value.value != expected:
                _fail(f"QCOM-restored gate constant changed: {name}")
            tree.body.remove(assignment)
        semantic = _function(tree, "_profile_semantic")
        returns = [node.value for node in semantic.body if isinstance(node, ast.Return)]
        if len(returns) != 1:
            _fail("QCOM-restored gate profile return changed")
        _remove_dict_keys(returns[0], {
            "stock_exclusion_policy_id": repr(matched.QCOM_EXCLUSION_POLICY_ID),
            "excluded_logical_security_sha256": "EXCLUDED_QCOM_SECURITY_ID_SHA256",
            "stock_exclusion_scope": repr(_SCOPE),
        })
        sleeve = _function(tree, "_raw_sleeve")
        _remove_exact_statement(sleeve,
            "eligible_rows = tuple(row for row in rows if row.security_id != EXCLUDED_QCOM_SECURITY_ID)")
        selected = [node for node in sleeve.body if isinstance(node, ast.Assign)
                    and isinstance(node.value, ast.Call)
                    and ast.unparse(node.value.func) == "_selected_ids"]
        xle = [node for node in ast.walk(sleeve) if isinstance(node, ast.Assign)
               and any(isinstance(target, ast.Name) and target.id == "eligible"
                       for target in node.targets)]
        if (len(selected) != 1 or len(xle) != 1
                or ast.unparse(selected[0].value.args[0]) != "eligible_rows"
                or not isinstance(xle[0].value, ast.Call)
                or not isinstance(xle[0].value.args[0], ast.GeneratorExp)
                or ast.unparse(xle[0].value.args[0].generators[0].iter) != "eligible_rows"):
            _fail("QCOM-restored stock eligibility anchor changed")
        selected[0].value.args[0] = ast.Name("rows", ast.Load())
        xle[0].value.args[0].generators[0].iter = ast.Name("rows", ast.Load())
    elif path == _ORDER:
        _remove_exact_statement(_function(tree, "on_after_close"), '''
if (_gate.EXCLUDED_QCOM_SECURITY_ID in target_weights
        or _gate.EXCLUDED_QCOM_SECURITY_ID in holdings):
    _error("QCOM-excluded sensitivity contains an excluded target or holding")
''')
        _remove_exact_statement(_function(tree, "_reference_prices"), '''
if _gate.EXCLUDED_QCOM_SECURITY_ID in security_ids:
    _error("QCOM-excluded sensitivity requested an excluded reference")
''')
    elif path == _TILT:
        for function_name, target in (("require_tilt_profile", "seed.update"),
                                      ("_aggregate", "aggregate.update")):
            function = _function(tree, function_name)
            calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)
                     and ast.unparse(node.func) == target and len(node.args) == 1
                     and isinstance(node.args[0], ast.Dict)]
            if len(calls) != 1:
                _fail("QCOM-restored tilt disclosure anchor changed")
            _remove_dict_keys(calls[0].args[0], {
                "stock_exclusion_policy_id": repr(matched.QCOM_EXCLUSION_POLICY_ID),
                "excluded_logical_security_sha256": repr(matched.QCOM_EXCLUSION_SECURITY_ID_SHA256),
            })
    if path in _REMOVAL_PATHS:
        if any(isinstance(node, ast.Name) and node.id.startswith("EXCLUDED_QCOM")
               for node in ast.walk(tree)):
            _fail("QCOM-restored source retains an exclusion symbol")
        if any(isinstance(node, ast.Constant) and node.value in {
                "stock_exclusion_policy_id", "excluded_logical_security_sha256", "stock_exclusion_scope"}
               for node in ast.walk(tree)):
            _fail("QCOM-restored source retains an exclusion disclosure")
    ast.fix_missing_locations(tree)
    return tree


def render_qcom_admitted_source(path, source, *, security_id, new_candidate_id):
    """Version one exact predecessor file after removing its exclusion."""
    if (type(new_candidate_id) is not str or not _CANDIDATE_ID.fullmatch(new_candidate_id)
            or int(new_candidate_id[1:]) <= 247):
        _fail("QCOM-restored candidate identity is not a distinct R-number")
    tree = strip_qcom_exclusion(path, source, security_id=security_id)
    slug = new_candidate_id.lower()
    class Version(ast.NodeTransformer):
        def visit_Constant(self, node):
            if type(node.value) is str:
                node.value = (node.value.replace("qcom_excluded", f"qcom_admitted_{slug}")
                    .replace("qcom-excluded", f"qcom-admitted-{slug}")
                    .replace("QCOM-excluded", f"QCOM-admitted-{new_candidate_id}"))
            return node

        def visit_ClassDef(self, node):
            if "QcomExcluded" in node.name:
                node.name = node.name.replace("QcomExcluded", f"QcomAdmitted{new_candidate_id}")
            return self.generic_visit(node)

    tree = Version().visit(tree)
    ast.fix_missing_locations(tree)
    rendered = ast.unparse(tree) + "\n"
    if ast.dump(tree, include_attributes=False) != ast.dump(
            ast.parse(rendered), include_attributes=False):
        _fail("QCOM-restored source formatting changed executable AST")
    if "QCOM-excluded" in rendered or "qcom_excluded" in rendered or "qcom-excluded" in rendered:
        _fail("QCOM-restored source retains an exclusion identity")
    return rendered


def _predecessor(package, source_candidate_id):
    if source_candidate_id in ("R231", "R232", "R233", "R234"):
        arm = "ar_off" if source_candidate_id in ("R231", "R233") else "ar_on100"
        return matched.build_qcom_exclusion_projection(package, arm,
            5 if source_candidate_id in ("R233", "R234") else 0)
    if source_candidate_id in ("R235", "R236", "R237"):
        return matched.build_qcom_exclusion_tilt_projection(
            package, {"R235": 80, "R236": 120, "R237": 200}[source_candidate_id], 0)
    if source_candidate_id in ("R238", "R239", "R240", "R241"):
        return coverage10.build_qcom_exclusion_coverage10_projection(package,
            {"R238": "ar_off", "R239": "ar_on80", "R240": "ar_on120",
             "R241": "ar_on200"}[source_candidate_id])
    if source_candidate_id in ("R242", "R243", "R244", "R245"):
        return three_name.build_qcom_exclusion_three_name_projection(package,
            {"R242": "ar_off", "R243": "ar_on80", "R244": "ar_on120",
             "R245": "ar_on200"}[source_candidate_id])
    if source_candidate_id == "R246":
        return entry_only.build_qcom_entry_only_projection(package)
    _fail("QCOM-restored source candidate is not in the frozen study")


def build_qcom_admitted_projection(package, source_candidate_id, new_candidate_id):
    """Build a non-executable, separately identified 17-file source closure.

    No R-number is assigned here: the caller must prospectively bind a fresh
    candidate ID and freeze the resulting source/profile hashes before launch.
    """
    if (type(source_candidate_id) is not str or source_candidate_id not in PREDECESSOR_SHA256
            or type(new_candidate_id) is not str or not _CANDIDATE_ID.fullmatch(new_candidate_id)
            or int(new_candidate_id[1:]) <= 247
            or new_candidate_id in PREDECESSOR_SHA256):
        _fail("QCOM-restored source and new candidate identities are invalid")
    predecessor, old_profile = _predecessor(package, source_candidate_id)
    if predecessor.projection_sha256 != PREDECESSOR_SHA256[source_candidate_id]:
        _fail("QCOM-restored frozen predecessor projection changed")
    security_id = matched._authenticated_qcom_security_id(package)
    sources = {item.project_path: render_qcom_admitted_source(
        item.project_path, item.source_bytes.decode("ascii"), security_id=security_id,
        new_candidate_id=new_candidate_id) for item in predecessor.source_files}
    with relaxed._cloud_loader(sources) as (load, _):
        bridge = load(relaxed._BRIDGE_NAME)
        baseline = bridge.require_bridge_profile("matched")
        old_hash = old_profile["matched_baseline_profile_sha256"]
        sources[_TILT] = relaxed._replace(sources[_TILT], old_hash, baseline["profile_sha256"])
        gate = load(_GATE[:-3])
        if (hasattr(gate, "EXCLUDED_QCOM_SECURITY_ID")
                or gate.RELAXED_COVERAGE_POLICY != (
                    three_name.COVERAGE_POLICY if source_candidate_id in (
                        "R242", "R243", "R244", "R245") else
                    coverage10.COVERAGE_POLICY if source_candidate_id in (
                        "R238", "R239", "R240", "R241") else
                    relaxed._selection.ALL25_COVERAGE_POLICY)):
            _fail("QCOM-restored gate exclusion or coverage policy changed")
        runtime = load(_TILT[:-3])
        profile = runtime.require_tilt_profile()
        runtime.expected_tilt_custom_statistic_names()
        if (profile.get("matched_baseline_profile_sha256") != baseline["profile_sha256"]
                or profile.get("target_gross_exposure") != old_profile["target_gross_exposure"]
                or profile.get("modeled_fee_bps_per_side") != old_profile["modeled_fee_bps_per_side"]
                or profile.get("slippage_bps") != old_profile["slippage_bps"]
                or profile.get("admission_leverage") != old_profile["admission_leverage"]
                or profile.get("maximum_stock_weight_change_fraction")
                    != old_profile["maximum_stock_weight_change_fraction"]
                or "stock_exclusion_policy_id" in profile
                or "excluded_logical_security_sha256" in profile):
            _fail("QCOM-restored profile changed another economic rule")
        for key in ("coverage_policy_id", "comparison_arm"):
            if key in old_profile and profile.get(key) != old_profile[key]:
                _fail("QCOM-restored coverage or comparison arm changed")
    files = tuple(sorted((base._source_file(path, source.encode("ascii"))
                          for path, source in sources.items()), key=lambda item: item.project_path))
    total = sum(item.byte_count for item in files)
    if (len(files) != 17 or len({item.project_path for item in files}) != 17
            or any(item.byte_count > base.MAXIMUM_QC_SOURCE_CHARACTERS for item in files)
            or total + base.MINIMUM_REVIEW_MARGIN_BYTES > base.MAXIMUM_TOTAL_SOURCE_BYTES):
        _fail("QCOM-restored source closure exceeded unchanged QC budgets")
    for item in files:
        base._audit_source(item.project_path, item.source_bytes)
    value = dataclasses.replace(predecessor,
        schema=f"arv2-six-qcom-admitted-{new_candidate_id.lower()}-projection-v1",
        role=profile["role"], variant=predecessor.variant.replace(
            "qcom_excluded", f"qcom_admitted_{new_candidate_id.lower()}"),
        profile_id=profile["profile_id"], profile_sha256=profile["profile_sha256"],
        source_files=files, total_source_byte_count=total)
    semantic = {key: item for key, item in value.to_record().items()
                if key not in ("projection_id", "projection_sha256")}
    digest = hashlib.sha256(base._canonical(semantic)).hexdigest()
    return dataclasses.replace(value, projection_sha256=digest,
        projection_id=f"arv2-six-qcom-admitted-{new_candidate_id.lower()}-projection-" + digest[:24]), json.loads(
            base._canonical(profile))
