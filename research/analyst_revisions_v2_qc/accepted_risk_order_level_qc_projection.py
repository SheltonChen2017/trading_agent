"""Exact, backtest-only QC source projection for QQQ order-level runs.

The projected runtime may submit simulated ``MarketOnOpenOrder`` requests
inside a QuantConnect backtest.  The source firewall rejects every other
order family, deployment and brokerage capabilities, live mode other than the
runtime's read-only refusal check, dynamic code loading, network/process I/O,
and Object Store writes.  This module only assembles and authenticates source;
it performs no QuantConnect, provider, credential, upload, launch, or result
I/O.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import re
from pathlib import Path

from research.analyst_revisions_v2.canonical import canonical_json_bytes

from . import accepted_risk_delta_order_package as delta_package_builder
from . import accepted_risk_preliminary_package as package_builder
from . import accepted_risk_qqq_order_level_qc_runtime as runtime_builder


class AcceptedRiskOrderLevelQcProjectionError(ValueError):
    """The input lineage, source closure, or capability boundary changed."""


PROJECTION_SCHEMA = "arv2-order-level-qc-source-projection-v1"
SOURCE_SCHEMA = "arv2-order-level-qc-source-file-v1"
MAIN_PROJECT_PATH = "main.py"
RUNTIME_PROJECT_PATH = "accepted_risk_qqq_order_level_qc_runtime.py"
MAX_SOURCE_FILE_BYTES = 64_000
# The execution-matched QQQ hurdle adds adjusted-open lineage and a second
# digested contextual path to the exact ten-file closure.  These caps
# retain at least one 4,096-byte review margin without admitting another file.
MAX_TOTAL_SOURCE_BYTES = 272_000

PROJECT_SOURCE_PATHS = (
    "accepted_risk_preliminary_rating_policy.py",
    "accepted_risk_preliminary_rating_evaluator.py",
    "accepted_risk_preliminary_qc_figi.py",
    "accepted_risk_market_cap_stock_portfolio_tilt.py",
    "accepted_risk_order_level_benchmark.py",
    "accepted_risk_order_level_core.py",
    "accepted_risk_order_level_input_runtime.py",
    "accepted_risk_sequential_r055_score.py",
    RUNTIME_PROJECT_PATH,
)

_FUTURE = re.compile(rb"(?m)^\s*from\s+__future__\s+import\s+")
_ALLOWED_IMPORT_MODULES = {
    "AlgorithmImports",
    "accepted_risk_order_level_core",
    "accepted_risk_order_level_benchmark",
    "accepted_risk_market_cap_stock_portfolio_tilt",
    "accepted_risk_order_level_input_runtime",
    "accepted_risk_preliminary_qc_figi",
    "accepted_risk_preliminary_rating_evaluator",
    "accepted_risk_preliminary_rating_policy",
    "accepted_risk_qqq_order_level_qc_runtime",
    "accepted_risk_sequential_r055_score",
    "collections",
    "collections.abc",
    "dataclasses",
    "datetime",
    "decimal",
    "enum",
    "fractions",
    "gzip",
    "hashlib",
    "io",
    "itertools",
    "json",
    "math",
    "re",
    "research.analyst_revisions_v2_qc",
    "time",
    "types",
    "typing",
    "zoneinfo",
}
_FORBIDDEN_IMPORT_ROOTS = {
    "builtins",
    "clr",
    "http",
    "importlib",
    "os",
    "pathlib",
    "requests",
    "socket",
    "subprocess",
    "urllib",
    "webbrowser",
    "websocket",
}
_FORBIDDEN_DYNAMIC_CALLS = {
    "compile",
    "eval",
    "exec",
    "getattr",
    "globals",
    "import",
    "locals",
    "setattr",
    "vars",
}
_FORBIDDEN_ORDER_CALLS = {
    "buy",
    "calculateorderquantity",
    "cancel",
    "cancelopenorders",
    "cancelorder",
    "comboleglimitorder",
    "combolimitorder",
    "combomarketorder",
    "exerciseoption",
    "limitiftouchedorder",
    "limitorder",
    "liquidate",
    "marketoncloseorder",
    "marketorder",
    "order",
    "sell",
    "setholdings",
    "stoplimitorder",
    "stopmarketorder",
    "submitorderrequest",
    "trailingstoporder",
    "transactions",
    "updateorderfields",
}
_FORBIDDEN_OPERATION_CALLS = {
    "debug",
    "deploy",
    "download",
    "error",
    "log",
    "quit",
    "setalpha",
    "setbrokeragemodel",
    "setexecution",
    "setportfolioconstruction",
    "setriskmanagement",
    "setuniverseselection",
}
_FORBIDDEN_OBJECT_STORE_WRITES = {
    "clear",
    "delete",
    "getfilepath",
    "save",
    "savebytes",
    "savestring",
}
_FORBIDDEN_CAPABILITY_NAMES = {
    "broker",
    "brokerage",
    "brokeragemodel",
    "deploy",
    "deployment",
    "notify",
    "notifications",
    "paper",
    "papertrade",
    "papertrading",
}


def _normalized(value: str) -> str:
    return value.casefold().replace("_", "")


def _is_self_algorithm(value: ast.AST) -> bool:
    return (
        isinstance(value, ast.Attribute)
        and isinstance(value.value, ast.Name)
        and value.value.id == "self"
        and value.attr == "_algorithm"
    )


def _approved_market_on_open_call(node: ast.Attribute, project_path: str) -> bool:
    return (
        project_path == RUNTIME_PROJECT_PATH
        and _normalized(node.attr) == "marketonopenorder"
        and _is_self_algorithm(node.value)
    )


def _approved_live_mode_read(node: ast.Attribute, project_path: str) -> bool:
    return (
        project_path == RUNTIME_PROJECT_PATH
        and _normalized(node.attr) == "livemode"
        and isinstance(node.ctx, ast.Load)
        and _is_self_algorithm(node.value)
    )


def _approved_fee_order_read(node: ast.Attribute, project_path: str) -> bool:
    return (
        project_path == MAIN_PROJECT_PATH
        and _normalized(node.attr) == "order"
        and isinstance(node.ctx, ast.Load)
        and isinstance(node.value, ast.Name)
        and node.value.id == "parameters"
    )


def _audit_cloud_capabilities(text: str, project_path: str) -> None:
    """Reject every cloud capability except one direct simulated MOO call."""

    try:
        tree = ast.parse(text, filename=project_path, feature_version=(3, 11))
    except SyntaxError as exc:
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level QC source is not valid Python AST"
        ) from exc
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    locally_defined = {
        _normalized(node.name)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = {item.name for item in node.names}
            roots = {item.split(".", 1)[0] for item in modules}
            if roots & _FORBIDDEN_IMPORT_ROOTS or not modules.issubset(
                _ALLOWED_IMPORT_MODULES
            ):
                raise AcceptedRiskOrderLevelQcProjectionError(
                    "order-level QC source imports a forbidden capability"
                )
            continue
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".", 1)[0]
            imported = {_normalized(item.name) for item in node.names}
            if (
                root in _FORBIDDEN_IMPORT_ROOTS
                or module not in _ALLOWED_IMPORT_MODULES
                or imported
                & (
                    _FORBIDDEN_DYNAMIC_CALLS
                    | _FORBIDDEN_ORDER_CALLS
                    | _FORBIDDEN_OPERATION_CALLS
                    | _FORBIDDEN_OBJECT_STORE_WRITES
                    | _FORBIDDEN_CAPABILITY_NAMES
                    | {"marketonopenorder", "livemode"}
                )
            ):
                raise AcceptedRiskOrderLevelQcProjectionError(
                    "order-level QC source imports a forbidden capability"
                )
            continue
        if isinstance(node, ast.Name):
            name = _normalized(node.id)
            if name in _FORBIDDEN_DYNAMIC_CALLS:
                raise AcceptedRiskOrderLevelQcProjectionError(
                    "order-level QC source references a dynamic capability"
                )
            if name in _FORBIDDEN_CAPABILITY_NAMES or name == "marketonopenorder":
                raise AcceptedRiskOrderLevelQcProjectionError(
                    "order-level QC source references an unscoped operational capability"
                )
            continue
        if isinstance(node, ast.Attribute):
            name = _normalized(node.attr)
            if name == "marketonopenorder":
                parent = parents.get(node)
                if (
                    not _approved_market_on_open_call(node, project_path)
                    or not isinstance(parent, ast.Call)
                    or parent.func is not node
                ):
                    raise AcceptedRiskOrderLevelQcProjectionError(
                        "MarketOnOpenOrder is permitted only as the runtime's direct simulated call"
                    )
            elif name == "livemode":
                if not _approved_live_mode_read(node, project_path):
                    raise AcceptedRiskOrderLevelQcProjectionError(
                        "live mode is permitted only as the runtime's read-only refusal check"
                    )
            elif name == "order" and _approved_fee_order_read(
                node, project_path
            ):
                pass
            elif name in (
                _FORBIDDEN_ORDER_CALLS
                | _FORBIDDEN_OPERATION_CALLS
                | _FORBIDDEN_OBJECT_STORE_WRITES
                | _FORBIDDEN_CAPABILITY_NAMES
                | {"getattribute"}
            ):
                raise AcceptedRiskOrderLevelQcProjectionError(
                    "order-level QC source reaches a forbidden operational capability"
                )
            continue
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                name = _normalized(node.func.attr)
            elif isinstance(node.func, ast.Name):
                name = _normalized(node.func.id)
            else:
                name = None
            if name in _FORBIDDEN_DYNAMIC_CALLS and (
                isinstance(node.func, ast.Name) or name == "getattribute"
            ):
                raise AcceptedRiskOrderLevelQcProjectionError(
                    "order-level QC source calls a dynamic capability"
                )
            if name in _FORBIDDEN_ORDER_CALLS:
                raise AcceptedRiskOrderLevelQcProjectionError(
                    "order-level QC source calls a forbidden operational capability"
                )
            if name in (
                _FORBIDDEN_OPERATION_CALLS
                | _FORBIDDEN_OBJECT_STORE_WRITES
                | _FORBIDDEN_CAPABILITY_NAMES
            ) and not (
                isinstance(node.func, ast.Name)
                and (name in locally_defined or node.func.id.startswith("_"))
            ):
                raise AcceptedRiskOrderLevelQcProjectionError(
                    "order-level QC source calls a forbidden operational capability"
                )


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level QC projection is not canonical ASCII JSON"
        ) from exc


@dataclasses.dataclass(frozen=True, slots=True)
class OrderLevelQcSourceFile:
    schema: str
    project_path: str
    byte_count: int
    content_sha256: str
    source_bytes: bytes = dataclasses.field(repr=False)

    def to_record(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "project_path": self.project_path,
            "byte_count": self.byte_count,
            "content_sha256": self.content_sha256,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class AcceptedRiskOrderLevelQcProjection:
    schema: str
    projection_id: str
    projection_sha256: str
    package_id: str
    package_sha256: str
    package_lineage_sha256: str
    activation_manifest_key: str
    activation_manifest_sha256: str
    activation_manifest_byte_count: int
    profile_id: str
    profile_sha256: str
    source_files: tuple[OrderLevelQcSourceFile, ...]
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
    broker_credentials: bool
    trading: bool

    def to_record(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "projection_id": self.projection_id,
            "projection_sha256": self.projection_sha256,
            "package_id": self.package_id,
            "package_sha256": self.package_sha256,
            "package_lineage_sha256": self.package_lineage_sha256,
            "activation_manifest_key": self.activation_manifest_key,
            "activation_manifest_sha256": self.activation_manifest_sha256,
            "activation_manifest_byte_count": self.activation_manifest_byte_count,
            "profile_id": self.profile_id,
            "profile_sha256": self.profile_sha256,
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
            "broker_credentials": self.broker_credentials,
            "trading": self.trading,
        }


def _validate_source(project_path: str, source: bytes) -> OrderLevelQcSourceFile:
    if (
        type(project_path) is not str
        or "/" in project_path
        or not project_path.endswith(".py")
        or type(source) is not bytes
        or not source
        or len(source) > MAX_SOURCE_FILE_BYTES
        or b"\r" in source
        or b"\x00" in source
        or _FUTURE.search(source) is not None
    ):
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level QC source violates size, path, or future-import guard"
        )
    try:
        text = source.decode("ascii")
    except UnicodeDecodeError as exc:
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level QC source is not exact ASCII"
        ) from exc
    _audit_cloud_capabilities(text, project_path)
    try:
        compile(text, project_path, "exec")
        compile("QC_PRELUDE_SENTINEL = True\n" + text, project_path, "exec")
        compile("from AlgorithmImports import *\n" + text, project_path, "exec")
    except (SyntaxError, ValueError) as exc:
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level QC source does not compile raw and after QC prelude"
        ) from exc
    return OrderLevelQcSourceFile(
        SOURCE_SCHEMA,
        project_path,
        len(source),
        hashlib.sha256(source).hexdigest(),
        source,
    )


def _require_delta_package(value):
    if type(value) is not delta_package_builder.AcceptedRiskDeltaOrderPackage:
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level input package type changed"
        )
    package = package_builder.require_accepted_risk_preliminary_package(
        value.package
    )
    if (
        value.lineage_sha256
        != hashlib.sha256(canonical_json_bytes(value.lineage)).hexdigest()
        or package.source_disposition_sha256 != value.lineage_sha256
        or value.decision_cutoff_session
        != delta_package_builder.DELTA_DECISION_END_SESSION
        or value.final_execution_session
        != delta_package_builder.FINAL_EXECUTION_SESSION
        or value.current_snapshot_identity_only is not True
        or value.refreshed_security_master is not False
        or any(
            getattr(value, field) is not False
            for field in (
                "provider_access",
                "quantconnect_access",
                "outcome_access",
                "orders",
                "trading",
            )
        )
    ):
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level input package lineage or disclosure changed"
        )
    return value, package


def _main_source(
    *,
    activation_manifest_key: str,
    activation_manifest_sha256: str,
    activation_manifest_byte_count: int,
    profile: dict[str, object],
) -> bytes:
    """Render the thin QC entry after the runtime interface is authenticated."""

    try:
        start = tuple(
            int(part) for part in profile["evaluation_start_session"].split("-")
        )
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level profile start session changed"
        ) from exc
    if (
        len(start) != 3
        or profile.get("profile_id") not in runtime_builder.PROFILE_IDS
        or profile.get("decision_cutoff_session")
        != delta_package_builder.DELTA_DECISION_END_SESSION
        or profile.get("final_execution_session")
        != delta_package_builder.FINAL_EXECUTION_SESSION
        or profile.get("backtest_only") is not True
        or profile.get("simulated_order_submission") is not True
        or any(
            profile.get(field) is not False
            for field in (
                "live_orders",
                "paper_orders",
                "funded_orders",
                "deployment",
                "broker_credentials",
                "trading",
            )
        )
    ):
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level profile capability or date binding changed"
        )
    end = tuple(
        int(part)
        for part in delta_package_builder.FINAL_EXECUTION_SESSION.split("-")
    )
    source = f'''from AlgorithmImports import *
from decimal import Decimal
from accepted_risk_qqq_order_level_qc_runtime import (
    AcceptedRiskQqqOrderLevelQcRuntime,
    STARTING_CASH,
)
from accepted_risk_order_level_core import MODELED_FEE_RATE_PER_SIDE


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


class ARV2QqqOrderLevelAlgorithm(QCAlgorithm):
    def initialize(self):
        self.set_time_zone("America/New_York")
        self.settings.daily_precise_end_time = True
        self.set_start_date({start[0]}, {start[1]}, {start[2]})
        self.set_end_date({end[0]}, {end[1]}, {end[2]})
        self.set_cash(STARTING_CASH)
        self.universe_settings.asynchronous = False
        self.universe_settings.resolution = Resolution.MINUTE
        self.universe_settings.data_normalization_mode = DataNormalizationMode.RAW
        authority_benchmark = self.add_equity(
            "SPY",
            Resolution.DAILY,
            fill_forward=False,
            leverage=1,
            extended_market_hours=False,
            data_normalization_mode=DataNormalizationMode.TOTAL_RETURN,
        ).symbol
        qqq_benchmark = self.add_equity(
            "QQQ",
            Resolution.MINUTE,
            fill_forward=False,
            leverage=1,
            extended_market_hours=False,
            data_normalization_mode=DataNormalizationMode.TOTAL_RETURN,
        ).symbol
        self.set_benchmark(qqq_benchmark)
        fundamental_universe = self.AddUniverse(lambda fundamentals: [])
        qqq_constituent_universe = self.add_universe(
            self.universe.etf(
                qqq_benchmark,
                self.universe_settings,
                self._arv2_accept_qqq_constituents,
            )
        )
        self._arv2_driver = AcceptedRiskQqqOrderLevelQcRuntime(
            self,
            activation_manifest_key={activation_manifest_key!r},
            activation_manifest_sha256={activation_manifest_sha256!r},
            activation_manifest_byte_count={activation_manifest_byte_count},
            profile_id={profile['profile_id']!r},
            authority_benchmark_symbol=authority_benchmark,
            qqq_benchmark_symbol=qqq_benchmark,
            fundamental_universe=fundamental_universe,
            qqq_constituent_universe=qqq_constituent_universe,
            minute_resolution=Resolution.MINUTE,
            raw_normalization=DataNormalizationMode.RAW,
            trade_bar_type=TradeBar,
            daily_resolution=Resolution.DAILY,
            total_return_normalization=DataNormalizationMode.TOTAL_RETURN,
            fee_model_factory=lambda: Arv2TenBpsFeeModel(),
            slippage_model_factory=lambda: NullSlippageModel(),
        )
        self._arv2_driver.initialize()
        self.schedule.on(
            self.date_rules.every_day(qqq_benchmark),
            self.time_rules.after_market_close(qqq_benchmark, 0),
            self._arv2_driver.on_after_close,
        )

    def _arv2_accept_qqq_constituents(self, constituents):
        if not hasattr(self, "_arv2_driver"):
            return []
        return self._arv2_driver.accept_qqq_constituents(constituents)

    def on_data(self, data):
        self._arv2_driver.on_data(data)

    def on_securities_changed(self, changes):
        self._arv2_driver.on_securities_changed(changes)

    def on_order_event(self, event):
        self._arv2_driver.on_order_event(event)

    def on_end_of_algorithm(self):
        self._arv2_driver.on_end_of_algorithm()
'''
    return source.encode("ascii")


def build_accepted_risk_order_level_qc_projection(
    delta_package,
    *,
    profile_id: str,
) -> AcceptedRiskOrderLevelQcProjection:
    delta_package, package = _require_delta_package(delta_package)
    profile = runtime_builder.require_qqq_order_level_profile(profile_id)
    activation = package.upload_objects[-1]
    if (
        activation.role != "activation_manifest"
        or activation.activation_manifest is not True
        or not activation.object_store_key.endswith("/transport-manifest.json")
    ):
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level package activation descriptor changed"
        )
    root = Path(__file__).resolve().parent
    files = []
    for project_path in PROJECT_SOURCE_PATHS:
        try:
            source = (root / project_path).read_bytes()
        except OSError as exc:
            raise AcceptedRiskOrderLevelQcProjectionError(
                "order-level QC source is unavailable"
            ) from exc
        files.append(_validate_source(project_path, source))
    files.append(
        _validate_source(
            MAIN_PROJECT_PATH,
            _main_source(
                activation_manifest_key=activation.object_store_key,
                activation_manifest_sha256=activation.content_sha256,
                activation_manifest_byte_count=activation.byte_count,
                profile=profile,
            ),
        )
    )
    files.sort(key=lambda item: item.project_path)
    total = sum(item.byte_count for item in files)
    if total > MAX_TOTAL_SOURCE_BYTES:
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level QC source set exceeds reviewed total size"
        )
    semantic = {
        "schema": PROJECTION_SCHEMA,
        "projection_id": None,
        "projection_sha256": None,
        "package_id": package.package_id,
        "package_sha256": package.package_sha256,
        "package_lineage_sha256": delta_package.lineage_sha256,
        "activation_manifest_key": activation.object_store_key,
        "activation_manifest_sha256": activation.content_sha256,
        "activation_manifest_byte_count": activation.byte_count,
        "profile_id": profile["profile_id"],
        "profile_sha256": profile["profile_sha256"],
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
        "broker_credentials": False,
        "trading": False,
    }
    digest = hashlib.sha256(_canonical(semantic)).hexdigest()
    value = AcceptedRiskOrderLevelQcProjection(
        PROJECTION_SCHEMA,
        "arv2-order-level-qc-projection-" + digest[:24],
        digest,
        package.package_id,
        package.package_sha256,
        delta_package.lineage_sha256,
        activation.object_store_key,
        activation.content_sha256,
        activation.byte_count,
        profile["profile_id"],
        profile["profile_sha256"],
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
        False,
    )
    package_builder.require_accepted_risk_preliminary_package(package)
    return require_accepted_risk_order_level_qc_projection(value)


def require_accepted_risk_order_level_qc_projection(
    value: AcceptedRiskOrderLevelQcProjection,
) -> AcceptedRiskOrderLevelQcProjection:
    if type(value) is not AcceptedRiskOrderLevelQcProjection:
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level QC projection type changed"
        )
    profile = runtime_builder.require_qqq_order_level_profile(value.profile_id)
    observed_paths = tuple(item.project_path for item in value.source_files)
    if (
        value.schema != PROJECTION_SCHEMA
        or type(value.source_files) is not tuple
        or observed_paths != tuple(sorted((*PROJECT_SOURCE_PATHS, MAIN_PROJECT_PATH)))
        or value.profile_sha256 != profile["profile_sha256"]
        or value.total_source_byte_count
        != sum(item.byte_count for item in value.source_files)
        or value.total_source_byte_count > MAX_TOTAL_SOURCE_BYTES
        or value.preliminary is not True
        or value.formal is not False
        or value.backtest_only is not True
        or value.simulated_order_submission is not True
        or value.market_on_open_orders_only is not True
        or any(
            getattr(value, field) is not False
            for field in (
                "live_orders",
                "paper_orders",
                "funded_orders",
                "deployment",
                "broker_credentials",
                "trading",
            )
        )
    ):
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level QC projection disclosure or inventory changed"
        )
    rebuilt = tuple(
        _validate_source(item.project_path, item.source_bytes)
        for item in value.source_files
    )
    if rebuilt != value.source_files:
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level QC projected source identity changed"
        )
    main_source = next(
        item.source_bytes
        for item in value.source_files
        if item.project_path == MAIN_PROJECT_PATH
    )
    if main_source != _main_source(
        activation_manifest_key=value.activation_manifest_key,
        activation_manifest_sha256=value.activation_manifest_sha256,
        activation_manifest_byte_count=value.activation_manifest_byte_count,
        profile=profile,
    ):
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level QC main source diverged from its activation or profile"
        )
    semantic = value.to_record()
    semantic["projection_id"] = None
    semantic["projection_sha256"] = None
    digest = hashlib.sha256(_canonical(semantic)).hexdigest()
    if (
        value.projection_sha256 != digest
        or value.projection_id
        != "arv2-order-level-qc-projection-" + digest[:24]
    ):
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level QC projection identity changed"
        )
    return value


def iter_accepted_risk_order_level_qc_sources(value):
    projection = require_accepted_risk_order_level_qc_projection(value)
    for item in projection.source_files:
        yield item.project_path, item.source_bytes


__all__ = (
    "AcceptedRiskOrderLevelQcProjection",
    "AcceptedRiskOrderLevelQcProjectionError",
    "OrderLevelQcSourceFile",
    "build_accepted_risk_order_level_qc_projection",
    "iter_accepted_risk_order_level_qc_sources",
    "require_accepted_risk_order_level_qc_projection",
)
