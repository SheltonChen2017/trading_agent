"""Pure fixed-source projection for one QC-local W5 coverage observation.

This prepares public code only. It never creates a project, reads source DATA,
loads credentials, submits a job or grants a run. Frozen dependencies retain
their original dormant diagnostic/publication methods; the NEW entrypoint and
coverage module cannot call History, orders or Object Store writes.
"""
import ast
import dataclasses
import hashlib
import json
import re

from scripts import arv2_r298_native_price_source_projection as previous
from research.analyst_revisions_v2_qc import newrule_available_history_native_coverage as coverage

SCHEMA = "arv2-r329-native-coverage-projection-v1"
PROFILE_SCHEMA = SCHEMA + "-profile"
PATCHER_NAME = "arv2_r329_native_coverage_projection.py"
PREDECESSOR_NAME = "arv2_r298_native_price_source_projection.py"
READER_NAME = "newrule_native_price_book_runtime.py"
PERIOD_NAME = "arv2_r327_available_history_period.py"
COVERAGE_NAME = "newrule_available_history_native_coverage.py"
LEGACY_SOURCE_PINS = {
    "accepted_risk_preliminary_rating_policy.py": "7d45e0c294d03b5775ca6bd911043ea1e9b819e448eb7107fcbf0a2f162e36bd",
    "accepted_risk_preliminary_rating_evaluator.py": "2fb9bc8a8f74e37b57acb97f4d20b5820be04b9ee470fc2f34b3a8ea2c804910",
    "accepted_risk_preliminary_qc_figi.py": "4ee85d92126e31d3bde9acaffb992a54cf44b02efa876157597b876086da7ca9",
    "accepted_risk_six_universe_order_qc_runtime.py": "84e4d69135ff13f592e071574d22b30255088f4df22bd11f33943c652d81a46a",
    "newrule_plain_input_runtime.py": "bc07c0bebc141ecad38c774a52ea3bddaad4664a7dd85ccf47581572ef9beb8f",
    "newrule_native_price_source_diagnostic.py": "57450eac9126831bc9d1c106325ed1832c10ba32e883563bb85e10060948e697",
    "newrule_native_price_book_publication.py": "03d100e962b98cd8b174d947a33636e421692445422c0dcce2282b46015435e2",
    "arv2_r298_ae_source_binding.py": "d67e13dfb73885a335345648a4149f1968b3ba2aebc26405ea409681a1be6bb1",
}
SOURCE_PINS = {
    **LEGACY_SOURCE_PINS,
    PREDECESSOR_NAME: "a34385be7b5dbf95c30a669fc251689edbe3e8e0429386b188d2ac103907da3e",
    READER_NAME: "76b2a193fe1b8de9c9f8c598464edc2d0058b61aa690e13cc6216051f862a3f6",
    PERIOD_NAME: "722cffeae9fbebcd9bca656c8994273d2b1fb36f6d3e269a018c8fb18e5b7b18",
    COVERAGE_NAME: "f0f74cdc920f79d13e1e89ac0e60f71f993edeb72d2ac6853e13fc7a83798202",
}
CLOUD_NAMES = tuple(sorted((*previous.CLOUD_NAMES, READER_NAME, PERIOD_NAME, COVERAGE_NAME)))
# Exact outputs of the named frozen normalizations, finalized with the new
# coverage source before any operational run freeze. No on-disk refresh exists.
CLOUD_DEPENDENCY_PINS = {
    "accepted_risk_order_level_input_runtime.py": "b3f48e1b1c6fc6cc665d9f8b475292260074feec5571eab6e8f0d1c1a091fd35",
    "accepted_risk_preliminary_qc_figi.py": "5958786ddd787a45a90d636a36d07136841ee79cf1ce904c8d749d47045ff81d",
    "accepted_risk_preliminary_rating_evaluator.py": "d706a19324f59ac36e910b715c3ee17312a7126444287d9eba18c8fc8d06c21a",
    "accepted_risk_preliminary_rating_policy.py": "be082935781e8d406e5c6126fe33bb08866bc765b1d1ac162a96df4c0c988fd7",
    PERIOD_NAME: "2f2143c37a6dbdc5e8f6ff284f2b36ef45b29f11b82146c9daf2864ad3f98424",
    "newrule_legacy_primitives.py": "2e8c22a26182a4fb46d3dc759b28e0da537c98e3a8c0c306aecd62f5bada8999",
    "newrule_native_price_book_publication.py": "f625466fbeda3f59170ef49b76ebd31900a391dc8025589e621c31cc91326085",
    READER_NAME: "5c266ef5af0d6b06bf6a98b024d2166e38ea4046ced088e8dd5557d0ea390d1c",
    "newrule_native_price_source_diagnostic.py": "1e1c43c106ebef50973f26b9202b6393e4ab47e4b62e26433da32ffc662d085c",
    COVERAGE_NAME: "b6236ea7c32417d4f49b281bc2e5a7262d1c2080b1a3811cbe5b6d01497854e3",
}
MAX_INPUT_FILE_BYTES = previous.MAX_INPUT_FILE_BYTES
MAX_CLOUD_FILE_BYTES = previous.MAX_CLOUD_FILE_BYTES
MAX_TOTAL_CLOUD_BYTES = previous.MAX_TOTAL_CLOUD_BYTES
MAX_RECORD_BYTES = previous.MAX_RECORD_BYTES
MAX_STATISTIC_BYTES = 8002
ALGORITHM_SESSION = "2026-10-14"
FALSE_FLAGS = {**previous.FALSE_FLAGS, "source_book_recreated": False,
    "source_data_exported": False, "price_coverage_admitted": False,
    "current_project_verified": False, "new_launch_attempt_granted": False}
