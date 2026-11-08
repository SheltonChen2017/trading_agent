"""Pure exact-source projection for a NEW QC-only five-identity diagnostic.

No file, credential, source-data, provider, project, compile or backtest call
exists here. Supplied public code bytes are pinned before deriving aliases.
A separate committed actual-project/paid-org/access/attempt freeze is required.
"""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import re

from scripts import arv2_r298_ae_source_binding as ae
from research.analyst_revisions_v2_qc import newrule_native_price_source_diagnostic as diagnostic
from research.analyst_revisions_v2_qc import newrule_native_price_book_publication as publication

SCHEMA = "arv2-r298-native-price-source-projection-v1"
PROFILE_SCHEMA = SCHEMA + "-profile"
RESULT_SCHEMA = SCHEMA + "-result"
PATCHER_NAME = "arv2_r298_native_price_source_projection.py"
NATIVE_NAME = "newrule_native_price_source_diagnostic.py"
PUBLICATION_NAME = "newrule_native_price_book_publication.py"
AE_NAME = "arv2_r298_ae_source_binding.py"
LEGACY_ORIGINAL = "accepted_risk_six_universe_order_qc_runtime.py"
PLAIN_LOADER = "newrule_plain_input_runtime.py"
ACTIVATION = ("arv2/newrule-plain-v1/95405d1b569d4bfeeb6c6d87/transport-manifest.json",
    "ffdc80e1b6e76410ddd4840e5a21e49aea1dbdd5c735b6bcbd88bfe832e0233b", 5901)
SPECIFICATION_SHA256 = "9da6813b4807d7ebf0ea32fddd38ab0740ff6c6edbc3bd05cdc5889775eb1f66"
SOURCE_PINS = {
    "accepted_risk_preliminary_rating_policy.py": "7d45e0c294d03b5775ca6bd911043ea1e9b819e448eb7107fcbf0a2f162e36bd",
    "accepted_risk_preliminary_rating_evaluator.py": "2fb9bc8a8f74e37b57acb97f4d20b5820be04b9ee470fc2f34b3a8ea2c804910",
    "accepted_risk_preliminary_qc_figi.py": "4ee85d92126e31d3bde9acaffb992a54cf44b02efa876157597b876086da7ca9",
    LEGACY_ORIGINAL: "84e4d69135ff13f592e071574d22b30255088f4df22bd11f33943c652d81a46a",
    PLAIN_LOADER: "bc07c0bebc141ecad38c774a52ea3bddaad4664a7dd85ccf47581572ef9beb8f",
    NATIVE_NAME: "57450eac9126831bc9d1c106325ed1832c10ba32e883563bb85e10060948e697",
    PUBLICATION_NAME: "03d100e962b98cd8b174d947a33636e421692445422c0dcce2282b46015435e2",
    AE_NAME: "d67e13dfb73885a335345648a4149f1968b3ba2aebc26405ea409681a1be6bb1",
}
CLOUD_NAMES = tuple(sorted(("main.py", "accepted_risk_order_level_input_runtime.py",
    "accepted_risk_preliminary_qc_figi.py", "accepted_risk_preliminary_rating_evaluator.py",
    "accepted_risk_preliminary_rating_policy.py", "newrule_legacy_primitives.py",
    NATIVE_NAME, PUBLICATION_NAME)))
MAX_INPUT_FILE_BYTES, MAX_CLOUD_FILE_BYTES = 100000, 64000
MAX_TOTAL_CLOUD_BYTES, MAX_RECORD_BYTES, MAX_STATISTIC_BYTES = 320 * 1024, 128 * 1024, 16384
META_STATISTIC = "ARV2_NATIVE_SOURCE_META"
FORBIDDEN_IMPORTS = frozenset(("os", "socket", "subprocess", "requests", "urllib", "http",
    "aiohttp", "shutil", "ftplib", "pathlib", "pickle", "marshal", "importlib"))
