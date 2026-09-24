"""Exact cloud-source projection for the six-universe order family.

This host-only builder authenticates the immutable delta input, renders one
role-specific LEAN entry point, and closes the source graph explicitly.  It
performs no network, QuantConnect, Object Store, outcome, or result access.
"""

import ast
import dataclasses
import hashlib
import json
from pathlib import Path

from . import accepted_risk_delta_order_package as _delta
from . import accepted_risk_preliminary_package as _package
from . import accepted_risk_six_universe_order_qc_runtime as _runtime
from . import accepted_risk_six_universe_order_targets as _targets


class AcceptedRiskSixUniverseOrderQcProjectionError(ValueError):
    """The package, source closure, entry point, or capability set changed."""


PROJECTION_SCHEMA = "arv2-six-universe-order-qc-projection-v1"
CAP90_PROJECTION_SCHEMA = "arv2-six-universe-order-qc-projection-cap90-v3"
SOURCE_FILE_SCHEMA = "arv2-six-universe-order-qc-source-file-v1"
MAIN_PROJECT_PATH = "main.py"
MAXIMUM_SOURCE_FILE_BYTES = 80 * 1024
# QC's file-management API refuses a Python source above 64,000 characters.
# Keep this platform bound distinct from the local source-review byte bound:
# only the new cap-90 projection is normalized; R-177 remains byte-identical.
MAXIMUM_QC_SOURCE_CHARACTERS = 64000
MAXIMUM_TOTAL_SOURCE_BYTES = 448 * 1024
MINIMUM_REVIEW_MARGIN_BYTES = 32 * 1024
ALGORITHM_START = (2020, 11, 1)
ALGORITHM_END = (2025, 12, 31)

_SOURCE_PATHS = (
    "accepted_risk_preliminary_rating_policy.py",
    "accepted_risk_preliminary_rating_evaluator.py",
    "accepted_risk_sequential_r055_score.py",
    "accepted_risk_order_level_core.py",
    "accepted_risk_order_level_forced_exit.py",
    "accepted_risk_order_level_input_runtime.py",
    "accepted_risk_preliminary_qc_figi.py",
    "accepted_risk_six_universe_gate.py",
    "accepted_risk_six_universe_gate_evaluator.py",
    "accepted_risk_simulated_moo_executor.py",
    "accepted_risk_six_universe_order_targets.py",
    "accepted_risk_six_universe_order_qc_runtime.py",
)

_FORBIDDEN_IMPORT_ROOTS = frozenset({
    "aiohttp",
    "ftplib",
    "http",
    "os",
    "requests",
    "shutil",
    "socket",
    "subprocess",
    "urllib",
})
_FORBIDDEN_CALL_NAMES = frozenset({
    "cancel_order",
    "delete",
    "download",
    "eval",
    "exec",
    "limit_order",
    "liquidate",
    "market_order",
    "open",
    "quit",
    "save",
    "save_bytes",
    "set_brokerage_model",
    "set_holdings",
    "stop_market_order",
    "system",
    "update_order",
    "write",
    "write_bytes",
})


def _error(message):
    raise AcceptedRiskSixUniverseOrderQcProjectionError(message)


def _canonical(value):
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise AcceptedRiskSixUniverseOrderQcProjectionError(
            "six-universe order projection is not canonical ASCII JSON"
        ) from exc


def _call_name(node):
    function = node.func
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        return function.attr
    return None


def _audit_source(project_path, source):
    try:
        text = source.decode("ascii")
        tree = ast.parse(text, filename=project_path)
        compile(text, project_path, "exec")
        compile(
            "from AlgorithmImports import *\n" + text,
            project_path,
            "exec",
        )
    except (SyntaxError, UnicodeDecodeError) as exc:
        raise AcceptedRiskSixUniverseOrderQcProjectionError(
            "six-universe projected source is not prelude-safe Python"
        ) from exc
    if "from __future__" in text:
        _error("six-universe projected source retained a future import")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = {item.name.split(".", 1)[0] for item in node.names}
            if roots & _FORBIDDEN_IMPORT_ROOTS:
                _error("six-universe projected source imported a forbidden capability")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root in _FORBIDDEN_IMPORT_ROOTS:
                _error("six-universe projected source imported a forbidden capability")
        elif isinstance(node, ast.Call):
            name = _call_name(node)
            if name in _FORBIDDEN_CALL_NAMES:
                _error("six-universe projected source called a forbidden capability")
    if text.count("market_on_open_order(") != (
        1 if project_path == "accepted_risk_six_universe_order_qc_runtime.py" else 0
    ):
        _error("six-universe projected MOO capability inventory changed")
    if text.count("remove_security(") != (
        1 if project_path == "accepted_risk_six_universe_order_qc_runtime.py" else 0
    ):
        _error("six-universe projected subscription-removal inventory changed")


