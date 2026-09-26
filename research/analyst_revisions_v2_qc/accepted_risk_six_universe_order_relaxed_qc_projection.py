"""Versioned, order-based relaxed selection from the exact recent closure.

Each prospective threshold tuple and tilt strength has its own profile/source
identity. Historical gates, input authority and cloud files stay untouched.
"""

import ast
import builtins
from contextlib import contextmanager
import dataclasses
import hashlib
import json
import sys
import types

from . import accepted_risk_six_universe_order_qc_projection as _base
from . import accepted_risk_six_universe_order_tilt_recent_qc_projection as _recent
from . import six_universe_relaxed_selection_source as _selection


class RelaxedOrderProjectionError(ValueError):
    """A source, policy, closure or profile binding is inconsistent."""


TILT_PERCENTS = tuple(range(20, 201, 20))
SUMMARY_SCHEMAS = {percent: f"arv2-six-universe-order-tilt{percent}-recent-summary-v1-relaxed-v1"
                   for percent in TILT_PERCENTS}
META_SCHEMA = "arv2-six-universe-order-runtime-meta-v1-relaxed-v1"
ALL25_SUMMARY_SCHEMA = "arv2-six-universe-order-tilt100-recent-summary-v1-all25-v1"
ALL25_META_SCHEMA = "arv2-six-universe-order-runtime-meta-v1-all25-v1"
_GATE_PATH = "accepted_risk_six_universe_gate.py"
_TARGET_PATH = "accepted_risk_six_universe_order_targets.py"
_TILT_TARGET_PATH = "accepted_risk_six_universe_order_tilt_targets.py"
_TILT_RUNTIME_PATH = "accepted_risk_six_universe_order_tilt_qc_runtime.py"
_BRIDGE_NAME = "accepted_risk_six_universe_order_bridge_qc_runtime"
_VERSIONED_PATHS = frozenset((
    _GATE_PATH, _TARGET_PATH, _TILT_TARGET_PATH, _TILT_RUNTIME_PATH,
    _BRIDGE_NAME + ".py", "accepted_risk_six_universe_order_qc_runtime.py",
    "accepted_risk_six_universe_gate_evaluator.py", "main.py",
))


def _replace(source, old, new, count=1):
    if source.count(old) != count:
        raise RelaxedOrderProjectionError("relaxed projection exact source anchor changed")
    return source.replace(old, new, count)


def _render_source(path, source, percent, policy, *, all25=False):
    if path == _GATE_PATH:
        source = (_selection.render_all25_gate_source(source, policy) if all25
                  else _selection.render_gate_source(source, policy))
    elif path == _TARGET_PATH:
        source = (_selection.render_all25_targets_source(source) if all25
                  else _selection.render_targets_source(source))
    fraction = f"{percent // 100}.{percent % 100:02d}"
    if path in (_TILT_TARGET_PATH, _TILT_RUNTIME_PATH):
        source = _replace(source, '"1.00"', repr(fraction), 2)
    if path not in _VERSIONED_PATHS:
        return source
    successor = "all25" if all25 else "relaxed"
    replacements = {
        "matched_revision_tilt100_recent": f"matched_revision_tilt{percent}_{successor}_recent",
        "cap90_matched_revision_tilt100_recent_v1": f"cap90_matched_revision_tilt{percent}_{successor}_recent_v1",
        "cap90_exploratory_v3": f"cap90_{successor}_recent_v1",
        "cap90_admission_settlement_v1": f"cap90_admission_{successor}_recent_v1",
    }

    class Version(ast.NodeTransformer):
        def visit_Constant(self, node):
            if type(node.value) is str:
                value = node.value
                if value in replacements:
                    node.value = replacements[value]
                elif value.startswith("arv2-six-universe-"):
                    if ("relaxed-selection" not in value and "order-relaxed-sleeve" not in value
                            and "all25-selection" not in value and "order-all25-sleeve" not in value
                            and value != "arv2-six-universe-order-sleeve-summary-table-v1"):
                        value = value.replace("tilt100", f"tilt{percent}")
                        node.value = (value + successor + "-") if value.endswith("-") else value + f"-{successor}-v1"
            return node

        def visit_ClassDef(self, node):
            if path == "main.py" and node.name == "ARV2SixUniverseOrderTilt100RecentAlgorithm":
                title = "All25" if all25 else "Relaxed"
                node.name = f"ARV2SixUniverseOrderTilt{percent}{title}RecentAlgorithm"
            return self.generic_visit(node)

    tree = Version().visit(ast.parse(source))
    ast.fix_missing_locations(tree)
    rendered = ast.unparse(tree) + "\n"
    if ast.dump(tree, include_attributes=False) != ast.dump(ast.parse(rendered), include_attributes=False):
        raise RelaxedOrderProjectionError("relaxed projection formatting changed executable AST")
    return rendered