FORBIDDEN_CALLS = frozenset(("open", "exec", "eval", "__import__", "compile", "print",
    "market_order", "market_on_open_order", "set_holdings", "liquidate", "limit_order",
    "stop_market_order", "cancel_order", "update_order", "set_brokerage_model", "remove_security",
    "download", "save", "save_string", "save_json", "save_xml", "delete", "clear"))
FALSE_FLAGS = {"project_created": False, "QC_contact_performed": False, "backtest_created": False,
    "paid_rights_granted": False, "private_organization_verified": False, "QC_processing_rights_granted": False,
    "source_or_strategy_price_admitted": False, "vendor_source_blockers_cleared": False,
    "strategy_result_accepted": False, "formal_identity_admitted": False,
    "point_in_time_proven": False, "formal_forward_ready": False, "paper_or_live_ready": False}
FINITE = frozenset(("project", "activation", "sources", "source_pin", "source_bound", "future",
    "legacy_ast", "cloud_audit", "specification", "scope", "generator", "profile", "projection", "unknown"))


class Refused(ValueError):
    """Finite public-code predicate only; no private row/exception rendering."""


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


def _project(value):
    require(type(value) is int and 0 < value <= 2147483647 and value != 38364439, "project")
    return value


def _specification():
    try:
        value = diagnostic.validate_specification(ae.expected_specification())
        require(digest(value) == SPECIFICATION_SHA256, "specification")
        return value
    except Refused:
        raise
    except Exception:
        raise Refused("specification") from None


def _scope(value, project_id, spec):
    try:
        require(type(value) is dict and "run_scope_tag" in value, "scope")
        publication.validate_scope(value)
        expected = publication.make_scope(project_id, digest(spec), value["run_scope_tag"])
        require(value == expected and value["own_project_id"] == project_id, "scope")
        return json.loads(canonical(expected))
    except Refused:
        raise
    except Exception:
        raise Refused("scope") from None


def _sources(value):
    require(type(value) is dict and set(value) == set(SOURCE_PINS), "sources")
    for name, pin in SOURCE_PINS.items():
        raw = value[name]
        require(type(raw) is bytes and 0 < len(raw) <= MAX_INPUT_FILE_BYTES
            and raw.isascii() and sha(raw) == pin, "source_pin")
    return dict(value)


def _no_annotations(tree):
    return not any(isinstance(node, ast.AnnAssign)
        or isinstance(node, ast.arg) and node.annotation is not None
        or isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and
            (node.returns is not None or getattr(node, "type_params", ()))
        for node in ast.walk(tree))


def _normalize(raw, name):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_INPUT_FILE_BYTES and raw.isascii(), "source_bound")
    tree = ast.parse(raw.decode("ascii"), filename=name)
    future = [node for node in tree.body if isinstance(node, ast.ImportFrom) and node.module == "__future__"]
    if future:
        require(len(future) == 1 and len(future[0].names) == 1
            and future[0].names[0].name == "annotations" and future[0].names[0].asname is None
            and _no_annotations(tree), "future")
        tree.body.remove(future[0])
    result = (ast.unparse(tree) + "\n").encode("ascii")
    require(ast.dump(tree, include_attributes=False) == ast.dump(ast.parse(result), include_attributes=False)
        and len(result) <= MAX_CLOUD_FILE_BYTES, "source_bound")
    compile(result, name, "exec")
    compile(b"from AlgorithmImports import *\n" + result, name, "exec")
    _audit(result, name)
    return result


def _node(tree, name, kind):
    values = [node for node in tree.body if isinstance(node, kind) and node.name == name]
    require(len(values) == 1, "legacy_ast")
    return values[0]


