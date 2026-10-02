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
from . import accepted_risk_delta_order_package as _delta
from . import six_universe_relaxed_selection_source as _selection


class MatchedHistoricalProjectionError(ValueError):
    """A prospective arm, source anchor or closure changed."""


ARMS = ("ar_off", "ar_on100", "six_etf_basket")
SLIPPAGE_BPS = (0, 5)
DIAGNOSTICS_PATH = "accepted_risk_matched_diagnostics.py"
META_SCHEMA = "arv2-six-matched-historical-meta-v1"
SUMMARY_SCHEMA = "arv2-six-matched-historical-summary-v1"
REFERENCE_PRICE_RULE = "raw_daily_history_or_exact_same_session_closing_minute_tradebar_v1"
ENGINE_FEE_BASIS = "raw_moo_open_plus_signed_installed_slippage_v1"
QCOM_EXCLUSION_POLICY_ID = "qcom_stock_eligibility_after_coverage_v1"
QCOM_EXCLUSION_SECURITY_ID_SHA256 = "12e2fb85270ad4370a284866d825f3a6cf121a92c997c3557861e6d08a7a6a1f"
QCOM_EXCLUSION_META_SCHEMA = "arv2-six-matched-qcom-excluded-meta-v1"
QCOM_EXCLUSION_SUMMARY_SCHEMA = "arv2-six-matched-qcom-excluded-summary-v1"


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
                node.keys.append(ast.Constant("reference_price_rule"))
                node.values.append(ast.Constant(REFERENCE_PRICE_RULE))
                node.keys.append(ast.Constant("engine_fee_basis"))
                node.values.append(ast.Constant(ENGINE_FEE_BASIS))
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


