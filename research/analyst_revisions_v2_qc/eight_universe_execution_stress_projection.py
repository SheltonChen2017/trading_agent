"""One frozen five-basis-point execution stress for the four fixed-100 arms.

This is a source projection, not a QC launcher. Each candidate derives from
exactly one already-authenticated zero-slippage source. The existing signed
installed-slippage MOO fee callback is deliberately left unchanged.
"""

import ast
import dataclasses
import hashlib
import json

from . import accepted_risk_six_universe_order_qc_projection as source_contract
from . import accepted_risk_six_universe_order_relaxed_qc_projection as loader
from . import eight_universe_ar_on_split_rounding as full_ar
from . import eight_universe_attribution_study as attribution
from . import eight_universe_r268_a3_split_rounding as cap_only


class EightUniverseExecutionStressProjectionError(ValueError):
    """The exact predecessor or execution-stress source anchor changed."""


SCHEMA = "arv2-eight-fixed100-five-bps-execution-stress-projection-v1"
CANDIDATE_PARENTS = {
    "R280": ("R268", "9bf45940b9215cdbfe17e868cb56f13ba65f382e9743d271fc768dcc442d6f76"),
    "R281": ("R277", "03833fe2e7990706ef5ac4d44120d7e9704ee94141fcd1a53d006fbd2059943e"),
    "R282": ("R278", "a9d3c606ade43291277e6ef3bcf9faaf4778bbea6fa1f70c1bc13abf6396a32f"),
    "R283": ("R270", "a063fc5bce74cdcc00c1bc8ce7fa3eff95b1db84f997d2e8acbc9dd24da0bec4"),
}
_MAIN = "main.py"
_TILT_RUNTIME = "accepted_risk_six_universe_order_tilt_qc_runtime.py"
_TILT_TARGETS = "accepted_risk_six_universe_order_tilt_targets.py"
CHANGED_SOURCE_PATHS = frozenset({_MAIN, _TILT_RUNTIME, _TILT_TARGETS})

# Kept inside main.py so the existing 17-file QC closure and three-statistic
# transport remain unchanged. The aggregate's META digest binds this summary.
_FILL_AUDIT_METHODS = """\
class _StressAuditMethods:
    def _arv2_capture_stress_fill(self, event):
        audit = self._arv2_stress_fills
        quantity = Decimal(str(event.fill_quantity))
        if not quantity.is_finite():
            audit['unverifiable'] += 1
            return
        if quantity == 0:
            return
        try:
            order = self.transactions.get_order_by_id(event.order_id)
        except Exception:
            audit['unverifiable'] += 1
            return
        if order is None:
            audit['unverifiable'] += 1
            return
        if order.type != OrderType.MARKET_ON_OPEN:
            return
        side = 'buy' if quantity > 0 else 'sell'
        audit[side] += 1
        try:
            bar = self.securities[event.symbol].get_last_data()
            if not isinstance(bar, TradeBar) or bar.end_time.date() != self.time.date():
                audit['unverifiable'] += 1
                return
            base = Decimal(str(bar.open))
            fill = Decimal(str(event.fill_price))
            if not base.is_finite() or base <= 0 or not fill.is_finite() or fill <= 0:
                audit['unverifiable'] += 1
                return
            signed_bps = ((fill - base) if quantity > 0 else (base - fill)) * Decimal(10000) / base
            if not signed_bps.is_finite():
                audit['unverifiable'] += 1
                return
            if signed_bps <= 0:
                audit['non_adverse'] += 1
            previous = audit['minimum_signed_bps']
            audit['minimum_signed_bps'] = signed_bps if previous is None else min(previous, signed_bps)
        except Exception:
            audit['unverifiable'] += 1

    def _arv2_stress_aggregate(self):
        aggregate = self._arv2_prior_aggregate()
        audit = self._arv2_stress_fills
        total = audit['buy'] + audit['sell']
        valid = (total == aggregate['execution']['filled_order_count_sum']
                 and audit['buy'] > 0 and audit['sell'] > 0
                 and audit['unverifiable'] == 0 and audit['non_adverse'] == 0
                 and audit['minimum_signed_bps'] is not None
                 and audit['minimum_signed_bps'] > 0)
        aggregate['execution_stress_fill_audit'] = {
            'schema': 'arv2-eight-five-bps-moo-fill-audit-v1',
            'filled_moo_count': total, 'buy_fill_count': audit['buy'],
            'sell_fill_count': audit['sell'],
            'unverifiable_fill_count': audit['unverifiable'],
            'non_adverse_fill_count': audit['non_adverse'],
            'minimum_signed_adverse_bps': (None if audit['minimum_signed_bps'] is None
                                           else str(audit['minimum_signed_bps'])),
            'reference': 'same-session-TradeBar-open',
            'valid': valid,
        }
        aggregate['run_valid'] = aggregate['run_valid'] and valid
        return aggregate
"""