def _money_source(raw):
    require(sha(raw) == SOURCE_PINS[LEGACY_ORIGINAL], "source_pin")
    old = ast.parse(raw)
    names = ("_error", "_decimal", "_decimal_text")
    selected = [_node(old, "AcceptedRiskSixUniverseOrderQcRuntimeError", ast.ClassDef)]
    selected.extend(_node(old, name, ast.FunctionDef) for name in names)
    tree = ast.Module(body=ast.parse("from decimal import Decimal, DecimalException\n").body + selected,
        type_ignores=[])
    result = _normalize((ast.unparse(ast.fix_missing_locations(tree)) + "\n").encode("ascii"),
        "newrule_legacy_primitives.py")
    current = ast.parse(result)
    for name in names:
        require(ast.dump(_node(current, name, ast.FunctionDef), include_attributes=False)
            == ast.dump(_node(old, name, ast.FunctionDef), include_attributes=False), "legacy_ast")
    return result


def _audit(raw, name):
    tree = ast.parse(raw)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            require(not {alias.name.split(".")[0] for alias in node.names} & FORBIDDEN_IMPORTS, "cloud_audit")
        elif isinstance(node, ast.ImportFrom):
            require((node.module or "").split(".")[0] not in FORBIDDEN_IMPORTS
                and node.module != "__future__", "cloud_audit")
        elif isinstance(node, ast.Call):
            called = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else None
            regex_compile = (isinstance(node.func, ast.Attribute) and node.func.attr == "compile"
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "re")
            require((called not in FORBIDDEN_CALLS or regex_compile)
                and (called != "save_bytes" or name == PUBLICATION_NAME), "cloud_audit")