def _render_fee_basis(path, source):
    """Preserve valuation estimates and match actual default full MOO fees."""
    if path != "main.py":
        return source
    tree = ast.parse(source)
    method = _named_function(tree, "get_order_fee")
    original = ast.parse("""
price = Decimal(str(parameters.security.open))
quantity = abs(Decimal(str(parameters.order.absolute_quantity)))
if not price.is_finite() or price <= 0 or not quantity.is_finite():
    raise RuntimeError("ARV2 fee input is invalid")
return OrderFee(CashAmount(price * quantity * MODELED_FEE_RATE_PER_SIDE, "USD"))
""").body
    if ([item.arg for item in method.args.args] != ["self", "parameters"]
            or [ast.dump(node, include_attributes=False) for node in method.body]
            != [ast.dump(node, include_attributes=False) for node in original]):
        _error("matched historical fee-basis exact anchor changed")
    method.body = ast.parse('''
"""MARKET callbacks are LEAN valuation estimates, not order authority.

The executor remains MOO-only. Preserve the original RAW-open estimate
without querying slippage for synthetic MARKET calls; actual MOO fees use
the signed installed slippage below.
"""
if parameters.order.type == OrderType.MARKET:
    estimate_price = Decimal(str(parameters.security.open))
    estimate_quantity = abs(Decimal(str(parameters.order.absolute_quantity)))
    if (not estimate_price.is_finite() or estimate_price <= 0
            or not estimate_quantity.is_finite() or estimate_quantity <= 0):
        raise RuntimeError("ARV2 fee input is invalid")
    return OrderFee(CashAmount(estimate_price * estimate_quantity * MODELED_FEE_RATE_PER_SIDE, "USD"))
price = Decimal(str(parameters.security.open))
quantity = abs(Decimal(str(parameters.order.absolute_quantity)))
signed_quantity = Decimal(str(parameters.order.quantity))
if (parameters.order.type != OrderType.MARKET_ON_OPEN
        or not price.is_finite() or price <= 0
        or not quantity.is_finite() or quantity <= 0
        or not signed_quantity.is_finite() or signed_quantity == 0
        or abs(signed_quantity) != quantity):
    raise RuntimeError("ARV2 fee input is invalid")
# Reuse the installed deterministic model: its MOO reference can differ
# across LEAN versions, so hardcoding open times five bps is not equivalent.
slippage = Decimal(str(parameters.security.slippage_model.get_slippage_approximation(
    parameters.security, parameters.order)))
if not slippage.is_finite() or slippage < 0:
    raise RuntimeError("ARV2 fee slippage input is invalid")
price += slippage if signed_quantity > 0 else -slippage
if not price.is_finite() or price <= 0:
    raise RuntimeError("ARV2 fee fill-price basis is invalid")
return OrderFee(CashAmount(price * quantity * MODELED_FEE_RATE_PER_SIDE, "USD"))
''').body
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
    """Admit only the exact RAW closing minute when daily history is absent."""
    if path != "accepted_risk_six_universe_order_qc_runtime.py":
        return source
    tree = ast.parse(source)
    reference = _named_function(tree, "_reference_prices")
    close = _named_function(tree, "on_after_close")
    initialize = _named_function(tree, "__init__")
    initializations = [node for node in initialize.body if isinstance(node, ast.Assign)
                       and ast.unparse(node) == "self._reference_history_call_count = 0"]
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and reference in node.body]
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
            or len(initializations) != 1 or len(classes) != 1
            or len(calls) != 1 or [item.arg for item in reference.args.args]
            != ["self", "session", "security_ids"] or reference.args.kwonlyargs
            or len(branches[0].body) != 1
            or ast.unparse(branches[0].body[0]) != f"_error({refusal!r})"):
        _error("matched historical reference-refusal exact anchor changed")
    index = initialize.body.index(initializations[0]) + 1
    initialize.body[index:index] = ast.parse("""
self._reference_closing_minute_repair_count = 0
self._reference_closing_minute_repair_sessions = set()
self._reference_closing_minute_repair_path = []
""").body
    classes[0].body.append(ast.parse("""
def _same_session_closing_minute_price(self, session, security, requested_sid):
    try:
        if requested_sid not in self._configured_sids:
            return None, "not_raw_configured"
        if _symbol_sid(security.symbol, "closing-minute reference security") != requested_sid:
            return None, "security_sid_mismatch"
        bar = security.get_last_data()
        if not isinstance(bar, self._trade_bar_type):
            return None, "not_trade_bar"
        if _symbol_sid(bar.symbol, "closing-minute reference bar") != requested_sid:
            return None, "bar_sid_mismatch"
        if bar.is_fill_forward is not False:
            return None, "fill_forward_or_unknown"
        actual_time = self._algorithm.time
        if (actual_time.date().isoformat() != session
                or bar.time.date().isoformat() != session
                or bar.end_time != actual_time
                or bar.time != actual_time - timedelta(minutes=1)):
            return None, "not_exact_same_session_closing_minute"
        if bar.period != timedelta(minutes=1):
            return None, "not_one_minute_period"
        return _decimal(bar.close, "same-session RAW closing-minute close", positive=True), None
    except Exception:
        # Unreadable Python/CLR cache data produces a reason and the existing
        # complete-census refusal; it never produces an authoritative mark.
        return None, "closing_minute_unavailable_or_invalid"
""").body[0])
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
security_sids = {security_id: sid for sid, security_id in sid_to_security.items()}
repair_prices = {}
repair_reasons = {}
for security_id in missing:
    price, reason = self._same_session_closing_minute_price(
        session, reference_securities[security_id], security_sids[security_id])
    repair_reasons[security_id] = reason
    if price is not None:
        repair_prices[security_id] = price
if len(repair_prices) == len(missing):
    result.update(repair_prices)
    self._reference_closing_minute_repair_count += len(missing)
    self._reference_closing_minute_repair_sessions.add(session)
    self._reference_closing_minute_repair_path.extend(
        [[session, security_hash] for security_hash in missing_hashes])
    return result
