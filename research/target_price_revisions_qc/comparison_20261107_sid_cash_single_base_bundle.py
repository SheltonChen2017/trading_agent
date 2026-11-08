"""Fixed static single-base successor of the retained SID-CASH v1 renderer.

Only public supplied source bytes and a separately claimed project registry
are processed. This source-load correction changes class declarations, import
placement and source/config identities. It changes no v1 economics or inputs.
There is no I/O, private opener, class/function transplantation, runtime code
construction, native effect, attempt claim or authority.
"""
from __future__ import annotations

import ast
import hashlib
import json

from . import comparison_20261107_sid_cash_bundle as predecessor

PREFIX = predecessor.PREFIX
MODULE = PREFIX + "comparison_20261107_sid_cash_single_base_bundle.py"
PREDECESSOR_MODULE = PREFIX + "comparison_20261107_sid_cash_bundle.py"
PREDECESSOR_SHA256 = "ae9455e7371cb4b24c8b5dfe218c28c437441e425e5d44f94eb716159f47ad39"
SOURCE_EPOCH = "TPR-SID-CASH-SINGLE-BASE-20261107-v2"
STUDY_ID = predecessor.STUDY_ID
PARENT_STUDY_ID = predecessor.PARENT_STUDY_ID
PARENT_SOURCE_EPOCH = predecessor.SOURCE_EPOCH
PREFLIGHT_MODULE = predecessor.PREFLIGHT_MODULE
RUNTIME_PATH = predecessor.RUNTIME_PATH
RUNTIME_SHA256 = predecessor.RUNTIME_SHA256
EXCLUDED_SID_SHA256 = predecessor.EXCLUDED_SID_SHA256
OWNER_INSTRUCTION = predecessor.OWNER_INSTRUCTION
OWNER_SHA256 = predecessor.OWNER_SHA256
REGISTRY_CREATION_OWNER_SHA256 = predecessor.REGISTRY_CREATION_OWNER_SHA256
ARMS = predecessor.ARMS
CANDIDATES = dict(predecessor.CANDIDATES)
MAX_SOURCE_BYTES = predecessor.MAX_SOURCE_BYTES
MAX_TOTAL_SOURCE_BYTES = predecessor.MAX_TOTAL_SOURCE_BYTES
MAX_CLOUD_FILE_BYTES = predecessor.MAX_CLOUD_FILE_BYTES
PINS = {**predecessor.PINS, PREDECESSOR_MODULE: PREDECESSOR_SHA256}
REQUIRED_SOURCES = frozenset(PINS)

# Explicit compatibility bindings used by the fixed action/result composition.
# No module-wide attribute forwarding or caller-selected renderer exists.
bundle = predecessor.bundle
preflight = predecessor.preflight
_wire = predecessor._wire
_sha = predecessor._sha
_packet = predecessor._packet
_policy_metadata = predecessor._policy_metadata


class CashBundleRefusal(ValueError):
    """Body-free refusal of a changed predecessor or static source shape."""


def _fail():
    raise CashBundleRefusal("fixed SID-CASH single-base render refused") from None


def _sources(public_sources):
    if type(public_sources) is not dict or set(public_sources) != REQUIRED_SOURCES:
        _fail()
    total = 0
    for path, expected in PINS.items():
        raw = public_sources[path]
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_SOURCE_BYTES or _sha(raw) != expected:
            _fail()
        total += len(raw)
    if total > MAX_TOTAL_SOURCE_BYTES:
        _fail()


def _classes(tree):
    return {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}


def _dump(nodes):
    # Equality is checked within this one interpreter; no cross-version
    # ast.dump value is persisted as a content identity.
    return tuple(ast.dump(node, include_attributes=False) for node in nodes)


def _candidate_import(node, module):
    return (isinstance(node, ast.Import) and len(node.names) == 1
        and node.names[0].name == module and node.names[0].asname == "candidate")