def _main(profile):
    profile = json.loads(canonical(profile))
    spec, scope = profile["specification"], profile["cache_scope"]
    raw = f'''from AlgorithmImports import *
import json
import newrule_native_price_source_diagnostic as diagnostic
import newrule_native_price_book_publication as publication
PROFILE = {profile!r}
SPECIFICATION = {spec!r}
CACHE_SCOPE = {scope!r}
MAX_META_BYTES = {MAX_STATISTIC_BYTES}
class NativePriceSourceAlgorithm(QCAlgorithm):
    def initialize(self):
        self._native_done = False
        self._native_statistic_attempted = False
        self._native_diagnostic = None
        self._native_publisher = None
        self._native_summary = None
        try:
            diagnostic.require(type(self.project_id) is int and self.project_id == {profile["project_id"]}, "settings")
            diagnostic.require(self.live_mode is False, "orders")
            self.set_time_zone("America/New_York")
            self.set_account_currency("USD")
            self.settings.daily_precise_end_time = True
            self.settings.seed_initial_prices = False
            self.set_start_date(2026, 10, 14)
            self.set_end_date(2026, 10, 14)
            self.set_cash(1000000)
            etfs = {{ticker: self.add_equity(ticker, Resolution.DAILY, fill_forward=False, leverage=1,
                extended_market_hours=False, data_normalization_mode=DataNormalizationMode.RAW).symbol
                for ticker in diagnostic.UNIVERSES}}
            self.set_benchmark(etfs["SPY"])
            self._native_diagnostic = diagnostic.NativePriceSourceDiagnostic(self,
                specification=SPECIFICATION, expected_specification_sha256={SPECIFICATION_SHA256!r},
                activation_manifest_key={ACTIVATION[0]!r}, activation_manifest_sha256={ACTIVATION[1]!r},
                activation_manifest_byte_count={ACTIVATION[2]}, benchmark_symbol=etfs["SPY"],
                etf_symbols=etfs, trade_bar_type=TradeBar, daily_resolution=Resolution.DAILY,
                raw_normalization=DataNormalizationMode.RAW)
            summary, book = self._native_diagnostic.prepare()
            self._native_summary = diagnostic.validate_summary(summary)
            self._native_publisher = publication.SpecificSourceBookNamespace(self,
                frozen_scope=CACHE_SCOPE, expected_scope_sha256={digest(scope)!r},
                expected_specification=SPECIFICATION)
            receipt = self._native_publisher.publish(self._native_summary, book)
            receipt = publication.validate_receipt(receipt, frozen_scope=CACHE_SCOPE,
                expected_specification=SPECIFICATION, expected_summary=self._native_summary)
            self._emit_native({{"schema": {RESULT_SCHEMA!r}, "project_id": {profile["project_id"]},
                "profile_sha256": {profile["profile_sha256"]!r}, "specification_sha256": {SPECIFICATION_SHA256!r},
                "terminal": "source_observation_QC_cache_written", "failure_code": None,
                "source_summary": self._native_summary, "publication": receipt,
                "publication_attempt": None, "strategy_result_accepted": False,
                "formal_forward_ready": False, "point_in_time_proven": False, "paper_or_live_ready": False}})
            self._native_done = True
        except Exception as error:
            code = diagnostic.finite(error)
            prefix = "diagnostic"
            if code == "unknown":
                code, prefix = publication.finite(error), "publication"
            if code == "unknown":
                prefix = "unknown"
            retained_summary = None
            if self._native_summary is not None:
                try:
                    retained_summary = diagnostic.validate_summary(self._native_summary)
                except Exception:
                    retained_summary = None
            attempt = None
            if self._native_publisher is not None:
                try:
                    attempt = publication.validate_attempt_record(self._native_publisher.attempt_record(),
                        frozen_scope=CACHE_SCOPE, expected_specification=SPECIFICATION, expected_summary=None)
                except Exception:
                    attempt = None
            failure = {{"schema": {RESULT_SCHEMA!r}, "project_id": {profile["project_id"]},
                "profile_sha256": {profile["profile_sha256"]!r}, "specification_sha256": {SPECIFICATION_SHA256!r},
                "terminal": "refused", "failure_code": prefix + "/" + code,
                "source_summary": retained_summary, "publication": None, "publication_attempt": attempt,
                "strategy_result_accepted": False, "formal_forward_ready": False,
                "point_in_time_proven": False, "paper_or_live_ready": False}}
            if not self._native_statistic_attempted:
                self._emit_native(failure)
            raise RuntimeError("native_source_diagnostic_refused") from None
    def _emit_native(self, value):
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
        if self._native_statistic_attempted or not 0 < len(raw) <= MAX_META_BYTES:
            raise RuntimeError("native_source_metadata_refused")
        self._native_statistic_attempted = True
        self.set_summary_statistic({META_STATISTIC!r}, raw.decode("ascii"))
    def on_data(self, data):
        if self._native_diagnostic is not None:
            self._native_diagnostic._no_orders()
    def on_end_of_algorithm(self):
        if not self._native_done or not self._native_statistic_attempted:
            raise RuntimeError("native_source_not_finished")
        self._native_diagnostic._no_orders()
'''
    return _normalize(raw.encode("ascii"), "main.py")


def profile_record():
    return {"schema": PROFILE_SCHEMA, "source_pins": dict(SOURCE_PINS),
        "activation": list(ACTIVATION), "specification_sha256": SPECIFICATION_SHA256,
        "cloud_file_names": list(CLOUD_NAMES), "maximum_cloud_file_bytes": MAX_CLOUD_FILE_BYTES,
        "maximum_total_cloud_bytes": MAX_TOTAL_CLOUD_BYTES, "maximum_custom_statistic_bytes": MAX_STATISTIC_BYTES,
        "algorithm_window": ["2026-10-14", "2026-10-14"], "raw_history_window": ["2020-12-31", "2026-10-13"],
        "no_order_exception": "exact_original_identity_and_RAW_source_availability_no_strategy_performance",
        "QC_data_location": "paid_organization_private_ObjectStore_only_no_host_raw_export",
        "calendar_policy": "independent_frozen_NYSE_schedule_hash_compared_before_History",
        "money_alias": "only_exact_AST_error_decimal_decimal_text_from_frozen_original_no_strategy_methods",
        "future_annotations_projection": "remove_annotations_future_only_after_proving_no_annotations_preserve_other_AST",
        "source_pin_qualification": "selected_source_bytes_not_whole_interpreter_or_deployed_cloud_version_proof",
        "standard_engine_statistics": "not_accepted_as_strategy_results",
        "new_project": "positive_exact_int_different_from_existing_R298_not_permission_to_create",
        "external_gates": ["paid_private_organization", "QC_cache_processing_rights", "storage_Create",
            "fresh_project_access_privacy", "source_input_identity", "idle_capacity", "attempt_accounting",
            "exact_compile_backtest_run_freeze"], **FALSE_FLAGS}