FORBIDDEN_NEW_CALLS = frozenset((*previous.FORBIDDEN_CALLS, "save_bytes", "history", "History",
    "NativePriceSourceDiagnostic", "SpecificSourceBookNamespace", "prepare", "publish",
    "set_market_price", "set_security_initializer", "set_security_seed", "log", "debug",
    "error", "quit", "set_runtime_statistic", "send", "request", "getenv"))
FINITE = frozenset(("project", "sources", "source_pin", "source_bound", "generator",
    "context", "coverage_profile", "cloud_audit", "cloud_closure", "projection", "profile", "unknown"))


class Refused(ValueError):
    """Finite public-code predicate; no private data or exception rendering."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else "unknown"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False).encode("ascii")


def sha(raw):
    require(type(raw) is bytes, "sources")
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(canonical(value))


def _hash(value):
    return type(value) is str and re.fullmatch("[0-9a-f]{64}", value) is not None


def _project(value):
    require(type(value) is int and 0 < value <= 2147483647 and value != 38364439, "project")
    return value


def _pairs(values):
    result = {}
    for key, value in values:
        require(key not in result, "projection")
        result[key] = value
    return result


def _json(raw):
    try:
        return json.loads(raw, object_pairs_hook=_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused("projection")))
    except (ValueError, UnicodeError, RecursionError):
        raise Refused("projection") from None


def _sources(value):
    require(previous.SOURCE_PINS == LEGACY_SOURCE_PINS, "source_pin")
    require(type(value) is dict and set(value) == set(SOURCE_PINS), "sources")
    for name, expected in SOURCE_PINS.items():
        raw = value[name]
        require(type(raw) is bytes and 0 < len(raw) <= MAX_INPUT_FILE_BYTES
            and raw.isascii() and _hash(expected) and sha(raw) == expected, "source_pin")
    return dict(value)


def _audit(raw, name):
    """Fixed dependencies retain dormant methods; the new call path is stricter."""
    try:
        previous._audit(raw, name)
        tree = ast.parse(raw)
        if name in (COVERAGE_NAME, "main.py", PERIOD_NAME):
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    called = node.func.attr if isinstance(node.func, ast.Attribute) else \
                        node.func.id if isinstance(node.func, ast.Name) else None
                    regex_compile = isinstance(node.func, ast.Attribute) and node.func.attr == "compile" \
                        and isinstance(node.func.value, ast.Name) and node.func.value.id == "re"
                    require(called not in FORBIDDEN_NEW_CALLS or regex_compile, "cloud_audit")
        # A complete cloud dependency set takes the first branch of these exact
        # frozen ImportError fallbacks. No scripts/research module is deployed.
        permitted = {item[:-3] for item in CLOUD_NAMES} | {"AlgorithmImports", "System",
            "collections", "dataclasses", "datetime", "decimal", "enum", "fractions", "hashlib",
            "itertools", "json", "math", "re", "time", "types", "typing", "zoneinfo"}
        host_fallbacks = set()
        for item in tree.body:
            if isinstance(item, ast.Try) and item.body and all(isinstance(child, (ast.Import, ast.ImportFrom))
                    for child in item.body) and len(item.handlers) == 1 and not item.orelse and not item.finalbody:
                handler = item.handlers[0]
                if isinstance(handler.type, ast.Name) and handler.type.id == "ImportError":
                    host_fallbacks.update(id(child) for child in handler.body if isinstance(child, ast.ImportFrom))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                require(all(alias.name.split(".")[0] in permitted for alias in node.names), "cloud_closure")
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                require(root in permitted or (root in ("research", "scripts") and id(node) in host_fallbacks),
                    "cloud_closure")
    except Refused:
        raise
    except Exception:
        raise Refused("cloud_audit") from None


def _normalized(raw, name):
    try:
        value = previous._normalize(raw, name)
        _audit(value, name)
        return value
    except Refused:
        raise
    except Exception:
        raise Refused("cloud_audit") from None


def _dependencies(supplied):
    names = ("accepted_risk_preliminary_qc_figi.py", "accepted_risk_preliminary_rating_evaluator.py",
        "accepted_risk_preliminary_rating_policy.py", previous.NATIVE_NAME, previous.PUBLICATION_NAME,
        READER_NAME, PERIOD_NAME, COVERAGE_NAME)
    cloud = {name: _normalized(supplied[name], name) for name in names}
    cloud["accepted_risk_order_level_input_runtime.py"] = _normalized(
        supplied[previous.PLAIN_LOADER], "accepted_risk_order_level_input_runtime.py")
    try:
        cloud["newrule_legacy_primitives.py"] = previous._money_source(supplied[previous.LEGACY_ORIGINAL])
    except Exception:
        raise Refused("source_pin") from None
    require({name: sha(raw) for name, raw in sorted(cloud.items())} == CLOUD_DEPENDENCY_PINS,
        "source_pin")
    return cloud


def _coverage_profile(project_id):
    try:
        value = coverage.profile_record(project_id)
        require(type(value) is dict and len(canonical(value)) <= MAX_RECORD_BYTES, "coverage_profile")
        require(coverage.MAX_STATISTIC_BYTES == MAX_STATISTIC_BYTES, "coverage_profile")
        require(coverage.reader.SOURCE_CONTEXT_SHA256 ==
            "dca0fb0cc15093a1fd892dfbfc2f4d1216a330bcf4bf355625cc07e774e3e07b", "context")
        return json.loads(canonical(value))
    except Refused:
        raise
    except Exception:
        raise Refused("coverage_profile") from None


def _main(profile):
    checked = _coverage_profile(_project(profile["project_id"]))
    require(profile["coverage_profile"] == checked, "coverage_profile")
    raw = f'''from AlgorithmImports import *
import newrule_available_history_native_coverage as coverage
EXPECTED_PROFILE = {checked!r}
class AvailableHistoryNativeCoverageAlgorithm(QCAlgorithm):
    def initialize(self):
        if getattr(self, "_coverage_init_claimed", False):
            raise RuntimeError("native_coverage_duplicate_initialize")
        self._coverage_init_claimed = True
        self._coverage_done = False
        self._coverage_emit_attempted = False
        self._coverage = None
        try:
            coverage.require(type(self.project_id) is int and self.project_id == {profile['project_id']}, "project")
            coverage.require(self.live_mode is False, "orders")
            self.set_time_zone("America/New_York")
            self.set_account_currency("USD")
            self.settings.daily_precise_end_time = True
            self.settings.seed_initial_prices = False
            self.set_start_date(2026, 10, 14)
            self.set_end_date(2026, 10, 14)
            self.set_cash(1000000)
            etfs = {{ticker: self.add_equity(ticker, Resolution.DAILY, fill_forward=False, leverage=1,
                extended_market_hours=False, data_normalization_mode=DataNormalizationMode.RAW).symbol
                for ticker in coverage.period.OWN_FUNDS}}
            self.set_benchmark(etfs["SPY"])
            self._coverage = coverage.AvailableHistoryNativeCoverage(self,
                runtime_project_id={profile['project_id']}, benchmark_symbol=etfs["SPY"], etf_symbols=etfs,
                trade_bar_type=TradeBar, daily_resolution=Resolution.DAILY,
                raw_normalization=DataNormalizationMode.RAW)
            observed = self._coverage.observe_once()
            observed = coverage.validate_summary(observed, expected_profile=EXPECTED_PROFILE)
            raw = coverage.canonical(observed)
            coverage.require(type(raw) is bytes and 0 < len(raw) <= {MAX_STATISTIC_BYTES}, "summary")
            self._coverage_emit_attempted = True
            self.set_summary_statistic(coverage.STATISTIC, raw.decode("ascii"))
            coverage.require(observed["terminal"] == "complete", "summary")
            self._coverage.assert_no_orders()
            self._coverage_done = True
        except Exception as error:
            raise RuntimeError("native_coverage_refused/" + coverage.finite(error)) from None
    def on_data(self, data):
        if self._coverage is not None:
            self._coverage.assert_no_orders()
    def on_end_of_algorithm(self):
        if not self._coverage_done or not self._coverage_emit_attempted or self._coverage is None:
            raise RuntimeError("native_coverage_not_finished")
        self._coverage.assert_no_orders()
'''
    return _normalized(raw.encode("ascii"), "main.py")


def profile_record():
    return {"schema": PROFILE_SCHEMA, "source_pins": dict(SOURCE_PINS),
        "cloud_dependency_pins": dict(CLOUD_DEPENDENCY_PINS), "cloud_file_names": list(CLOUD_NAMES),
        "maximum_cloud_file_bytes": MAX_CLOUD_FILE_BYTES, "maximum_total_cloud_bytes": MAX_TOTAL_CLOUD_BYTES,
        "maximum_custom_statistic_bytes": MAX_STATISTIC_BYTES,
        "algorithm_window": [ALGORITHM_SESSION, ALGORITHM_SESSION],
        "no_order_exception": "read_existing_QC_book_dated_native_reference_NAV_coverage_not_strategy_performance",
        "new_entrypoints": "AvailableHistoryNativeCoverage.observe_once_only_no_old_prepare_publication_History",
        "frozen_dependency_capabilities": "unchanged_dormant_History_and_store_write_methods_present_not_invoked",
        "cloud_imports": "all_flat_dependencies_supplied_research_scripts_host_fallbacks_never_needed",
        "existing_data": "read_only_exact_QC_private_book_no_source_recreation_no_raw_export",
        "source_pin_qualification": "selected_public_sources_not_whole_interpreter_or_actual_cloud_readback",
        "external_gates": ["owner_resource_release", "paid_private_organization_processing_rights",
            "exact_owned_project_access_idle_capacity", "actual_source_readback", "attempt_and_run_freeze"],
        **FALSE_FLAGS}


@dataclasses.dataclass(frozen=True, slots=True)
class SourceProjection:
    projection_sha256: str
    record_bytes: bytes = dataclasses.field(repr=False)
    profile_bytes: bytes = dataclasses.field(repr=False)
    source_pairs: tuple = dataclasses.field(repr=False)

    def to_record(self):
        value, _, _ = validate_public_projection(self.record_bytes, self.profile_bytes, self.source_pairs,
            expected_projection_sha256=self.projection_sha256,
            expected_profile_sha256=_json(self.profile_bytes)["profile_sha256"])
        return value


def generate(*, project_id, sources, generator_source_bytes, expected_generator_sha256):
    """Explicit-project source derivation only; no operational authority."""
    project_id = _project(project_id)
    require(type(generator_source_bytes) is bytes and 0 < len(generator_source_bytes) <= MAX_INPUT_FILE_BYTES
        and generator_source_bytes.isascii() and _hash(expected_generator_sha256)
        and sha(generator_source_bytes) == expected_generator_sha256, "generator")
    supplied = _sources(sources)
    cloud = _dependencies(supplied)
    observed_profile = _coverage_profile(project_id)
    seed = {"schema": PROFILE_SCHEMA, "project_id": project_id, "coverage_profile": observed_profile,
        "coverage_profile_sha256": digest(observed_profile), "generator_sha256": expected_generator_sha256,
        "raw_source_pins": dict(SOURCE_PINS), "cloud_dependency_pins": dict(CLOUD_DEPENDENCY_PINS),
        "policy_sha256": digest(profile_record()), **FALSE_FLAGS}
    profile = {**seed, "profile_sha256": digest(seed)}
    cloud["main.py"] = _main(profile)
    pairs = tuple(sorted(cloud.items()))
    require(tuple(name for name, _ in pairs) == CLOUD_NAMES
        and sum(len(raw) for _, raw in pairs) <= MAX_TOTAL_CLOUD_BYTES, "source_bound")
    record = {"schema": SCHEMA, "project_id": project_id, "profile_sha256": profile["profile_sha256"],
        "coverage_profile_sha256": digest(observed_profile), "policy_sha256": digest(profile_record()),
        "source_files": [{"name": name, "byte_count": len(raw), "sha256": sha(raw)} for name, raw in pairs],
        **FALSE_FLAGS}
    result = SourceProjection(digest(record), canonical(record), canonical(profile), pairs)
    result.to_record()
    return result


def validate_public_projection(record_bytes, profile_bytes, source_pairs, *,
        expected_projection_sha256, expected_profile_sha256):
    require(type(record_bytes) is bytes and 0 < len(record_bytes) <= MAX_RECORD_BYTES
        and type(profile_bytes) is bytes and 0 < len(profile_bytes) <= MAX_RECORD_BYTES
        and _hash(expected_projection_sha256) and sha(record_bytes) == expected_projection_sha256
        and _hash(expected_profile_sha256), "projection")
    record, profile = _json(record_bytes), _json(profile_bytes)
    record_keys = {"schema", "project_id", "profile_sha256", "coverage_profile_sha256", "policy_sha256",
        "source_files", *FALSE_FLAGS}
    profile_keys = {"schema", "project_id", "coverage_profile", "coverage_profile_sha256", "generator_sha256",
        "raw_source_pins", "cloud_dependency_pins", "policy_sha256", "profile_sha256", *FALSE_FLAGS}
    require(type(record) is dict and set(record) == record_keys and canonical(record) == record_bytes
        and type(profile) is dict and set(profile) == profile_keys and canonical(profile) == profile_bytes, "projection")
    seed = dict(profile)
    declared = seed.pop("profile_sha256")
    require(record["schema"] == SCHEMA and profile["schema"] == PROFILE_SCHEMA
        and declared == expected_profile_sha256 == digest(seed) == record["profile_sha256"]
        and profile["raw_source_pins"] == SOURCE_PINS
        and profile["cloud_dependency_pins"] == CLOUD_DEPENDENCY_PINS
        and _hash(profile["generator_sha256"])
        and all(record[key] is profile[key] is False for key in FALSE_FLAGS)
        and profile["policy_sha256"] == record["policy_sha256"] == digest(profile_record()), "profile")
    project_id = _project(profile["project_id"])
    observed = _coverage_profile(project_id)
    require(type(record["project_id"]) is int and record["project_id"] == project_id
        and profile["coverage_profile"] == observed
        and profile["coverage_profile_sha256"] == record["coverage_profile_sha256"] == digest(observed), "coverage_profile")
    require(type(source_pairs) is tuple and len(source_pairs) == len(CLOUD_NAMES)
        and all(type(pair) is tuple and len(pair) == 2 for pair in source_pairs)
        and tuple(name for name, _ in source_pairs) == CLOUD_NAMES, "sources")
    cloud = dict(source_pairs)
    require(all(type(raw) is bytes and 0 < len(raw) <= MAX_CLOUD_FILE_BYTES for raw in cloud.values())
        and sum(len(raw) for raw in cloud.values()) <= MAX_TOTAL_CLOUD_BYTES
        and cloud["main.py"] == _main(profile)
        and {name: sha(raw) for name, raw in source_pairs if name != "main.py"} == CLOUD_DEPENDENCY_PINS
        and record["source_files"] == [{"name": name, "byte_count": len(raw), "sha256": sha(raw)}
            for name, raw in source_pairs], "projection")
    for name, raw in source_pairs:
        _audit(raw, name)
        compile(raw, name, "exec")
        compile(b"from AlgorithmImports import *\n" + raw, name, "exec")
    return record, profile, source_pairs
