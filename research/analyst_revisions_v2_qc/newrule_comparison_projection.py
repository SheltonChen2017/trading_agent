"""Pinned host-only source projection for six real retrospective portfolios.

No provider, Object Store, QC job or order is invoked here. Exact October
package admission and explicit new source pins are mandatory. Generated
legacy primitives contain selected read/accounting methods only, never the
old MOO initializer/executor. Selected byte pins are not interpreter integrity.
"""

import ast
import dataclasses
import hashlib
import json
from pathlib import Path

from . import accepted_risk_october_order_package as october
from . import accepted_risk_preliminary_package as compact
from . import newrule_comparison_qc_runtime as runtime
from . import newrule_comparison_targets as targets


ROOT = Path("/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2/research/analyst_revisions_v2_qc")
OLD_PINS = {
    "accepted_risk_preliminary_rating_policy.py": "7d45e0c294d03b5775ca6bd911043ea1e9b819e448eb7107fcbf0a2f162e36bd",
    "accepted_risk_preliminary_rating_evaluator.py": "2fb9bc8a8f74e37b57acb97f4d20b5820be04b9ee470fc2f34b3a8ea2c804910",
    "accepted_risk_order_level_core.py": "063ed8fb7024c879a640780c07723c7edfb95665acc711d02fc8be0d964e965f",
    "accepted_risk_order_level_forced_exit.py": "21ef6978d7c26b833b0ec553298584c360f03d602f3c244f2fc8645bd113ec3f",
    "accepted_risk_order_level_input_runtime.py": "a08098648d98a95736471113d48a3e1183f04969d2c2561b1a4f5d6bfc80d7ee",
    "accepted_risk_preliminary_qc_figi.py": "4ee85d92126e31d3bde9acaffb992a54cf44b02efa876157597b876086da7ca9",
    "accepted_risk_six_universe_order_qc_runtime.py": "84e4d69135ff13f592e071574d22b30255088f4df22bd11f33943c652d81a46a",
    "accepted_risk_six_universe_order_qc_projection.py": "5037fdc1153c9ac927a540201fa92cb45db463e8313e0c88e04ddc9f0eb301f6",
}
NEW_SOURCE_NAMES = (
    "accepted_risk_october_order_package.py", "accepted_risk_preopen_rating_score.py",
    "newrule_comparison_targets.py", "newrule_comparison_qc_runtime.py",
    "newrule_comparison_projection.py",
)
EXTRACT_FUNCTIONS = ("_error", "_canonical", "_sha", "_decimal", "_decimal_text", "_symbol_sid")
EXTRACT_METHODS = ("_require_initialized", "_portfolio_equity", "_portfolio_cash",
    "configure_security", "on_securities_changed", "_symbol_for_security", "_ensure_security",
    "_prune_execution_subscriptions", "_current_quantity", "_current_holding_census",
    "_reference_prices", "_external_order_event", "_observe_account")
FORBIDDEN_IMPORTS = frozenset(("os", "socket", "subprocess", "requests", "urllib", "http",
                              "aiohttp", "shutil", "ftplib", "pathlib"))
FORBIDDEN_CALLS = frozenset(("open", "exec", "eval", "download", "save", "save_bytes", "write",
    "write_bytes", "set_holdings", "set_brokerage_model", "liquidate", "limit_order",
    "stop_market_order", "cancel_order", "update_order", "market_on_open_order"))


def require(value, code):
    targets.require(value, code)


def normalize(source, path):
    require(type(source) is bytes and 0 < len(source) <= 100000, "source_bound")
    tree = ast.parse(source.decode("ascii"), filename=path)
    require(not any(isinstance(node, ast.ImportFrom) and node.module == "__future__"
                    for node in ast.walk(tree)), "source_future")
    normalized = (ast.unparse(tree) + "\n").encode("ascii")
    require(ast.dump(tree, include_attributes=False) == ast.dump(ast.parse(normalized), include_attributes=False),
            "source_ast_changed")
    require(len(normalized) <= 64000, "qc_file_character_bound")
    compile(normalized, path, "exec")
    compile(b"from AlgorithmImports import *\n" + normalized, path, "exec")
    return normalized