@dataclasses.dataclass(frozen=True, slots=True)
class SourceProjection:
    projection_sha256: str
    record_bytes: bytes = dataclasses.field(repr=False)
    profile_bytes: bytes = dataclasses.field(repr=False)
    source_pairs: tuple = dataclasses.field(repr=False)

    def to_record(self):
        value, _, _ = validate_public_projection(self.record_bytes, self.profile_bytes, self.source_pairs,
            expected_projection_sha256=self.projection_sha256,
            expected_profile_sha256=json.loads(self.profile_bytes)["profile_sha256"])
        return value


def generate(*, project_id, frozen_cache_scope, sources, generator_source_bytes,
             expected_generator_sha256, input_activation=ACTIVATION):
    """Pure concrete-project derivation, never an operational authorization."""
    project_id = _project(project_id)
    require(type(input_activation) is tuple and input_activation == ACTIVATION
        and tuple(type(value) for value in input_activation) == (str, str, int), "activation")
    require(type(generator_source_bytes) is bytes and 0 < len(generator_source_bytes) <= MAX_INPUT_FILE_BYTES
        and generator_source_bytes.isascii() and _hash(expected_generator_sha256)
        and sha(generator_source_bytes) == expected_generator_sha256, "generator")
    supplied = _sources(sources)
    spec = _specification()
    scope = _scope(frozen_cache_scope, project_id, spec)
    cloud = {
        "accepted_risk_order_level_input_runtime.py": _normalize(supplied[PLAIN_LOADER], "accepted_risk_order_level_input_runtime.py"),
        "accepted_risk_preliminary_qc_figi.py": _normalize(supplied["accepted_risk_preliminary_qc_figi.py"], "accepted_risk_preliminary_qc_figi.py"),
        "accepted_risk_preliminary_rating_evaluator.py": _normalize(supplied["accepted_risk_preliminary_rating_evaluator.py"], "accepted_risk_preliminary_rating_evaluator.py"),
        "accepted_risk_preliminary_rating_policy.py": _normalize(supplied["accepted_risk_preliminary_rating_policy.py"], "accepted_risk_preliminary_rating_policy.py"),
        "newrule_legacy_primitives.py": _money_source(supplied[LEGACY_ORIGINAL]),
        NATIVE_NAME: _normalize(supplied[NATIVE_NAME], NATIVE_NAME),
        PUBLICATION_NAME: _normalize(supplied[PUBLICATION_NAME], PUBLICATION_NAME),
    }
    seed = {"schema": PROFILE_SCHEMA, "project_id": project_id, "specification": spec,
        "specification_sha256": SPECIFICATION_SHA256, "cache_scope": scope, "cache_scope_sha256": digest(scope),
        "activation": list(ACTIVATION), "generator_sha256": expected_generator_sha256,
        "raw_source_pins": dict(SOURCE_PINS),
        "cloud_dependency_pins": {name: sha(raw) for name, raw in sorted(cloud.items())},
        "policy_sha256": digest(profile_record()), **FALSE_FLAGS}
    profile = {**seed, "profile_sha256": digest(seed)}
    cloud["main.py"] = _main(profile)
    pairs = tuple(sorted(cloud.items()))
    require(tuple(name for name, _ in pairs) == CLOUD_NAMES
        and sum(len(raw) for _, raw in pairs) <= MAX_TOTAL_CLOUD_BYTES, "source_bound")
    record = {"schema": SCHEMA, "project_id": project_id, "profile_sha256": profile["profile_sha256"],
        "specification_sha256": SPECIFICATION_SHA256, "cache_scope_sha256": digest(scope),
        "source_files": [{"name": name, "byte_count": len(raw), "sha256": sha(raw)} for name, raw in pairs],
        "policy_sha256": digest(profile_record()), **FALSE_FLAGS}
    raw_record, raw_profile = canonical(record), canonical(profile)
    result = SourceProjection(sha(raw_record), raw_record, raw_profile, pairs)
    result.to_record()
    return result


