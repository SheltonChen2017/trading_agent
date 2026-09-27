"""Same-source historical AR ablation and an actual six-ETF order control.

Only prospective rendered sources change. Frozen historical/recent builders,
inputs and cloud artifacts remain untouched; there is no network/outcome access.
"""

import ast
import dataclasses
import hashlib
import json
from pathlib import Path

from . import accepted_risk_six_universe_order_qc_projection as _base
from . import accepted_risk_six_universe_order_relaxed_qc_projection as _relaxed
from . import accepted_risk_six_universe_order_settlement_qc_projection as _settlement
from . import accepted_risk_six_universe_order_tilt_ladder_floor_qc_projection as _historical
from . import accepted_risk_six_universe_order_tilt_recent_qc_projection as _recent
from . import six_universe_relaxed_selection_source as _selection


class MatchedHistoricalProjectionError(ValueError):
    """A prospective arm, source anchor or closure changed."""


ARMS = ("ar_off", "ar_on100", "six_etf_basket")
SLIPPAGE_BPS = (0, 5)
DIAGNOSTICS_PATH = "accepted_risk_matched_diagnostics.py"
META_SCHEMA = "arv2-six-matched-historical-meta-v1"
SUMMARY_SCHEMA = "arv2-six-matched-historical-summary-v1"


def _error(message):
    raise MatchedHistoricalProjectionError(message)