def _fail(message):
    raise EightUniverseExecutionStressProjectionError(message)


def _parent(package, candidate):
    if type(candidate) is not str or candidate not in CANDIDATE_PARENTS:
        _fail("five-bps stress candidate is not frozen")
    parent_id, expected_sha = CANDIDATE_PARENTS[candidate]
    if parent_id == "R268":
        projection, profile = cap_only.build_projection(package)
    elif parent_id == "R270":
        projection, profile = full_ar.build_projection(package, "R270")
    else:
        projection, profile = attribution.build_projection(package, parent_id)
    if (projection.projection_sha256 != expected_sha
            or profile["profile_sha256"] != projection.profile_sha256
            or profile["slippage_bps"] != "0"
            or projection.role != profile["role"]
            or "_s0" not in projection.role
            or "_s0" not in projection.variant
            or "-s0-" not in projection.profile_id):
        _fail("five-bps stress predecessor source or profile changed")
    return projection, profile


def _function(tree, name):
    found = [node for node in ast.walk(tree)
             if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(found) != 1:
        _fail("five-bps stress exact function anchor changed: " + name)
    return found[0]


def _render(path, source, old, runtime_variant, candidate):
    tree = ast.parse(source)
    new_role = old.role.replace("_s0", "_s5")
    new_variant = runtime_variant.replace("_s0", "_s5")
    new_profile_id = old.profile_id.replace("-s0-", "-s5-")
    counts = {"role": 0, "variant": 0, "profile_id": 0,
              "model": 0, "slippage": 0, "diagnostics": 0,
              "fill_audit": 0, "class": 0}

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and type(node.value) is str:
            if node.value == old.role:
                node.value = new_role
                counts["role"] += 1
            elif node.value == runtime_variant:
                node.value = new_variant
                counts["variant"] += 1
            elif node.value == old.profile_id:
                node.value = new_profile_id
                counts["profile_id"] += 1

    if path == _MAIN:
        arguments = [node for node in ast.walk(tree)
                     if isinstance(node, ast.keyword)
                     and node.arg == "slippage_model_factory"]
        if (len(arguments) != 1
                or ast.unparse(arguments[0].value) != "lambda: NullSlippageModel()"):
            _fail("five-bps stress installed-model anchor changed")
        arguments[0].value = ast.parse(
            "lambda: ConstantSlippageModel(0.0005)", mode="eval").body
        counts["model"] = 1
        diagnostics = [node for node in ast.walk(tree)
                       if isinstance(node, ast.Call)
                       and isinstance(node.func, ast.Name)
                       and node.func.id == "install_matched_diagnostics"]
        if (len(diagnostics) != 1 or len(diagnostics[0].args) != 3
                or diagnostics[0].keywords
                or not isinstance(diagnostics[0].args[2], ast.Constant)
                or type(diagnostics[0].args[2].value) is not int
                or diagnostics[0].args[2].value != 0):
            _fail("five-bps stress diagnostic slippage anchor changed")
        diagnostics[0].args[2] = ast.Constant(5)
        counts["diagnostics"] = 1
        classes = [node for node in tree.body if isinstance(node, ast.ClassDef)
                   and node.name.startswith("ARV2")]
        if len(classes) != 1:
            _fail("five-bps stress algorithm class anchor changed")
        classes[0].name = f"ARV2Eight{candidate}FiveBpsStressAlgorithm"
        counts["class"] = 1
        initialize = _function(tree, "initialize")
        anchors = [index for index, statement in enumerate(initialize.body)
                   if isinstance(statement, ast.Expr)
                   and isinstance(statement.value, ast.Call)
                   and isinstance(statement.value.func, ast.Name)
                   and statement.value.func.id == "install_matched_diagnostics"]
        if len(anchors) != 1:
            _fail("five-bps stress fill-audit installation anchor changed")
        initialize.body[anchors[0] + 1:anchors[0] + 1] = ast.parse(
            "self._arv2_stress_fills = {'buy': 0, 'sell': 0, 'unverifiable': 0, "
            "'non_adverse': 0, 'minimum_signed_bps': None}\n"
            "self._arv2_prior_aggregate = self._arv2_driver._aggregate\n"
            "self._arv2_driver._aggregate = self._arv2_stress_aggregate\n"
        ).body
        order_event = _function(tree, "on_order_event")
        if len(order_event.body) != 1 or ast.unparse(order_event.body[0]) != \
                "self._arv2_driver.on_order_event(event)":
            _fail("five-bps stress order-event audit anchor changed")
        order_event.body[:0] = ast.parse("self._arv2_capture_stress_fill(event)").body
        methods = ast.parse(_FILL_AUDIT_METHODS).body[0].body
        classes[0].body.extend(methods)
        counts["fill_audit"] = 1
        fee = _function(tree, "get_order_fee")
        if ("get_slippage_approximation" not in ast.unparse(fee)
                or "OrderType.MARKET_ON_OPEN" not in ast.unparse(fee)):
            _fail("five-bps stress signed installed-slippage fee callback changed")
    elif path == _TILT_RUNTIME:
        function = _function(tree, "require_tilt_profile")
        updates = [node for node in ast.walk(function)
                   if isinstance(node, ast.Call)
                   and ast.unparse(node.func) == "seed.update"
                   and len(node.args) == 1
                   and isinstance(node.args[0], ast.Dict)]
        if len(updates) != 1:
            _fail("five-bps stress profile disclosure anchor changed")
        disclosed = updates[0].args[0]
        keys = [key.value if isinstance(key, ast.Constant) else None
                for key in disclosed.keys]
        if "slippage_bps" in keys:
            _fail("five-bps stress profile already has slippage override")
        disclosed.keys.append(ast.Constant("slippage_bps"))
        disclosed.values.append(ast.Constant("5"))
        counts["slippage"] = 1

    expected = {
        _MAIN: {"role": 1, "variant": 1, "profile_id": 0,
                "model": 1, "slippage": 0, "diagnostics": 1,
                "fill_audit": 1, "class": 1},
        _TILT_RUNTIME: {"role": 0, "variant": 1, "profile_id": 1,
                        "model": 0, "slippage": 1, "diagnostics": 0,
                        "fill_audit": 0, "class": 0},
        _TILT_TARGETS: {"role": 1, "variant": 0, "profile_id": 0,
                        "model": 0, "slippage": 0, "diagnostics": 0,
                        "fill_audit": 0, "class": 0},
    }
    if path not in expected or counts != expected[path]:
        _fail(f"five-bps stress source-change census changed: {path}: {counts}")
    ast.fix_missing_locations(tree)
    rendered = ast.unparse(tree) + "\n"
    if ast.dump(tree, include_attributes=False) != ast.dump(
            ast.parse(rendered), include_attributes=False):
        _fail("five-bps stress rendered AST changed")
    return rendered


def build_projection(package, candidate):
    """Build a distinct 17-file order source; no QC or provider I/O."""
    old, old_profile = _parent(package, candidate)
    originals = {item.project_path: item.source_bytes.decode("ascii")
                 for item in old.source_files}
    runtime_tree = ast.parse(originals[_TILT_RUNTIME])
    variants = [node.value.value for node in runtime_tree.body
                if isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "TILT_VARIANT"
                and isinstance(node.value, ast.Constant)
                and type(node.value.value) is str]
    if (len(variants) != 1 or "_s0" not in variants[0]
            or not old.variant.startswith(variants[0])):
        _fail("five-bps stress parent runtime variant changed")
    sources = {path: (_render(path, source, old, variants[0], candidate)
                      if path in CHANGED_SOURCE_PATHS else source)
               for path, source in originals.items()}
    if ({path for path in sources if sources[path] != originals[path]}
            != CHANGED_SOURCE_PATHS):
        _fail("five-bps stress source escaped three-file allowlist")
    with loader._cloud_loader(sources) as (load, _):
        runtime = load(_TILT_RUNTIME[:-3])
        profile = runtime.require_tilt_profile()
        runtime.expected_tilt_custom_statistic_names()
        if (profile["role"] != old.role.replace("_s0", "_s5")
                or profile["profile_id"] != old.profile_id.replace("-s0-", "-s5-")
                or profile["slippage_bps"] != "5"
                or profile["modeled_fee_bps_per_side"] != "10"
                or profile["target_gross_exposure"] != "0.98"
                or profile["admission_leverage"] != "2"
                or profile["comparison_arm"] != old_profile["comparison_arm"]
                or profile["analyst_revision_economic_usage"]
                   != old_profile["analyst_revision_economic_usage"]
                or profile["coverage_policy_id"] != old_profile["coverage_policy_id"]
                or profile["maximum_stock_weight_change_fraction"]
                   != old_profile["maximum_stock_weight_change_fraction"]
                or {key: value for key, value in profile.items()
                    if key not in ("profile_sha256", "profile_id", "role", "slippage_bps")}
                   != {key: value for key, value in old_profile.items()
                       if key not in ("profile_sha256", "profile_id", "role", "slippage_bps")}):
            _fail("five-bps stress changed selection, target or order economics")
    files = tuple(sorted((source_contract._source_file(path, source.encode("ascii"))
                          for path, source in sources.items()),
                         key=lambda item: item.project_path))
    total = sum(item.byte_count for item in files)
    if (len(files) != 17 or len({item.project_path for item in files}) != 17
            or any(item.byte_count > source_contract.MAXIMUM_QC_SOURCE_CHARACTERS
                   for item in files)
            or total + source_contract.MINIMUM_REVIEW_MARGIN_BYTES
               > source_contract.MAXIMUM_TOTAL_SOURCE_BYTES):
        _fail("five-bps stress QC source closure exceeded exact budget")
    for item in files:
        source_contract._audit_source(item.project_path, item.source_bytes)
    semantic = dataclasses.replace(old, schema=SCHEMA,
        role=profile["role"], variant=old.variant.replace("_s0", "_s5"),
        profile_id=profile["profile_id"], profile_sha256=profile["profile_sha256"],
        source_files=files, total_source_byte_count=total)
    record = {key: value for key, value in semantic.to_record().items()
              if key not in ("projection_id", "projection_sha256")}
    digest = hashlib.sha256(source_contract._canonical(record)).hexdigest()
    return dataclasses.replace(semantic, projection_sha256=digest,
        projection_id=f"arv2-eight-{candidate.lower()}-five-bps-stress-{digest[:24]}"), json.loads(
            source_contract._canonical(profile))


__all__ = ("CANDIDATE_PARENTS", "CHANGED_SOURCE_PATHS", "SCHEMA",
           "build_projection")