@dataclasses.dataclass(frozen=True, slots=True)
class SixUniverseOrderQcSourceFile:
    schema: str
    project_path: str
    byte_count: int
    content_sha256: str
    source_bytes: bytes = dataclasses.field(repr=False)

    def to_record(self):
        return {
            "schema": self.schema,
            "project_path": self.project_path,
            "byte_count": self.byte_count,
            "content_sha256": self.content_sha256,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class AcceptedRiskSixUniverseOrderQcProjection:
    schema: str
    projection_id: str
    projection_sha256: str
    role: str
    variant: str
    profile_id: str
    profile_sha256: str
    package_id: str
    package_sha256: str
    package_lineage_sha256: str
    activation_manifest_key: str
    activation_manifest_sha256: str
    activation_manifest_byte_count: int
    source_files: tuple
    total_source_byte_count: int
    preliminary: bool
    formal: bool
    backtest_only: bool
    simulated_order_submission: bool
    market_on_open_orders_only: bool
    live_orders: bool
    paper_orders: bool
    funded_orders: bool
    deployment: bool
    trading: bool

    def to_record(self):
        record = {
            "schema": self.schema,
            "projection_id": self.projection_id,
            "projection_sha256": self.projection_sha256,
            "role": self.role,
            "profile_id": self.profile_id,
            "profile_sha256": self.profile_sha256,
            "package_id": self.package_id,
            "package_sha256": self.package_sha256,
            "package_lineage_sha256": self.package_lineage_sha256,
            "activation_manifest_key": self.activation_manifest_key,
            "activation_manifest_sha256": self.activation_manifest_sha256,
            "activation_manifest_byte_count": self.activation_manifest_byte_count,
            "source_files": [item.to_record() for item in self.source_files],
            "total_source_byte_count": self.total_source_byte_count,
            "preliminary": self.preliminary,
            "formal": self.formal,
            "backtest_only": self.backtest_only,
            "simulated_order_submission": self.simulated_order_submission,
            "market_on_open_orders_only": self.market_on_open_orders_only,
            "live_orders": self.live_orders,
            "paper_orders": self.paper_orders,
            "funded_orders": self.funded_orders,
            "deployment": self.deployment,
            "trading": self.trading,
        }
        # The R-177 record shape remains unchanged.  This field is part of
        # the distinct exploratory projection's authenticated semantics only.
        if self.variant == _runtime.CAP90_VARIANT:
            record["variant"] = self.variant
        return record


def _source_file(project_path, source):
    if (
        type(project_path) is not str
        or not project_path.endswith(".py")
        or type(source) is not bytes
        or not source
        or len(source) > MAXIMUM_SOURCE_FILE_BYTES
    ):
        _error("six-universe projected source file exceeded its bound")
    _audit_source(project_path, source)
    return SixUniverseOrderQcSourceFile(
        SOURCE_FILE_SCHEMA,
        project_path,
        len(source),
        hashlib.sha256(source).hexdigest(),
        source,
    )


def _cap90_qc_runtime_source(source):
    """Render the reviewed runtime's exact AST within QC's file limit.

    This transformation is exclusive to the cap-90 exploratory projection.
    It cannot change statements, expressions, literals, or their order: both
    parsed syntax trees must be structurally identical before upload.
    """

    if type(source) is not bytes:
        _error("six-universe cap-90 runtime source is not bytes")
    try:
        original = source.decode("ascii")
        original_tree = ast.parse(original)
        normalized = ast.unparse(original_tree) + "\n"
        normalized_source = normalized.encode("ascii")
        normalized_tree = ast.parse(normalized)
    except (SyntaxError, UnicodeError, RecursionError, ValueError) as exc:
        raise AcceptedRiskSixUniverseOrderQcProjectionError(
            "six-universe cap-90 runtime AST normalization failed"
        ) from exc
    if ast.dump(original_tree, include_attributes=False) != ast.dump(
        normalized_tree, include_attributes=False
    ):
        _error("six-universe cap-90 runtime AST changed during normalization")
    if len(normalized) > MAXIMUM_QC_SOURCE_CHARACTERS:
        _error("six-universe cap-90 runtime exceeded QC's source limit")
    return normalized_source


def _main_source(*, activation, profile, variant):
    tickers = _gate_tickers()
    variant_line = (
        "" if variant == "r177" else f"            variant={variant!r},\n"
    )
    reflected = '''from System import Convert as _Arv2DotNetConvert, Enum as _Arv2DotNetEnum


def _arv2_reflected_order_status(enum_type):
    refusal = "QC OrderStatus reflected map changed"
    try:
        names = tuple(_Arv2DotNetEnum.GetNames(enum_type))
        values = tuple(_Arv2DotNetEnum.GetValues(enum_type))
        numbers = tuple(_Arv2DotNetConvert.ToInt32(value) for value in values)
        reflected_type = values[0].GetType()
        same_type = all(value.GetType() == reflected_type for value in values)
    except Exception as exc:
        raise RuntimeError(refusal) from exc
    expected = (
        ("New", 0), ("Submitted", 1), ("PartiallyFilled", 2),
        ("Filled", 3), ("Canceled", 5), ("None", 6), ("Invalid", 7),
        ("CancelPending", 8), ("UpdateSubmitted", 9),
    )
    if (
        len(names) != len(expected)
        or len(values) != len(expected)
        or any(type(name) is not str for name in names)
        or any(type(number) is not int for number in numbers)
        or tuple(zip(names, numbers)) != expected
        or not same_type
        or any(type(value) is not type(values[0]) for value in values)
        or any(
            value == prior
            for index, value in enumerate(values)
            for prior in values[:index]
        )
    ):
        raise RuntimeError(refusal)

    class ReflectedOrderStatus:
        NEW, SUBMITTED, PARTIALLY_FILLED, FILLED, CANCELED, NONE, INVALID, CANCEL_PENDING, UPDATE_SUBMITTED = values

    return ReflectedOrderStatus


'''
    source = f'''from AlgorithmImports import *
from decimal import Decimal
{reflected}from accepted_risk_order_level_core import MODELED_FEE_RATE_PER_SIDE
from accepted_risk_six_universe_order_qc_runtime import (
    AcceptedRiskSixUniverseOrderQcDriver,
    STARTING_CASH,
)


class Arv2TenBpsFeeModel(FeeModel):
    def get_order_fee(self, parameters):
        price = Decimal(str(parameters.security.open))
        quantity = abs(Decimal(str(parameters.order.absolute_quantity)))
        if not price.is_finite() or price <= 0 or not quantity.is_finite():
            raise RuntimeError("ARV2 fee input is invalid")
        return OrderFee(CashAmount(
            price * quantity * MODELED_FEE_RATE_PER_SIDE,
            "USD",
        ))


class ARV2SixUniverseOrderAlgorithm(QCAlgorithm):
    def initialize(self):
        self.set_time_zone("America/New_York")
        self.settings.daily_precise_end_time = True
        self.settings.seed_initial_prices = True
        self.set_start_date({ALGORITHM_START[0]}, {ALGORITHM_START[1]}, {ALGORITHM_START[2]})
        self.set_end_date({ALGORITHM_END[0]}, {ALGORITHM_END[1]}, {ALGORITHM_END[2]})
        self.set_cash(STARTING_CASH)
        self.universe_settings.asynchronous = False
        self.universe_settings.resolution = Resolution.DAILY
        self.universe_settings.data_normalization_mode = DataNormalizationMode.RAW
        self._arv2_etf_symbols = {{}}
        for ticker in {tickers!r}:
            self._arv2_etf_symbols[ticker] = self.add_equity(
                ticker,
                Resolution.MINUTE,
                fill_forward=False,
                leverage=1,
                extended_market_hours=False,
                data_normalization_mode=DataNormalizationMode.RAW,
            ).symbol
        self.set_benchmark(self._arv2_etf_symbols["SPY"])
        self._arv2_fundamental_universe = self.add_universe(
            self._arv2_accept_fundamentals
        )
        self._arv2_constituent_universes = {{}}
        for ticker in {tickers!r}:
            callback = lambda constituents, ticker=ticker: self._arv2_accept_constituents(ticker, constituents)
            self._arv2_constituent_universes[ticker] = self.add_universe(
                self.universe.etf(
                    self._arv2_etf_symbols[ticker],
                    self.universe_settings,
                    callback,
                )
            )
        reflected_status = _arv2_reflected_order_status(OrderStatus)
        self._arv2_driver = AcceptedRiskSixUniverseOrderQcDriver(
            self,
            activation_manifest_key={activation.object_store_key!r},
            activation_manifest_sha256={activation.content_sha256!r},
            activation_manifest_byte_count={activation.byte_count},
            benchmark_symbol=self._arv2_etf_symbols["SPY"],
            etf_symbols=self._arv2_etf_symbols,
            role={profile['role']!r},
{variant_line}            fundamental_universe=self._arv2_fundamental_universe,
            constituent_universes=self._arv2_constituent_universes,
            trade_bar_type=TradeBar,
            minute_resolution=Resolution.MINUTE,
            daily_resolution=Resolution.DAILY,
            raw_normalization=DataNormalizationMode.RAW,
            fee_model_factory=lambda: Arv2TenBpsFeeModel(),
            slippage_model_factory=lambda: NullSlippageModel(),
            order_status_enum=reflected_status,
            order_status_to_int=_Arv2DotNetConvert.ToInt32,
            split_occurred_type=SplitType.SPLIT_OCCURRED,
        )
        self._arv2_driver.initialize()
        benchmark = self._arv2_etf_symbols["SPY"]
        self.schedule.on(
            self.date_rules.every_day(benchmark),
            self.time_rules.after_market_close(benchmark, 0),
            self._arv2_driver.on_after_close,
        )
        self.schedule.on(
            self.date_rules.every_day(benchmark),
            self.time_rules.before_market_open(benchmark, 10),
            self._arv2_driver.on_before_open,
        )

    def _arv2_accept_fundamentals(self, fundamentals):
        if not hasattr(self, "_arv2_driver"):
            return []
        return self._arv2_driver.accept_fundamentals(fundamentals)

    def _arv2_accept_constituents(self, ticker, constituents):
        if not hasattr(self, "_arv2_driver"):
            return []
        return self._arv2_driver.accept_constituents(ticker, constituents)

    def on_data(self, data):
        self._arv2_driver.on_data(data)

    def on_securities_changed(self, changes):
        if hasattr(self, "_arv2_driver"):
            self._arv2_driver.on_securities_changed(changes)

    def on_order_event(self, event):
        self._arv2_driver.on_order_event(event)

    def on_splits(self, splits):
        self._arv2_driver.on_splits(splits)

    def on_end_of_algorithm(self):
        self._arv2_driver.on_end_of_algorithm()
'''
    return source.encode("ascii")


def _gate_tickers():
    # Local import closure is already explicit; keep order identical to the
    # frozen gate rather than sorting it after the fact.
    from . import accepted_risk_six_universe_gate as gate

    return tuple(gate.UNIVERSE_IDS)


def build_accepted_risk_six_universe_order_qc_projection(
    delta_package,
    *,
    role,
    variant="r177",
):
    if (
        type(variant) is not str
        or variant not in ("r177", _runtime.CAP90_VARIANT)
    ):
        _error("six-universe order projection variant is not frozen")
    if type(delta_package) is not _delta.AcceptedRiskDeltaOrderPackage:
        _error("six-universe order projection requires the exact delta package")
    if (
        delta_package.package.package_id != _delta.EXPECTED_DELTA_PACKAGE_ID
        or delta_package.package.package_sha256
        != _delta.EXPECTED_DELTA_PACKAGE_SHA256
        or delta_package.lineage_sha256
        != _delta.EXPECTED_DELTA_LINEAGE_SHA256
    ):
        _error("six-universe order delta package identity changed")
    package = _package.require_accepted_risk_preliminary_package(
        delta_package.package
    )
    try:
        profile = _runtime.require_six_universe_order_profile(
            role, variant=variant
        )
    except _runtime.AcceptedRiskSixUniverseOrderQcRuntimeError as exc:
        raise AcceptedRiskSixUniverseOrderQcProjectionError(str(exc)) from exc
    activation = package.upload_objects[-1]
    if (
        activation.role != "activation_manifest"
        or activation.activation_manifest is not True
        or not activation.object_store_key.endswith("/transport-manifest.json")
    ):
        _error("six-universe order activation descriptor changed")
    root = Path(__file__).resolve().parent
    files = []
    for project_path in _SOURCE_PATHS:
        try:
            source = (root / project_path).read_bytes()
        except OSError as exc:
            raise AcceptedRiskSixUniverseOrderQcProjectionError(
                "six-universe projected source is unavailable"
            ) from exc
        if (
            variant == _runtime.CAP90_VARIANT
            and project_path == "accepted_risk_six_universe_order_qc_runtime.py"
        ):
            source = _cap90_qc_runtime_source(source)
        files.append(_source_file(project_path, source))
    files.append(
        _source_file(
            MAIN_PROJECT_PATH,
            _main_source(
                activation=activation,
                profile=profile,
                variant=variant,
            ),
        )
    )
    files.sort(key=lambda item: item.project_path)
    if variant == _runtime.CAP90_VARIANT and any(
        item.byte_count > MAXIMUM_QC_SOURCE_CHARACTERS for item in files
    ):
        _error("six-universe cap-90 source exceeded QC's file limit")
    total = sum(item.byte_count for item in files)
    if total + MINIMUM_REVIEW_MARGIN_BYTES > MAXIMUM_TOTAL_SOURCE_BYTES:
        _error("six-universe projected source set exceeded its reviewed bound")
    projection_schema = (
        PROJECTION_SCHEMA if variant == "r177" else CAP90_PROJECTION_SCHEMA
    )
    semantic = {
        "schema": projection_schema,
        "role": role,
        "profile_id": profile["profile_id"],
        "profile_sha256": profile["profile_sha256"],
        "package_id": package.package_id,
        "package_sha256": package.package_sha256,
        "package_lineage_sha256": delta_package.lineage_sha256,
        "activation_manifest_key": activation.object_store_key,
        "activation_manifest_sha256": activation.content_sha256,
        "activation_manifest_byte_count": activation.byte_count,
        "source_files": [item.to_record() for item in files],
        "total_source_byte_count": total,
        "preliminary": True,
        "formal": False,
        "backtest_only": True,
        "simulated_order_submission": True,
        "market_on_open_orders_only": True,
        "live_orders": False,
        "paper_orders": False,
        "funded_orders": False,
        "deployment": False,
        "trading": False,
    }
    if variant == _runtime.CAP90_VARIANT:
        semantic["variant"] = variant
    digest = hashlib.sha256(_canonical(semantic)).hexdigest()
    value = AcceptedRiskSixUniverseOrderQcProjection(
        projection_schema,
        "arv2-six-universe-order-qc-projection-" + digest[:24],
        digest,
        role,
        variant,
        profile["profile_id"],
        profile["profile_sha256"],
        package.package_id,
        package.package_sha256,
        delta_package.lineage_sha256,
        activation.object_store_key,
        activation.content_sha256,
        activation.byte_count,
        tuple(files),
        total,
        True,
        False,
        True,
        True,
        True,
        False,
        False,
        False,
        False,
        False,
    )
    if value.to_record()["projection_sha256"] != digest:
        _error("six-universe order projection did not self-authenticate")
    return value


__all__ = (
    "AcceptedRiskSixUniverseOrderQcProjection",
    "AcceptedRiskSixUniverseOrderQcProjectionError",
    "ALGORITHM_END",
    "ALGORITHM_START",
    "CAP90_PROJECTION_SCHEMA",
    "MAIN_PROJECT_PATH",
    "MAXIMUM_QC_SOURCE_CHARACTERS",
    "MAXIMUM_SOURCE_FILE_BYTES",
    "MAXIMUM_TOTAL_SOURCE_BYTES",
    "MINIMUM_REVIEW_MARGIN_BYTES",
    "PROJECTION_SCHEMA",
    "SOURCE_FILE_SCHEMA",
    "SixUniverseOrderQcSourceFile",
    "build_accepted_risk_six_universe_order_qc_projection",
)