@contextmanager
def _cloud_loader(sources):
    """Load only projected dependencies; restore every host module afterwards."""
    names = {path[:-3] for path in sources if path != "main.py"}
    missing = object()
    saved = {name: sys.modules.get(name, missing) for name in names}
    modules = {name: types.ModuleType(name) for name in names}
    completed, visiting = set(), set()
    original_import = builtins.__import__

    def cloud_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "research" or name.startswith("research."):
            raise RelaxedOrderProjectionError("relaxed cloud closure attempted host fallback")
        if name.startswith("accepted_risk_") and name not in names:
            raise RelaxedOrderProjectionError("relaxed cloud closure attempted host fallback")
        return original_import(name, globals, locals, fromlist, level)

    def load(name):
        if name in completed:
            return modules[name]
        if name not in names or name in visiting:
            raise RelaxedOrderProjectionError("relaxed cloud dependency is missing or cyclic")
        visiting.add(name)
        source = sources[name + ".py"]
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in names:
                        load(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module in names:
                load(node.module)
        exec(compile(source, name + ".py", "exec"), modules[name].__dict__)
        visiting.remove(name)
        completed.add(name)
        return modules[name]

    try:
        for name, module in modules.items():
            sys.modules[name] = module
            module.__dict__["__builtins__"] = {**vars(builtins), "__import__": cloud_import}
        yield load, modules
    finally:
        for name, value in saved.items():
            if value is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


def build_relaxed_order_projection(prior_package, latest_package, percent, policy):
    """Return ``(projection, profile)`` for one prospective canonical policy."""
    if type(percent) is not int or percent not in TILT_PERCENTS:
        raise RelaxedOrderProjectionError("relaxed tilt percent must be 20 through 200 in steps of 20")
    return _build_projection(prior_package, latest_package, percent, policy)


def build_weight_ablation_projection(prior_package, latest_package, percent, policy):
    """A separate 0/100 pair; zero removes weight transfers, NOT AR entry gates.

    The historical ladder and its frozen manifest remain unchanged. The 100%
    arm reproduces the exact successful R214 source; the zero arm retains the
    identical gate/bridge/baseline, input package, exposure and order economics.
    """
    if type(percent) is not int or percent not in (0, 100):
        raise RelaxedOrderProjectionError("weight ablation requires exactly zero or 100 percent")
    return _build_projection(prior_package, latest_package, percent, policy)


def build_all25_order_projection(prior_package, latest_package, percent=100):
    """Separate all-six 25%-coverage/100%-tilt candidate, not the old ladder.

    Only coverage admission changes; AR entry outside XLE and all order/cash/
    exposure constraints stay intact. Unknown members are never invented.
    """
    if type(percent) is not int or percent != 100:
        raise RelaxedOrderProjectionError("all25 projection requires exactly 100 percent tilt")
    return _build_projection(prior_package, latest_package, percent,
                             _selection.ALL25_COVERAGE_POLICY, all25=True)


def _build_projection(prior_package, latest_package, percent, policy, *, all25=False):
    if not all25:
        policy = _selection._policy(policy)
    predecessor = _recent.build_corrected_short_window_tilt_projection(prior_package, latest_package, 100)
    sources = {item.project_path: _render_source(item.project_path,
        item.source_bytes.decode("ascii"), percent, policy, all25=all25) for item in predecessor.source_files}
    # The bridge hash includes the changed gate and evaluator. Rebind it before
    # loading the tilt runtime, which verifies that literal at profile reads.
    with _cloud_loader(sources) as (load, _modules):
        bridge = load(_BRIDGE_NAME)
        matched = bridge.require_bridge_profile("matched")
        sources[_TILT_RUNTIME_PATH] = _replace(sources[_TILT_RUNTIME_PATH],
            _recent.MATCHED_BASELINE_PROFILE_SHA256, matched["profile_sha256"])
        runtime = load(_TILT_RUNTIME_PATH[:-3])
        profile = runtime.require_tilt_profile()
        runtime.expected_tilt_custom_statistic_names()
        summary_schema = (ALL25_SUMMARY_SCHEMA if all25
                          else f"arv2-six-universe-order-tilt{percent}-recent-summary-v1-relaxed-v1")
        meta_schema = ALL25_META_SCHEMA if all25 else META_SCHEMA
        if runtime.TILT_SUMMARY_SCHEMA != summary_schema or runtime.TILT_META_SCHEMA != meta_schema:
            raise RelaxedOrderProjectionError("relaxed result schema binding changed")
    files = tuple(sorted((_base._source_file(path, source.encode("ascii"))
        for path, source in sources.items()), key=lambda item: item.project_path))
    total = sum(item.byte_count for item in files)
    if (len(files) != 16 or len({item.project_path for item in files}) != 16
            or any(item.byte_count > _base.MAXIMUM_QC_SOURCE_CHARACTERS for item in files)
            or total + _base.MINIMUM_REVIEW_MARGIN_BYTES > _base.MAXIMUM_TOTAL_SOURCE_BYTES):
        raise RelaxedOrderProjectionError("relaxed source closure exceeded unchanged QC budgets")
    for item in files:
        compile("from AlgorithmImports import *\n" + item.source_bytes.decode("ascii"), item.project_path, "exec")
    successor = "all25" if all25 else "relaxed"
    value = dataclasses.replace(predecessor,
        schema=f"arv2-six-universe-{successor}-tilt{percent}-qc-projection-v1",
        role=profile["role"], variant=f"cap90_matched_revision_tilt{percent}_{successor}_recent_v1",
        profile_id=profile["profile_id"], profile_sha256=profile["profile_sha256"],
        source_files=files, total_source_byte_count=total)
    semantic = {key: item for key, item in value.to_record().items()
                if key not in ("projection_id", "projection_sha256")}
    digest = hashlib.sha256(_base._canonical(semantic)).hexdigest()
    return dataclasses.replace(value, projection_sha256=digest,
        projection_id=f"arv2-six-universe-{successor}-tilt{percent}-qc-projection-" + digest[:24]), json.loads(_base._canonical(profile).decode("ascii"))