def audit(path, source):
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            require(not {alias.name.split(".")[0] for alias in node.names} & FORBIDDEN_IMPORTS,
                    "forbidden_import")
        elif isinstance(node, ast.ImportFrom):
            require((node.module or "").split(".")[0] not in FORBIDDEN_IMPORTS,
                    "forbidden_import")
        elif isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else (
                node.func.id if isinstance(node.func, ast.Name) else None)
            require(name not in FORBIDDEN_CALLS, "forbidden_call")
    for attribute, expected in (("market_order", 1 if path == "newrule_comparison_qc_runtime.py" else 0),
            ("remove_security", 1 if path == "newrule_legacy_primitives.py" else 0),
            ("market_on_open_order", 0)):
        require(sum(isinstance(node, ast.Attribute) and node.attr == attribute
                    for node in ast.walk(tree)) == expected, "capability_inventory")
    require(not any(isinstance(node, ast.Constant) and node.value in
                    ("market_order", "market_on_open_order", "remove_security") for node in ast.walk(tree)),
            "dynamic_order_capability")


def _node(tree, name, kind):
    values = [item for item in tree.body if type(item) is kind and item.name == name]
    require(len(values) == 1, "exact_ast_anchor")
    return values[0]


def legacy_primitives(source):
    require(hashlib.sha256(source).hexdigest() == OLD_PINS["accepted_risk_six_universe_order_qc_runtime.py"],
            "legacy_runtime_pin")
    tree = ast.parse(source)
    old = _node(tree, "AcceptedRiskSixUniverseOrderQcDriver", ast.ClassDef)
    body = [_node(old, name, ast.FunctionDef) for name in EXTRACT_METHODS]
    selected = [_node(tree, "AcceptedRiskSixUniverseOrderQcRuntimeError", ast.ClassDef)]
    selected.extend(_node(tree, name, ast.FunctionDef) for name in EXTRACT_FUNCTIONS)
    selected.append(ast.ClassDef(name=old.name, bases=[], keywords=[], body=body, decorator_list=[]))
    prelude = ast.parse("""import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal, DecimalException, localcontext
import accepted_risk_order_level_forced_exit as _forced
STARTING_CASH = Decimal('1000000')
MAXIMUM_REFERENCE_SECURITIES = 256
MAXIMUM_REFERENCE_HISTORY_CALLS = 400
MAXIMUM_ACTIVE_DYNAMIC_SECURITY_COUNT = 192
""")
    result = ast.fix_missing_locations(ast.Module(body=prelude.body + selected, type_ignores=[]))
    rendered = (ast.unparse(result) + "\n").encode("ascii")
    copied = _node(ast.parse(rendered), old.name, ast.ClassDef)
    require(tuple(item.name for item in copied.body) == EXTRACT_METHODS, "legacy_method_inventory")
    for before, after in zip(body, copied.body, strict=True):
        require(ast.dump(before, include_attributes=False) == ast.dump(after, include_attributes=False),
                "legacy_method_ast_changed")
    return rendered


def reflected_status_source(source):
    require(hashlib.sha256(source).hexdigest() == OLD_PINS["accepted_risk_six_universe_order_qc_projection.py"],
            "legacy_projection_pin")
    function = _node(ast.parse(source), "_main_source", ast.FunctionDef)
    constants = [node.value.value for node in function.body if type(node) is ast.Assign
        and len(node.targets) == 1 and type(node.targets[0]) is ast.Name
        and node.targets[0].id == "reflected" and type(node.value) is ast.Constant
        and type(node.value.value) is str]
    require(len(constants) == 1, "reflected_status_anchor")
    reflected = constants[0]
    _node(ast.parse(reflected), "_arv2_reflected_order_status", ast.FunctionDef)
    return reflected