def validate_public_projection(record_bytes, profile_bytes, source_pairs, *,
                              expected_projection_sha256, expected_profile_sha256):
    require(type(record_bytes) is bytes and 0 < len(record_bytes) <= MAX_RECORD_BYTES
        and type(profile_bytes) is bytes and 0 < len(profile_bytes) <= MAX_RECORD_BYTES
        and _hash(expected_projection_sha256) and sha(record_bytes) == expected_projection_sha256
        and _hash(expected_profile_sha256), "projection")
    record, profile = _json(record_bytes), _json(profile_bytes)
    profile_keys = {"schema", "project_id", "specification", "specification_sha256", "cache_scope",
        "cache_scope_sha256", "activation", "generator_sha256", "raw_source_pins", "cloud_dependency_pins",
        "policy_sha256", "profile_sha256", *FALSE_FLAGS}
    record_keys = {"schema", "project_id", "profile_sha256", "specification_sha256", "cache_scope_sha256",
        "source_files", "policy_sha256", *FALSE_FLAGS}
    require(type(record) is dict and set(record) == record_keys and canonical(record) == record_bytes
        and type(profile) is dict and set(profile) == profile_keys and canonical(profile) == profile_bytes, "projection")
    seed = dict(profile); declared = seed.pop("profile_sha256")
    require(profile["schema"] == PROFILE_SCHEMA and record["schema"] == SCHEMA
        and declared == expected_profile_sha256 == digest(seed) == record["profile_sha256"]
        and profile["raw_source_pins"] == SOURCE_PINS and _hash(profile["generator_sha256"])
        and all(profile[key] is record[key] is False for key in FALSE_FLAGS)
        and profile["specification"] == _specification()
        and profile["specification_sha256"] == record["specification_sha256"] == SPECIFICATION_SHA256
        and profile["activation"] == list(ACTIVATION)
        and profile["policy_sha256"] == record["policy_sha256"] == digest(profile_record()), "profile")
    project_id = _project(profile["project_id"])
    scope = _scope(profile["cache_scope"], project_id, profile["specification"])
    require(type(record["project_id"]) is int and record["project_id"] == project_id
        and digest(scope) == profile["cache_scope_sha256"] == record["cache_scope_sha256"], "scope")
    require(type(source_pairs) is tuple and len(source_pairs) == len(CLOUD_NAMES)
        and all(type(pair) is tuple and len(pair) == 2 for pair in source_pairs)
        and tuple(name for name, _ in source_pairs) == CLOUD_NAMES, "sources")
    cloud = dict(source_pairs)
    require(all(type(raw) is bytes and 0 < len(raw) <= MAX_CLOUD_FILE_BYTES for raw in cloud.values())
        and sum(map(len, cloud.values())) <= MAX_TOTAL_CLOUD_BYTES
        and cloud["main.py"] == _main(profile)
        and profile["cloud_dependency_pins"] == {name: sha(raw) for name, raw in source_pairs if name != "main.py"}
        and record["source_files"] == [{"name": name, "byte_count": len(raw), "sha256": sha(raw)} for name, raw in source_pairs],
        "projection")
    for name, raw in source_pairs:
        _audit(raw, name)
    return record, profile, source_pairs