entries = []
for security_id, security_hash in zip(missing[:32], missing_hashes[:32]):
    delisted = getattr(reference_securities[security_id], "is_delisted", None)
    entries.append({
        "security_id_sha256": security_hash,
        "role": ("target_and_held" if security_id in target_security_ids and security_id in holding_quantities
                 else "target_only" if security_id in target_security_ids else "held_only"),
        "holding_quantity": holding_quantities.get(security_id, 0),
        "is_delisted": delisted if type(delisted) is bool else None,
        "closing_minute_refusal_reason": (repair_reasons[security_id]
            or "fresh_closing_minute_available_census_incomplete"),
    })
context = _canonical({
    "session": session,
    "requested_count": len(security_ids),
    "received_count": len(result),
    "missing_count": len(missing),
    "fresh_closing_minute_available_count": len(repair_prices),
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
        sources[path] = _render_fee_basis(path, _render_reference_refusal(path,
            _render_diagnostics(path, _render_identity(path, source, arm, slippage_bps), arm, slippage_bps)))
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


def _authenticated_qcom_security_id(package):
    """Bind the exclusion to the reviewed logical ID, never a current ticker."""
    if (type(package) is not _delta.AcceptedRiskDeltaOrderPackage
            or package.package.package_sha256 != _delta.EXPECTED_DELTA_PACKAGE_SHA256):
        _error("QCOM exclusion requires the exact historical package")
    _manifest, roles = _delta._load_prior_roles(package.package)
    bindings = roles["runtime_symbol_bindings"]
    matches = [row for row in bindings
               if type(row) is dict and row.get("diagnostic_current_ticker") == "QCOM"]
    if len(matches) != 1 or type(matches[0].get("security_id")) is not str:
        _error("QCOM exclusion historical identity is missing or ambiguous")
    security_id = matches[0]["security_id"]
    if (not security_id or hashlib.sha256(security_id.encode("utf-8")).hexdigest()
            != QCOM_EXCLUSION_SECURITY_ID_SHA256):
        _error("QCOM exclusion historical identity differs from R225 diagnostic")
    return security_id


def _render_qcom_exclusion(path, source, security_id, arm, slippage_bps):
    """Change only eligibility/guards and variant schemas in a rendered arm."""
    old_role = f"matched_historical_{arm}_s{slippage_bps}"
    new_role = f"matched_qcom_excluded_{arm}_s{slippage_bps}"
    old_variant = f"cap90_matched_historical_{arm}_s{slippage_bps}_v1"
    new_variant = f"cap90_matched_qcom_excluded_{arm}_s{slippage_bps}_v1"
    changed_paths = (_relaxed._GATE_PATH, "accepted_risk_six_universe_order_qc_runtime.py",
                     _relaxed._TILT_RUNTIME_PATH, "main.py")
    if path not in changed_paths and old_role not in source and old_variant not in source:
        return source
    tree = ast.parse(source)

    class ExactRuntimeIdentity(ast.NodeTransformer):
        count = 0

        def visit_Constant(self, node):
            replacement = {old_role: new_role, old_variant: new_variant}.get(node.value) if type(node.value) is str else None
            if replacement is not None:
                self.count += 1
                node.value = replacement
            return node

    identity = ExactRuntimeIdentity()
    tree = identity.visit(tree)
    if path not in changed_paths and identity.count == 0:
        _error("QCOM exclusion role/variant identity anchor changed")
    if path == _relaxed._GATE_PATH:
        constants = {
            "EXCLUDED_QCOM_SECURITY_ID": security_id,
            "EXCLUDED_QCOM_SECURITY_ID_SHA256": QCOM_EXCLUSION_SECURITY_ID_SHA256,
        }
        insertion = next((index for index, node in enumerate(tree.body)
                          if isinstance(node, (ast.Assign, ast.AnnAssign, ast.ClassDef, ast.FunctionDef))), None)
        if insertion is None:
            _error("QCOM exclusion gate insertion anchor changed")
        tree.body[insertion:insertion] = [ast.Assign([ast.Name(name, ast.Store())], ast.Constant(value))
                                          for name, value in constants.items()]
        schema_count = 0
        for node in tree.body:
            if (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id in ("PROFILE_SCHEMA", "CONSTRUCTION_SCHEMA")
                    and isinstance(node.value, ast.Constant) and type(node.value.value) is str):
                node.value.value += "-qcom-excluded-v1"
                schema_count += 1
        semantic = _named_function(tree, "_profile_semantic")
        semantic_returns = [node for node in semantic.body
                            if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict)]
        if len(semantic_returns) != 1:
            _error("QCOM exclusion profile disclosure anchor changed")
        profile_dict = semantic_returns[0].value
        keys = [key.value if isinstance(key, ast.Constant) else None for key in profile_dict.keys]
        if (schema_count != 2 or keys.count("minimum_positive_score_count") != 1
                or "excluded_logical_security_sha256" in keys):
            _error("QCOM exclusion gate schema or profile anchor changed")
        profile_dict.keys.extend((ast.Constant("stock_exclusion_policy_id"),
                                  ast.Constant("excluded_logical_security_sha256"),
                                  ast.Constant("stock_exclusion_scope")))
        profile_dict.values.extend((ast.Constant(QCOM_EXCLUSION_POLICY_ID),
                                    ast.Name("EXCLUDED_QCOM_SECURITY_ID_SHA256", ast.Load()),
                                    ast.Constant("all_six_stock_sleeves_all_decisions_2021_2025_coverage_denominators_unchanged")))
        sleeve = _named_function(tree, "_raw_sleeve")
        coverage = [node for node in ast.walk(sleeve) if isinstance(node, ast.Assign)
                    and ast.unparse(node) == "coverage = _coverage(rows, profile, snapshot.universe_id)"]
        selected = [node for node in sleeve.body if isinstance(node, ast.Assign)
                    and isinstance(node.value, ast.Call)
                    and ast.unparse(node.value.func) == "_selected_ids"]
        xle = [node for node in ast.walk(sleeve) if isinstance(node, ast.Assign)
               and any(isinstance(target, ast.Name) and target.id == "eligible"
                       for target in node.targets)]
        if (len(coverage) != 1 or len(selected) != 1 or len(xle) != 1
                or len(selected[0].value.args) != 3
                or ast.unparse(selected[0].value.args[0]) != "rows"
                or not isinstance(xle[0].value, ast.Call)
                or len(xle[0].value.args) != 1
                or not isinstance(xle[0].value.args[0], ast.GeneratorExp)
                or len(xle[0].value.args[0].generators) != 1
                or ast.unparse(xle[0].value.args[0].generators[0].iter) != "rows"):
            _error("QCOM exclusion eligibility anchor changed")
        # The original rows still determine source validity and coverage.
        # Only stock rank/entry candidates are filtered; unfilled capital
        # follows the unchanged own-sleeve ETF rule.
        sleeve.body.insert(sleeve.body.index(selected[0]), ast.parse(
            "eligible_rows = tuple(row for row in rows if row.security_id != EXCLUDED_QCOM_SECURITY_ID)"
        ).body[0])
        selected[0].value.args[0] = ast.Name("eligible_rows", ast.Load())
        xle[0].value.args[0].generators[0].iter = ast.Name("eligible_rows", ast.Load())
    elif path == "accepted_risk_six_universe_order_qc_runtime.py":
        schema = [node for node in tree.body if isinstance(node, ast.Assign)
                  and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                  and node.targets[0].id == "META_SCHEMA"]
        reference = _named_function(tree, "_reference_prices")
        closing = _named_function(tree, "on_after_close")
        holdings = [node for node in closing.body if isinstance(node, ast.Assign)
                    and ast.unparse(node) == "holdings = self._current_holding_census()"]
        if (len(schema) != 1 or len(holdings) != 1
                or not isinstance(schema[0].value, ast.Constant)
                or type(schema[0].value.value) is not str):
            _error("QCOM exclusion runtime guard anchor changed")
        schema[0].value = ast.Constant(QCOM_EXCLUSION_META_SCHEMA)
        closing.body.insert(closing.body.index(holdings[0]) + 1, ast.parse('''
if (_gate.EXCLUDED_QCOM_SECURITY_ID in target_weights
        or _gate.EXCLUDED_QCOM_SECURITY_ID in holdings):
    _error("QCOM-excluded sensitivity contains an excluded target or holding")
''').body[0])
        reference.body.insert(0, ast.parse('''
if _gate.EXCLUDED_QCOM_SECURITY_ID in security_ids:
    _error("QCOM-excluded sensitivity requested an excluded reference")
''').body[0])
    elif path == _relaxed._TILT_RUNTIME_PATH:
        summaries = [node for node in tree.body if isinstance(node, ast.Assign)
                  and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                  and node.targets[0].id == "TILT_SUMMARY_SCHEMA"]
        metas = [node for node in tree.body if isinstance(node, ast.Assign)
                 and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                 and node.targets[0].id == "TILT_META_SCHEMA"]
        profile_schemas = [node for node in tree.body if isinstance(node, ast.Assign)
                           and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                           and node.targets[0].id == "TILT_PROFILE_SCHEMA"]
        updates = [node.args[0] for node in ast.walk(_named_function(tree, "require_tilt_profile"))
                   if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                       and isinstance(node.func.value, ast.Name) and node.func.value.id == "seed"
                       and node.func.attr == "update" and len(node.args) == 1
                       and isinstance(node.args[0], ast.Dict))]
        aggregate_updates = [node.args[0] for node in ast.walk(_named_function(tree, "_aggregate"))
                             if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                                 and isinstance(node.func.value, ast.Name) and node.func.value.id == "aggregate"
                                 and node.func.attr == "update" and len(node.args) == 1
                                 and isinstance(node.args[0], ast.Dict))]
        if (len(summaries) != 1 or not isinstance(summaries[0].value, ast.Constant)
                or len(metas) != 1 or len(profile_schemas) != 1
                or not isinstance(profile_schemas[0].value, ast.Constant)
                or len(aggregate_updates) != 1
                or len(updates) != 1):
            _error("QCOM exclusion summary schema anchor changed")
        summaries[0].value = ast.Constant(QCOM_EXCLUSION_SUMMARY_SCHEMA)
        metas[0].value = ast.Constant(QCOM_EXCLUSION_META_SCHEMA)
        profile_schemas[0].value = ast.Constant("arv2-six-matched-qcom-excluded-profile-v1")
        keys = [key.value if isinstance(key, ast.Constant) else None for key in updates[0].keys]
        aggregate_keys = [key.value if isinstance(key, ast.Constant) else None
                          for key in aggregate_updates[0].keys]
        if (keys.count("maximum_stock_weight_change_fraction") != 1
                or aggregate_keys.count("maximum_stock_weight_change_fraction") != 1
                or "stock_exclusion_policy_id" in keys
                or "stock_exclusion_policy_id" in aggregate_keys):
            _error("QCOM exclusion tilt profile disclosure anchor changed")
        profile_ids = [index for index, key in enumerate(keys) if key == "profile_id"]
        if len(profile_ids) != 1:
            _error("QCOM exclusion tilt profile ID anchor changed")
        updates[0].values[profile_ids[0]] = ast.Constant(
            f"arv2-six-matched-qcom-excluded-{arm}-s{slippage_bps}-profile-v1")
        updates[0].keys.extend((ast.Constant("stock_exclusion_policy_id"),
                                ast.Constant("excluded_logical_security_sha256")))
        updates[0].values.extend((ast.Constant(QCOM_EXCLUSION_POLICY_ID),
                                  ast.Constant(QCOM_EXCLUSION_SECURITY_ID_SHA256)))
        aggregate_updates[0].keys.extend((ast.Constant("stock_exclusion_policy_id"),
                                          ast.Constant("excluded_logical_security_sha256")))
        aggregate_updates[0].values.extend((ast.Constant(QCOM_EXCLUSION_POLICY_ID),
                                            ast.Constant(QCOM_EXCLUSION_SECURITY_ID_SHA256)))
    elif path == "main.py":
        classes = [node for node in tree.body if isinstance(node, ast.ClassDef)
                   and node.name == f"ARV2MatchedHistorical{arm.title().replace('_', '')}S{slippage_bps}Algorithm"]
        if len(classes) != 1:
            _error("QCOM exclusion main algorithm anchor changed")
        classes[0].name = classes[0].name.replace("Algorithm", "QcomExcludedAlgorithm")
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def build_qcom_exclusion_projection(package, arm, slippage_bps=0):
    """Prospective QCOM-excluded stock sensitivity; not a rerun of R225.

    This preserves every original constituent/coverage denominator and all
    historical input bytes. It excludes one authenticated logical security
    from stock eligibility from the first decision in both stock arms.
    """
    if type(arm) is not str or arm not in ("ar_off", "ar_on100"):
        _error("QCOM exclusion needs the exact two stock arms")
    if type(slippage_bps) is not int or slippage_bps not in SLIPPAGE_BPS:
        _error("QCOM exclusion needs zero or five bps slippage")
    security_id = _authenticated_qcom_security_id(package)
    predecessor, old_profile = build_matched_historical_projection(package, arm, slippage_bps)
    sources = {item.project_path: _render_qcom_exclusion(item.project_path,
        item.source_bytes.decode("ascii"), security_id, arm, slippage_bps)
        for item in predecessor.source_files}
    with _relaxed._cloud_loader(sources) as (load, _):
        baseline = load(_relaxed._BRIDGE_NAME).require_bridge_profile("matched")
        sources[_relaxed._TILT_RUNTIME_PATH] = _relaxed._replace(
            sources[_relaxed._TILT_RUNTIME_PATH],
            old_profile["matched_baseline_profile_sha256"], baseline["profile_sha256"])
        runtime = load(_relaxed._TILT_RUNTIME_PATH[:-3])
        profile = runtime.require_tilt_profile()
        runtime.expected_tilt_custom_statistic_names()
        if (profile.get("stock_exclusion_policy_id") != QCOM_EXCLUSION_POLICY_ID
                or profile.get("excluded_logical_security_sha256") != QCOM_EXCLUSION_SECURITY_ID_SHA256
                or runtime.TILT_META_SCHEMA != QCOM_EXCLUSION_META_SCHEMA
                or runtime.TILT_SUMMARY_SCHEMA != QCOM_EXCLUSION_SUMMARY_SCHEMA):
            _error("QCOM exclusion profile or transport schema changed")
    files = tuple(sorted((_base._source_file(path, source.encode("ascii"))
                          for path, source in sources.items()), key=lambda item: item.project_path))
    total = sum(item.byte_count for item in files)
    if (len(files) != 17 or len({item.project_path for item in files}) != 17
            or any(item.byte_count > _base.MAXIMUM_QC_SOURCE_CHARACTERS for item in files)
            or total + _base.MINIMUM_REVIEW_MARGIN_BYTES > _base.MAXIMUM_TOTAL_SOURCE_BYTES):
        _error("QCOM-excluded source closure exceeded unchanged QC budgets")
    for item in files:
        _base._audit_source(item.project_path, item.source_bytes)
    value = dataclasses.replace(predecessor,
        schema="arv2-six-matched-qcom-excluded-projection-v1",
        variant=f"cap90_matched_qcom_excluded_{arm}_s{slippage_bps}_v1", role=profile["role"],
        profile_id=profile["profile_id"], profile_sha256=profile["profile_sha256"],
        source_files=files, total_source_byte_count=total)
    semantic = {key: item for key, item in value.to_record().items()
                if key not in ("projection_id", "projection_sha256")}
    digest = hashlib.sha256(_base._canonical(semantic)).hexdigest()
    return dataclasses.replace(value, projection_sha256=digest,
        projection_id="arv2-six-matched-qcom-excluded-projection-" + digest[:24]), json.loads(_base._canonical(profile))