def main_source(profile, activation, old_projection):
    reflected = reflected_status_source(old_projection)
    return f'''from AlgorithmImports import *
from decimal import Decimal
{reflected}
from newrule_comparison_qc_runtime import NewruleComparisonDriver, STARTING_CASH

class NewruleTenBpsFeeModel(FeeModel):
    def get_order_fee(self, parameters):
        price = Decimal(str(parameters.security.price))
        quantity = abs(Decimal(str(parameters.order.absolute_quantity)))
        if not price.is_finite() or price <= 0 or not quantity.is_finite():
            raise RuntimeError("newrule fee input")
        return OrderFee(CashAmount(price * quantity * Decimal("0.001"), "USD"))

class NewruleComparisonAlgorithm(QCAlgorithm):
    def initialize(self):
        self.set_time_zone("America/New_York")
        self.settings.daily_precise_end_time = True
        self.settings.seed_initial_prices = True
        self.set_start_date(2020, 11, 1)
        self.set_end_date(2026, 10, 13)
        self.set_cash(STARTING_CASH)
        self.universe_settings.asynchronous = False
        self.universe_settings.resolution = Resolution.DAILY
        self.universe_settings.data_normalization_mode = DataNormalizationMode.RAW
        etfs = {{ticker: self.add_equity(ticker, Resolution.MINUTE, fill_forward=(ticker == "SPY"),
            leverage=1, extended_market_hours=(ticker == "SPY"), data_normalization_mode=DataNormalizationMode.RAW).symbol
            for ticker in {targets.UNIVERSES!r}}}
        self.set_benchmark(etfs["SPY"])
        fundamentals = self.add_universe(self._fundamentals)
        constituents = {{}}
        for ticker in {targets.UNIVERSES!r}:
            callback = lambda rows, ticker=ticker: self._constituents(ticker, rows)
            constituents[ticker] = self.add_universe(self.universe.etf(etfs[ticker], self.universe_settings, callback))
        self._driver = NewruleComparisonDriver(self, profile={profile!r},
            activation_manifest_key={activation.object_store_key!r},
            activation_manifest_sha256={activation.content_sha256!r},
            activation_manifest_byte_count={activation.byte_count},
            benchmark_symbol=etfs["SPY"], etf_symbols=etfs,
            fundamental_universe=fundamentals, constituent_universes=constituents,
            trade_bar_type=TradeBar, minute_resolution=Resolution.MINUTE, daily_resolution=Resolution.DAILY,
            raw_normalization=DataNormalizationMode.RAW, fee_model_factory=lambda: NewruleTenBpsFeeModel(),
            slippage_model_factory=lambda: NullSlippageModel(),
            order_status_enum=_arv2_reflected_order_status(OrderStatus),
            order_status_to_int=_Arv2DotNetConvert.ToInt32, split_occurred_type=SplitType.SPLIT_OCCURRED,
            split_warning_type=SplitType.WARNING, split_data_type=Split)
        self._driver.initialize()
        self.schedule.on(self.date_rules.every_day(etfs["SPY"]), self.time_rules.before_market_open(etfs["SPY"], 10), self._driver.on_before_open)
        self.schedule.on(self.date_rules.every_day(etfs["SPY"]), self.time_rules.after_market_open(etfs["SPY"], 1), self._driver.on_after_open)
        self.schedule.on(self.date_rules.every_day(etfs["SPY"]), self.time_rules.after_market_close(etfs["SPY"], 0), self._driver.on_after_close)
    def _fundamentals(self, rows):
        return [] if not hasattr(self, "_driver") else self._driver.accept_fundamentals(rows)
    def _constituents(self, ticker, rows):
        return [] if not hasattr(self, "_driver") else self._driver.accept_constituents(ticker, rows)
    def on_data(self, data):
        self._driver.on_data(data)
    def on_securities_changed(self, changes):
        if hasattr(self, "_driver"):
            self._driver.on_securities_changed(changes)
    def on_order_event(self, event):
        self._driver.on_order_event(event)
    def on_splits(self, splits):
        self._driver.on_splits(splits)
    def on_end_of_algorithm(self):
        self._driver.on_end_of_algorithm()
'''.encode("ascii")


@dataclasses.dataclass(frozen=True, slots=True)
class SourceFile:
    project_path: str
    source_bytes: bytes = dataclasses.field(repr=False)

    @property
    def content_sha256(self):
        return hashlib.sha256(self.source_bytes).hexdigest()

    @property
    def byte_count(self):
        return len(self.source_bytes)

    def to_record(self):
        return {"project_path": self.project_path, "byte_count": self.byte_count,
                "content_sha256": self.content_sha256}