def _named_function(tree, name):
    matches = [node for node in ast.walk(tree)
               if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(matches) != 1:
        _error("matched historical exact function anchor changed")
    return matches[0]


def _render_basket(path, source):
    """Reuse existing basket allocation/diagnostics, not an off-label stock arm."""
    tree = ast.parse(source)
    if path == _relaxed._TARGET_PATH:
        for name in ("_role_weights", "_sleeve_diagnostic"):
            node = _named_function(tree, name)
            node.body[:0] = ast.parse("if role == ROLE_MATCHED:\n    role = ROLE_SIX_ETF_BASKET\n").body
    elif path == _relaxed._TILT_TARGET_PATH:
        function = _named_function(tree, "tilt_matched_weights")
        returns = [node for node in ast.walk(function) if isinstance(node, ast.Return)]
        if (len(returns) != 1 or ast.unparse(returns[0].value) != "construction.matched_weights"):
            _error("matched historical AR-off basket return anchor changed")
        returns[0].value.attr = "etf_basket_weights"
        anchor = "tuple((sleeve.matched_security_ids for sleeve in construction.sleeves))"
        matches = [node for node in ast.walk(tree)
                   if isinstance(node, ast.Call) and ast.unparse(node) == anchor]
        if len(matches) != 1:
            _error("matched historical basket selected-ID check anchor changed")
        matches[0].args[0].elt = ast.Tuple([], ast.Load())
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def _render_identity(path, source, arm, slippage_bps):
    """Bind profile disclosure and LEAN execution to the same frozen cost arm."""
    suffix = f"{arm}-s{slippage_bps}"
    role = f"matched_historical_{arm}_s{slippage_bps}"
    variant = f"cap90_matched_historical_{arm}_s{slippage_bps}_v1"
    replacements = {
        _historical.TILT_ROLES[100]: role,
        _historical.TILT_VARIANTS[100]: variant,
    }
    counters = {"profile_slippage": 0, "main_slippage": 0, "profile_arm": 0}

    class Identity(ast.NodeTransformer):
        def visit_Constant(self, node):
            if type(node.value) is str:
                if node.value in replacements:
                    node.value = replacements[node.value]
                elif node.value.startswith("arv2-six-universe-") and node.value != "arv2-six-universe-order-sleeve-summary-table-v1":
                    node.value += f"-matched-{suffix}-v1"
            return node

        def visit_Assign(self, node):
            self.generic_visit(node)
            names = [item.id for item in node.targets if isinstance(item, ast.Name)]
            if path == _relaxed._TILT_RUNTIME_PATH and "TILT_META_SCHEMA" in names:
                node.value = ast.Constant(META_SCHEMA)
            if path == _relaxed._TILT_RUNTIME_PATH and "TILT_SUMMARY_SCHEMA" in names:
                node.value = ast.Constant(SUMMARY_SCHEMA)
            if path == "accepted_risk_six_universe_order_qc_runtime.py" and "META_SCHEMA" in names:
                node.value = ast.Constant(META_SCHEMA)
            if path == _relaxed._TILT_TARGET_PATH and "TILT_RANK_RULE_ID" in names and arm == "six_etf_basket":
                node.value = ast.Constant("disabled_six_ETF_budget_basket_v1")
            return node

        def visit_Dict(self, node):
            self.generic_visit(node)
            keys = [key.value if isinstance(key, ast.Constant) else None for key in node.keys]
            if path == "accepted_risk_six_universe_order_qc_runtime.py" and "slippage_bps" in keys:
                node.values[keys.index("slippage_bps")] = ast.Constant(str(slippage_bps))
                counters["profile_slippage"] += 1
            if path == _relaxed._TILT_RUNTIME_PATH and "maximum_stock_weight_change_fraction" in keys:
                node.keys += [ast.Constant("comparison_arm"), ast.Constant("analyst_revision_economic_usage")]
                node.values += [ast.Constant(arm), ast.Constant(
                    "entry_count_and_weight" if arm == "ar_on100" else "none_authenticated_score_clock_only")]
                counters["profile_arm"] += 1
            return node

        def visit_keyword(self, node):
            self.generic_visit(node)
            if path == "main.py" and node.arg == "slippage_model_factory":
                node.value = ast.parse("lambda: NullSlippageModel()" if slippage_bps == 0
                                       else "lambda: ConstantSlippageModel(0.0005)", mode="eval").body
                counters["main_slippage"] += 1
            return node

        def visit_ClassDef(self, node):
            self.generic_visit(node)
            if path == "main.py" and node.name == "ARV2SixUniverseOrderTilt100GuardAlgorithm":
                node.name = f"ARV2MatchedHistorical{arm.title().replace('_', '')}S{slippage_bps}Algorithm"
            return node

    tree = Identity().visit(ast.parse(source))
    expected = {"profile_slippage": int(path == "accepted_risk_six_universe_order_qc_runtime.py"),
                "main_slippage": int(path == "main.py"),
                "profile_arm": 2 * int(path == _relaxed._TILT_RUNTIME_PATH)}
    # One dict specifies the profile and one emits the same fields in aggregates.
    if counters != expected:
        _error("matched historical profile or execution anchor changed")
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def _render_diagnostics(path, source, arm, slippage_bps):
    """Third bounded statistic is linked by META, not mixed into economics."""
    tree = ast.parse(source)
    if path == "main.py":
        tree.body.insert(1, ast.ImportFrom("accepted_risk_matched_diagnostics",
            [ast.alias("install_matched_diagnostics")], 0))
        method = _named_function(tree, "initialize")
        anchors = [index for index, node in enumerate(method.body)
                   if isinstance(node, ast.Expr) and ast.unparse(node) == "self._arv2_driver.initialize()"]
        if len(anchors) != 1:
            _error("matched historical diagnostics initialization anchor changed")
        method.body.insert(anchors[0] + 1,
            ast.parse(f"install_matched_diagnostics(self._arv2_driver, {arm!r}, {slippage_bps})").body[0])
    elif path == _relaxed._BRIDGE_NAME + ".py":
        tree.body.insert(1, ast.ImportFrom("accepted_risk_matched_diagnostics",
            [ast.alias("diagnostic_digest"), ast.alias("diagnostic_text")], 0))
        function = _named_function(tree, "expected_bridge_custom_statistic_names")
        arrays = [node for node in ast.walk(function) if isinstance(node, ast.Tuple)]
        if len(arrays) != 1 or len(arrays[0].elts) != 2:
            _error("matched historical statistic inventory anchor changed")
        arrays[0].elts.append(ast.Constant("ARV2_SIX_GATE_ORDER_DIAGNOSTICS"))
        end = _named_function(tree, "on_end_of_algorithm")
        anchors = {"meta": 0, "statistics": 0}
        for node in ast.walk(end):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            name = node.targets[0].id if isinstance(node.targets[0], ast.Name) else None
            if name == "meta" and isinstance(node.value, ast.Dict):
                keys = [key.value if isinstance(key, ast.Constant) else None for key in node.value.keys]
                if "result_transport" not in keys:
                    _error("matched historical META transport anchor changed")
                node.value.values[keys.index("result_transport")] = ast.Constant("three_bounded_custom_summary_statistics")
                node.value.keys.append(ast.Constant("matched_diagnostics_sha256"))
                node.value.values.append(ast.parse("diagnostic_digest(self)", mode="eval").body)
                anchors["meta"] += 1
            elif name == "statistics" and isinstance(node.value, ast.Dict):
                node.value.keys.append(ast.Constant("ARV2_SIX_GATE_ORDER_DIAGNOSTICS"))
                node.value.values.append(ast.parse("diagnostic_text(self)", mode="eval").body)
                anchors["statistics"] += 1
        if anchors != {"meta": 1, "statistics": 1}:
            _error("matched historical diagnostics transport anchor changed")
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def _render_reference_refusal(path, source):
    """Describe missing planning marks without changing or replacing them."""
    if path != "accepted_risk_six_universe_order_qc_runtime.py":
        return source
    tree = ast.parse(source)
    reference = _named_function(tree, "_reference_prices")
    close = _named_function(tree, "on_after_close")
    refusal = "six-universe RAW reference price census is incomplete; no stale-price fallback is permitted"
    branches = [node for node in reference.body if isinstance(node, ast.If)
                and ast.unparse(node.test) == "set(result) != set(security_ids)"]
    assignments = [node for node in reference.body if isinstance(node, ast.Assign)
                   and ast.unparse(node) == "sid_to_security = {}"]
    symbols = [node for node in ast.walk(reference) if isinstance(node, ast.Assign)
               and ast.unparse(node) == "sid_to_security[sid] = security_id"]
    loops = [node for node in reference.body if isinstance(node, ast.For)
             and any(item in symbols for item in node.body)]
    calls = [node for node in ast.walk(close) if isinstance(node, ast.Call)
             and ast.unparse(node) == "self._reference_prices(session, reference_ids)"]
    if (len(branches) != 1 or len(assignments) != 1 or len(symbols) != 1 or len(loops) != 1
            or len(calls) != 1 or [item.arg for item in reference.args.args]
            != ["self", "session", "security_ids"] or reference.args.kwonlyargs
            or len(branches[0].body) != 1
            or ast.unparse(branches[0].body[0]) != f"_error({refusal!r})"):
        _error("matched historical reference-refusal exact anchor changed")
    reference.args.kwonlyargs.extend((ast.arg("target_security_ids"), ast.arg("holding_quantities")))
    reference.args.kw_defaults.extend((None, None))
    calls[0].keywords.extend(ast.parse(
        "f(target_security_ids=tuple(sorted(target_weights)), holding_quantities=holdings)"
    ).body[0].value.keywords)
    reference.body.insert(reference.body.index(assignments[0]) + 1,
                          ast.parse("reference_securities = {}").body[0])
    # Reuse securities already resolved for the existing history request.
    loops[0].body.insert(loops[0].body.index(symbols[0]) + 1,
                        ast.parse("reference_securities[security_id] = _security").body[0])
    branches[0].body = ast.parse("""
if (type(target_security_ids) is not tuple
        or tuple(sorted(set(target_security_ids))) != target_security_ids
        or type(holding_quantities) is not dict
        or any(type(quantity) is not int or quantity <= 0 for quantity in holding_quantities.values())
        or set(target_security_ids) | set(holding_quantities) != set(security_ids)):
    _error("six-universe missing-reference diagnostic context changed")
missing = tuple(sorted(set(security_ids) - set(result)))
missing_hashes = [hashlib.sha256(item.encode("utf-8")).hexdigest() for item in missing]
entries = []
for security_id, security_hash in zip(missing[:32], missing_hashes[:32]):
    delisted = getattr(reference_securities[security_id], "is_delisted", None)
    entries.append({
        "security_id_sha256": security_hash,
        "role": ("target_and_held" if security_id in target_security_ids and security_id in holding_quantities
                 else "target_only" if security_id in target_security_ids else "held_only"),
        "holding_quantity": holding_quantities.get(security_id, 0),
        "is_delisted": delisted if type(delisted) is bool else None,
    })
context = _canonical({
    "session": session,
    "requested_count": len(security_ids),
    "received_count": len(result),
    "missing_count": len(missing),
    "missing": entries,
    "omitted_missing_count": max(0, len(missing) - 32),
    "missing_security_id_path_sha256": _sha(missing_hashes),
})
if len(context) > 8192:
    _error("six-universe missing-reference diagnostic exceeded bounded context")
_error("six-universe RAW reference price census is incomplete; no stale-price fallback is permitted; context="
       + context.decode("ascii"))
""").body
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def build_matched_historical_projection(package, arm, slippage_bps=0):
    """Return a launch-ready projection/profile, never launch or inspect returns.

    All arms use one exact historical package, all-six 25% coverage, 98% gross,
    weekly next-open orders and ten-bps fees. Slippage is an explicit 0/5-bps
    engine-price sensitivity; it is not a measured spread or impact estimate.
    """
    if type(arm) is not str or arm not in ARMS:
        _error("matched historical arm must be AR-off, AR-on100 or six-ETF")
    if type(slippage_bps) is not int or slippage_bps not in SLIPPAGE_BPS:
        _error("matched historical slippage must be exactly zero or five bps")
    predecessor = _historical.build_tilt_floor_projection(package, 100)
    sources = {}
    for item in predecessor.source_files:
        path, original = item.project_path, item.source_bytes.decode("ascii")
        source = _relaxed._render_source(path, original, 100 if arm == "ar_on100" else 0,
            _selection.ALL25_COVERAGE_POLICY, all25=True, ar_off=arm != "ar_on100")
        if arm == "six_etf_basket":
            source = _render_basket(path, source)
        if path == "accepted_risk_order_level_input_runtime.py":
            source = _recent._correct_input_reader(original)
        sources[path] = _render_reference_refusal(path,
            _render_diagnostics(path, _render_identity(path, source, arm, slippage_bps), arm, slippage_bps))
    sources[DIAGNOSTICS_PATH] = Path(__file__).with_name(DIAGNOSTICS_PATH).read_text(encoding="ascii")
    # Recompute every descendant authority from prospective source, never reuse
    # an old matched profile as the denominator of a changed construction.
    with _relaxed._cloud_loader(sources) as (load, _):
        baseline = load(_relaxed._BRIDGE_NAME).require_bridge_profile("matched")
        old = _settlement.CANDIDATES["R191"]["profile_sha256"]
        sources[_relaxed._TILT_RUNTIME_PATH] = _relaxed._replace(
            sources[_relaxed._TILT_RUNTIME_PATH], old, baseline["profile_sha256"])
        runtime = load(_relaxed._TILT_RUNTIME_PATH[:-3])
        profile = runtime.require_tilt_profile()
        runtime.expected_tilt_custom_statistic_names()
    files = tuple(sorted((_base._source_file(path, source.encode("ascii"))
                         for path, source in sources.items()), key=lambda item: item.project_path))
    total = sum(item.byte_count for item in files)
    if (len(files) != 17 or len({item.project_path for item in files}) != 17
            or any(item.byte_count > _base.MAXIMUM_QC_SOURCE_CHARACTERS for item in files)
            or total + _base.MINIMUM_REVIEW_MARGIN_BYTES > _base.MAXIMUM_TOTAL_SOURCE_BYTES):
        _error("matched historical source closure exceeded unchanged QC budgets")
    for item in files:
        _base._audit_source(item.project_path, item.source_bytes)
    value = dataclasses.replace(predecessor,
        schema="arv2-six-matched-historical-projection-v1", role=profile["role"],
        variant=f"cap90_matched_historical_{arm}_s{slippage_bps}_v1",
        profile_id=profile["profile_id"], profile_sha256=profile["profile_sha256"],
        source_files=files, total_source_byte_count=total)
    semantic = {key: item for key, item in value.to_record().items()
                if key not in ("projection_id", "projection_sha256")}
    digest = hashlib.sha256(_base._canonical(semantic)).hexdigest()
    return dataclasses.replace(value, projection_sha256=digest,
        projection_id="arv2-six-matched-historical-projection-" + digest[:24]), json.loads(_base._canonical(profile))