# These are new prospective arms. The R231--R234 renderer above and its source
# closure remain frozen, including the R232 100% reference used below.
QCOM_EXCLUSION_TILT_PERCENTS = (80, 120, 200)


def _render_qcom_exclusion_tilt(path, source, percent):
    """Change only the 100% arm's transfer strength and tilt identities."""
    target_path = _relaxed._TILT_TARGET_PATH
    runtime_path = _relaxed._TILT_RUNTIME_PATH
    if path not in (target_path, runtime_path, "main.py"):
        return source
    arm = f"ar_on{percent}"
    fraction = f"{percent // 100}.{percent % 100:02d}"
    role = f"matched_qcom_excluded_{arm}_s0"
    variant = f"cap90_matched_qcom_excluded_{arm}_s0_v1"
    old_role = "matched_qcom_excluded_ar_on100_s0"
    old_variant = "cap90_matched_qcom_excluded_ar_on100_s0_v1"
    replacements = {
        target_path: {
            old_role: (role, 1),
            "arv2-six-universe-order-tilt100-guard-decision-target-v1-all25-v1-matched-ar_on100-s0-v1":
                (f"arv2-six-universe-order-tilt{percent}-guard-decision-target-v1-all25-v1-matched-{arm}-s0-v1", 1),
            "arv2-six-universe-order-tilt100-guard-target-path-v1-all25-v1-matched-ar_on100-s0-v1":
                (f"arv2-six-universe-order-tilt{percent}-guard-target-path-v1-all25-v1-matched-{arm}-s0-v1", 1),
            "arv2-six-universe-order-tilt100-guard-target-path-all25--matched-ar_on100-s0-v1":
                (f"arv2-six-universe-order-tilt{percent}-guard-target-path-all25--matched-{arm}-s0-v1", 1),
            "1.00": (fraction, 2),
        },
        runtime_path: {
            old_variant: (variant, 1),
            "arv2-six-matched-qcom-excluded-profile-v1":
                (f"arv2-six-matched-qcom-excluded-tilt{percent}-profile-v1", 1),
            QCOM_EXCLUSION_META_SCHEMA:
                (f"arv2-six-matched-qcom-excluded-tilt{percent}-meta-v1", 1),
            QCOM_EXCLUSION_SUMMARY_SCHEMA:
                (f"arv2-six-matched-qcom-excluded-tilt{percent}-summary-v1", 1),
            "arv2-six-matched-qcom-excluded-ar_on100-s0-profile-v1":
                (f"arv2-six-matched-qcom-excluded-{arm}-s0-profile-v1", 1),
            "ar_on100": (arm, 2),
            "1.00": (fraction, 2),
        },
        "main.py": {old_role: (role, 1), old_variant: (variant, 1)},
    }
    expected = replacements[path]
    counts = {value: 0 for value in expected}

    class TiltIdentity(ast.NodeTransformer):
        class_count = 0
        description_count = 0

        def visit_Constant(self, node):
            if type(node.value) is str:
                if node.value in expected:
                    counts[node.value] += 1
                    node.value = expected[node.value][0]
                elif path == target_path and "bounded by 100% of its own post-cap" in node.value:
                    self.description_count += 1
                    node.value = node.value.replace("bounded by 100% of its own post-cap",
                                                    f"bounded by {percent}% of its own post-cap")
            return node

        def visit_ClassDef(self, node):
            if path == "main.py" and node.name == "ARV2MatchedHistoricalArOn100S0QcomExcludedAlgorithm":
                self.class_count += 1
                node.name = f"ARV2MatchedHistoricalArOn{percent}S0QcomExcludedAlgorithm"
            return self.generic_visit(node)

    transform = TiltIdentity()
    tree = transform.visit(ast.parse(source))
    if (any(counts[value] != expected[value][1] for value in expected)
            or transform.class_count != int(path == "main.py")
            or transform.description_count != int(path == target_path)):
        _error("QCOM-excluded tilt exact source anchor changed")
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def build_qcom_exclusion_tilt_projection(package, percent, slippage_bps=0):
    """Prospective 80/120/200% QCOM-excluded AR-on physical-order sources.

    The percentage scales each stock's own post-cap weight transfer capacity;
    it does not scale the 98% portfolio target or the admission leverage.
    The matched gate, bridge, historical package and R232 baseline are common.
    """
    if type(percent) is not int or percent not in QCOM_EXCLUSION_TILT_PERCENTS:
        _error("QCOM-excluded tilt percent must be exactly 80, 120 or 200")
    if type(slippage_bps) is not int or slippage_bps != 0:
        _error("QCOM-excluded tilt study requires zero modeled slippage")
    predecessor, original_profile = build_qcom_exclusion_projection(package, "ar_on100", 0)
    sources = {item.project_path: _render_qcom_exclusion_tilt(
        item.project_path, item.source_bytes.decode("ascii"), percent)
        for item in predecessor.source_files}
    with _relaxed._cloud_loader(sources) as (load, _):
        runtime = load(_relaxed._TILT_RUNTIME_PATH[:-3])
        profile = runtime.require_tilt_profile()
        runtime.expected_tilt_custom_statistic_names()
        if (profile.get("maximum_stock_weight_change_fraction")
                != f"{percent // 100}.{percent % 100:02d}"
                or profile.get("comparison_arm") != f"ar_on{percent}"
                or profile.get("matched_baseline_profile_sha256")
                != original_profile["matched_baseline_profile_sha256"]
                or profile.get("stock_exclusion_policy_id") != QCOM_EXCLUSION_POLICY_ID
                or profile.get("excluded_logical_security_sha256")
                != QCOM_EXCLUSION_SECURITY_ID_SHA256
                or profile.get("modeled_fee_bps_per_side") != "10"
                or profile.get("slippage_bps") != "0"):
            _error("QCOM-excluded tilt profile or order economics changed")
    files = tuple(sorted((_base._source_file(path, source.encode("ascii"))
                          for path, source in sources.items()), key=lambda item: item.project_path))
    total = sum(item.byte_count for item in files)
    if (len(files) != 17 or len({item.project_path for item in files}) != 17
            or any(item.byte_count > _base.MAXIMUM_QC_SOURCE_CHARACTERS for item in files)
            or total + _base.MINIMUM_REVIEW_MARGIN_BYTES > _base.MAXIMUM_TOTAL_SOURCE_BYTES):
        _error("QCOM-excluded tilt source closure exceeded unchanged QC budgets")
    for item in files:
        _base._audit_source(item.project_path, item.source_bytes)
    arm = f"ar_on{percent}"
    value = dataclasses.replace(predecessor,
        schema=f"arv2-six-matched-qcom-excluded-tilt{percent}-projection-v1",
        variant=f"cap90_matched_qcom_excluded_{arm}_s0_v1", role=profile["role"],
        profile_id=profile["profile_id"], profile_sha256=profile["profile_sha256"],
        source_files=files, total_source_byte_count=total)
    semantic = {key: item for key, item in value.to_record().items()
                if key not in ("projection_id", "projection_sha256")}
    digest = hashlib.sha256(_base._canonical(semantic)).hexdigest()
    return dataclasses.replace(value, projection_sha256=digest,
        projection_id=f"arv2-six-matched-qcom-excluded-tilt{percent}-projection-" + digest[:24]), json.loads(_base._canonical(profile))