@dataclasses.dataclass(frozen=True, slots=True)
class Projection:
    record_bytes: bytes
    projection_sha256: str
    source_files: tuple
    profile_bytes: bytes

    def to_record(self):
        value = json.loads(self.record_bytes)
        require(hashlib.sha256(self.record_bytes).hexdigest() == self.projection_sha256
                and value["source_files"] == [item.to_record() for item in self.source_files],
                "projection_binding")
        profile = json.loads(self.profile_bytes)
        seed = dict(profile)
        supplied = seed.pop("profile_sha256")
        require(targets.digest(seed) == supplied == value["profile_sha256"], "projection_profile_binding")
        return value


def render_projection(*, profile, activation, sources):
    """Internal synthetic-test seam, not a package-admitting public builder."""
    expected = set(OLD_PINS) | set(NEW_SOURCE_NAMES)
    require(type(sources) is dict and set(sources) == expected, "source_inventory")
    for name, pin in OLD_PINS.items():
        require(hashlib.sha256(sources[name]).hexdigest() == pin, "old_source_pin")
    require(profile["source_pins"] == {name: hashlib.sha256(payload).hexdigest()
                                      for name, payload in sorted(sources.items())}, "profile_source_pins")
    excluded = {"accepted_risk_six_universe_order_qc_runtime.py", "accepted_risk_six_universe_order_qc_projection.py",
                "accepted_risk_october_order_package.py", "newrule_comparison_projection.py"}
    raw = {name: value for name, value in sources.items() if name not in excluded}
    raw["newrule_legacy_primitives.py"] = legacy_primitives(sources["accepted_risk_six_universe_order_qc_runtime.py"])
    raw["main.py"] = main_source(profile, activation, sources["accepted_risk_six_universe_order_qc_projection.py"])
    files = []
    for name, source in sorted(raw.items()):
        normalized = normalize(source, name)
        audit(name, normalized)
        files.append(SourceFile(name, normalized))
    require(sum(item.byte_count for item in files) <= 448 * 1024, "source_total_bound")
    record = {"schema": "arv2-newrule-comparison-qc-projection-v1",
        "candidate_id": profile["candidate_id"], "profile_sha256": profile["profile_sha256"],
        "package_sha256": profile["package_sha256"], "lineage_sha256": profile["lineage_sha256"],
        "activation_manifest_key": activation.object_store_key,
        "activation_manifest_sha256": activation.content_sha256,
        "activation_manifest_byte_count": activation.byte_count,
        "source_files": [item.to_record() for item in files],
        "market_orders_only": True, "market_on_open_orders_only": False,
        "backtest_only": True, "point_in_time_proven": False, "formal_identity_admitted": False,
        "formal_forward_ready": False, "paper_or_live_ready": False}
    payload = targets.canonical(record)
    return Projection(payload, hashlib.sha256(payload).hexdigest(), tuple(files), targets.canonical(profile))


def build_projection(value, *, expected_package_sha256, expected_lineage_sha256,
                     expected_new_source_pins, universe_count, ar_percent):
    value = october.require_october_order_input_package(value)
    require(value.package.package_sha256 == expected_package_sha256
            and value.lineage_sha256 == expected_lineage_sha256, "external_package_pins")
    require(type(expected_new_source_pins) is dict and set(expected_new_source_pins) == set(NEW_SOURCE_NAMES),
            "new_source_pin_inventory")
    require(Path(__file__).parent == ROOT, "designated_source_root")
    sources = {}
    for name, pin in {**OLD_PINS, **expected_new_source_pins}.items():
        targets.require_sha(pin)
        path = ROOT / name
        require(path.is_file() and not path.is_symlink(), "source_regular_file")
        source = path.read_bytes()
        require(hashlib.sha256(source).hexdigest() == pin, "selected_source_pin")
        sources[name] = source
    package = compact.require_accepted_risk_preliminary_package(value.package)
    activation = package.upload_objects[-1]
    require(activation.activation_manifest is True and activation.content_sha256
            and activation.byte_count > 0, "activation_descriptor")
    profile = runtime.make_profile(october._sessions(),
        package_sha256=expected_package_sha256, lineage_sha256=expected_lineage_sha256,
        universe_count=universe_count, ar_percent=ar_percent,
        source_pins={name: hashlib.sha256(source).hexdigest() for name, source in sorted(sources.items())})
    return render_projection(profile=profile, activation=activation, sources=sources)