def _single_base_main(raw, *, arm):
    """Rewrite fixed headers/placement only; preserve every function body."""
    module = "comparison_20261028_algorithm" if arm == "cap_off" else "comparison_20261028_multi_algorithm"
    algorithm = "ComparisonOffAlgorithm" if arm == "cap_off" else "ComparisonMultiAlgorithm"
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_CLOUD_FILE_BYTES:
        _fail()
    text = raw.decode("utf-8")
    old_tree = ast.parse(text)
    old = _classes(old_tree)
    if (set(old) != {"ResourceRecoveryRefusal", "ResourceRecoveryMixin", "CashExclusionRefusal",
            "CashExclusionMixin", "Main"}
            or old["ResourceRecoveryMixin"].bases or old["CashExclusionMixin"].bases
            or any(old[name].keywords or old[name].decorator_list for name in
                ("ResourceRecoveryMixin", "CashExclusionMixin", "Main"))
            or _dump(old["Main"].bases) != _dump(ast.parse(
                "class Main(CashExclusionMixin, ResourceRecoveryMixin, candidate." + algorithm + "):\n    pass\n").body[0].bases)
            or len(old["Main"].body) != 1 or not isinstance(old["Main"].body[0], ast.Pass)):
        _fail()
    imports = [node for node in old_tree.body if _candidate_import(node, module)]
    if len(imports) != 1:
        _fail()
    suffix = ("\nimport " + module + " as candidate\n\n"
        "class Main(CashExclusionMixin, ResourceRecoveryMixin, candidate." + algorithm + "):\n    pass\n")
    resource_header = "class ResourceRecoveryMixin:"
    cash_header = "class CashExclusionMixin:"
    if (not text.endswith(suffix) or text.count(resource_header) != 1 or text.count(cash_header) != 1):
        _fail()
    result = text[:-len(suffix)]
    result = result.replace(resource_header,
        "import " + module + " as candidate\n\n"
        "class _ResourceRecoveryLayer(candidate." + algorithm + "):", 1)
    result = result.replace(cash_header, "class Main(_ResourceRecoveryLayer):", 1)
    result += "\ndel _ResourceRecoveryLayer\n"
    new_tree = ast.parse(result)
    new = _classes(new_tree)
    if (set(new) != {"ResourceRecoveryRefusal", "_ResourceRecoveryLayer", "CashExclusionRefusal", "Main"}
            or len(new["_ResourceRecoveryLayer"].bases) != 1 or len(new["Main"].bases) != 1
            or _dump(new["_ResourceRecoveryLayer"].bases) != _dump(ast.parse(
                "class _ResourceRecoveryLayer(candidate." + algorithm + "):\n    pass\n").body[0].bases)
            or _dump(new["Main"].bases) != _dump(ast.parse(
                "class Main(_ResourceRecoveryLayer):\n    pass\n").body[0].bases)):
        _fail()
    for before, after in (("ResourceRecoveryMixin", "_ResourceRecoveryLayer"), ("CashExclusionMixin", "Main")):
        if _dump(old[before].body) != _dump(new[after].body):
            _fail()
        old_methods = [ast.get_source_segment(text, node) for node in old[before].body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        new_methods = [ast.get_source_segment(result, node) for node in new[after].body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        if old_methods != new_methods:
            _fail()
    old_other = [node for node in old_tree.body if not _candidate_import(node, module)
        and not (isinstance(node, ast.ClassDef) and node.name in ("ResourceRecoveryMixin", "CashExclusionMixin", "Main"))]
    deleted = [node for node in new_tree.body if isinstance(node, ast.Delete)]
    if (len(deleted) != 1 or _dump(deleted[0].targets) != _dump([ast.Name(id="_ResourceRecoveryLayer", ctx=ast.Del())])
            or new_tree.body[-1] is not deleted[0]):
        _fail()
    new_other = [node for node in new_tree.body if not _candidate_import(node, module)
        and not isinstance(node, ast.Delete)
        and not (isinstance(node, ast.ClassDef) and node.name in ("_ResourceRecoveryLayer", "Main"))]
    if _dump(old_other) != _dump(new_other):
        _fail()
    position = new_tree.body.index(new["_ResourceRecoveryLayer"])
    if (position < 1 or not _candidate_import(new_tree.body[position - 1], module)
            or sum(_candidate_import(node, module) for node in new_tree.body) != 1):
        _fail()
    encoded = result.encode("utf-8")
    if not 0 < len(encoded) <= MAX_CLOUD_FILE_BYTES:
        _fail()
    return encoded, {
        "candidate_module": module, "candidate_class": algorithm,
        "source_class_chain": ["Main", "_ResourceRecoveryLayer", "candidate." + algorithm],
        "candidate_import_immediately_before_resource_class": True,
        "temporary_resource_class_alias_deleted": True,
        "all_methods_and_global_helpers_preserved": True,
        "all_other_top_level_statements_preserved": True}


def build_cash_candidate(*, public_sources, project_bindings_raw,
        expected_project_bindings_sha256, arm, operation_id, attempt,
        prior_attempts_looks_sha256, latest_owner_instruction_sha256):
    """Render only the fixed v2 source-load correction of a v1 candidate.

    Candidate/study economics and attempt metadata retain their old meanings.
    A same-study subsequent attempt must preserve earlier receipts/history;
    this pure metadata renderer never consumes or resets any attempt.
    """
    try:
        _sources(public_sources)
        files, predecessor_report_raw = predecessor.build_cash_candidate(
            public_sources={name: public_sources[name] for name in predecessor.REQUIRED_SOURCES},
            project_bindings_raw=project_bindings_raw,
            expected_project_bindings_sha256=expected_project_bindings_sha256,
            arm=arm, operation_id=operation_id, attempt=attempt,
            prior_attempts_looks_sha256=prior_attempts_looks_sha256,
            latest_owner_instruction_sha256=latest_owner_instruction_sha256)
        old_files = dict(files)
        old_report = json.loads(predecessor_report_raw)
        config = preflight._config(files["comparison_20261028_config.py"])
        old_config_sha = old_report["config_sha256"]
        source_hashes = {name: _sha(raw) for name, raw in sorted(public_sources.items())}
        closure = _sha(_wire({"schema": "tpr-cmp1107-sid-cash-single-base-template-closure-v2",
            "source_epoch": SOURCE_EPOCH, "study_id": STUDY_ID,
            "cloud_layout": "fixed-inline-single-base-main-v2",
            "predecessor_source_epoch": predecessor.SOURCE_EPOCH,
            "predecessor_builder_sha256": PREDECESSOR_SHA256,
            "static_class_shape": "Main -> _ResourceRecoveryLayer -> fixed candidate; delete temporary alias",
            "source_hashes": source_hashes, "excluded_sid_sha256": EXCLUDED_SID_SHA256}))
        files["main.py"], shape = _single_base_main(files["main.py"], arm=arm)
        config["source_template_closure_sha256"] = closure
        config_raw = _wire(config)
        config_sha = _sha(config_raw)
        files["comparison_20261028_config.py"] = ("CONFIG_JSON = " + repr(config_raw.decode("ascii")) + "\n").encode("ascii")
        driver = shape["candidate_module"] + ".py"
        files[driver] = bundle._assignment(files[driver], "EXPECTED_CONFIG_SHA256", repr(old_config_sha), repr(config_sha))
        changed = {name for name in files if files[name] != old_files[name]}
        if changed != {"main.py", driver, "comparison_20261028_config.py"}:
            _fail()
        for name in old_files:
            if name not in changed and files[name] != old_files[name]:
                _fail()
        if (config["study_id"] != STUDY_ID or config["policy_sha256"] != old_report["policy_sha256"]
                or config["calendar_sha256"] != old_report["calendar_sha256"]
                or config["attempt"] != attempt or config["prior_attempts_looks_sha256"] != prior_attempts_looks_sha256):
            _fail()
        predecessor._checked_cloud(files)
        hashes = {name: _sha(raw) for name, raw in sorted(files.items())}
        report = {**old_report,
            "schema": "tpr-cmp1107-sid-cash-single-base-project-bundle-v2",
            "source_epoch": SOURCE_EPOCH, "cloud_layout": "fixed-inline-single-base-main-v2",
            "predecessor_source_epoch": predecessor.SOURCE_EPOCH,
            "predecessor_builder_source_sha256": PREDECESSOR_SHA256,
            "predecessor_same_lineage_render_report_sha256": _sha(predecessor_report_raw),
            "predecessor_rendered_source_closure_sha256": old_report["rendered_source_closure_sha256"],
            "predecessor_config_sha256": old_config_sha,
            "predecessor_source_template_closure_sha256": old_report["source_template_closure_sha256"],
            "config_sha256": config_sha, "source_template_closure_sha256": closure,
            "template_source_hashes": source_hashes, "cloud_source_hashes": hashes,
            "cloud_source_bytes": {name: len(raw) for name, raw in sorted(files.items())},
            "rendered_source_closure_sha256": _sha(_wire(hashes)), "file_count": len(files),
            "main_class": "Main(_ResourceRecoveryLayer)", "single_base_class_shape": shape,
            "changed_from_v1_files": sorted(changed), "new_policy_or_calendar": False,
            "additional_strategy_economics_changed_vs_v1": False,
            "v1_financial_function_bodies_unchanged": True,
            "v1_cash_mask_and_native_census_bodies_unchanged": True,
            "v1_global_helpers_and_cooperative_super_order_preserved": True,
            "class_functions_transplanted": False, "runtime_code_construction": False,
            "managed_multiple_base_declaration_removed": True,
            "native_single_base_compatibility_verified": False,
            "source_load_correction_only": True,
            "earlier_attempts_preserved_not_reset": True,
            "native_accounting_accepted": False, "native_origin_authenticated": False,
            "strategy_accepted": False, "backtesting_ready": False,
            "financial_metrics": None, "accepted_performance": None,
            "qc_requests": 0, "qc_compiles": 0, "backtests_launched": 0,
            "new_attempts": 0, "new_observed_looks": 0, "reservation_sha256": None}
        return files, _wire(report) + b"\n"
    except CashBundleRefusal:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError,
            SyntaxError, OverflowError, RecursionError):
        _fail()
