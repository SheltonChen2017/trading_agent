"""Host-side exact source projection for one preliminary ARV2 QC project."""

from __future__ import annotations

import dataclasses
import ast
import hashlib
import json
import re
from pathlib import Path

from . import accepted_risk_preliminary_package as package_builder
from . import accepted_risk_preliminary_qc_runtime as runtime_builder
from . import accepted_risk_regime_rating_evaluator as regime_evaluator
from . import accepted_risk_etf_baseline_evaluator as etf_evaluator
from . import accepted_risk_stock_portfolio_evaluator as stock_portfolio_evaluator


class AcceptedRiskPreliminaryQcProjectionError(ValueError):
    """The compact QC source set or its bound input activation is inexact."""


PROJECTION_SCHEMA = "arv2-accepted-risk-preliminary-qc-source-projection-v2"
SOURCE_SCHEMA = "arv2-accepted-risk-preliminary-qc-source-file-v1"
MAX_SOURCE_FILE_BYTES = 60_000
MAX_TOTAL_SOURCE_BYTES = 260_000
ALGORITHM_START = (2026, 4, 1)
ALGORITHM_END = (2026, 9, 11)
PROJECT_SOURCE_PATHS = (
    "accepted_risk_preliminary_rating_policy.py",
    "accepted_risk_preliminary_rating_evaluator.py",
    "accepted_risk_regime_rating_evaluator.py",
    "accepted_risk_preliminary_qc_figi.py",
    "accepted_risk_preliminary_qc_runtime.py",
)
ETF_PROJECT_SOURCE_PATHS = (
    "accepted_risk_preliminary_rating_policy.py",
    "accepted_risk_preliminary_rating_evaluator.py",
    "accepted_risk_regime_rating_evaluator.py",
    "accepted_risk_preliminary_qc_figi.py",
    "accepted_risk_preliminary_qc_runtime.py",
    "accepted_risk_etf_baseline_evaluator.py",
    "accepted_risk_etf_baseline_qc_runtime.py",
)
STOCK_PORTFOLIO_PROJECT_SOURCE_PATHS = (
    *PROJECT_SOURCE_PATHS,
    "accepted_risk_stock_portfolio_evaluator.py",
)
STOCK_PORTFOLIO_PROFILE_ID = stock_portfolio_evaluator.PROFILE_ID
STOCK_PORTFOLIO_PROFILE_SHA256 = (
    stock_portfolio_evaluator.require_stock_portfolio_profile(
        STOCK_PORTFOLIO_PROFILE_ID
    )["profile_sha256"]
)
MAIN_PROJECT_PATH = "main.py"
_FUTURE = re.compile(rb"(?m)^\s*from\s+__future__\s+import\s+")
_FORBIDDEN_IMPORT_ROOTS = {
    "System",
    "builtins",
    "clr",
    "http",
    "importlib",
    "operator",
    "requests",
    "socket",
    "subprocess",
    "urllib",
    "webbrowser",
    "websocket",
}
_ALLOWED_IMPORT_MODULES = {
    "AlgorithmImports",
    "accepted_risk_preliminary_qc_figi",
    "accepted_risk_preliminary_qc_runtime",
    "accepted_risk_preliminary_rating_evaluator",
    "accepted_risk_preliminary_rating_policy",
    "accepted_risk_regime_rating_evaluator",
    "accepted_risk_stock_portfolio_evaluator",
    "accepted_risk_etf_baseline_evaluator",
    "accepted_risk_etf_baseline_qc_runtime",
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
    "json",
    "math",
    "re",
    "research.analyst_revisions_v2_qc",
    "time",
    "types",
    "typing",
}
_FORBIDDEN_DYNAMIC_CALLS = {
    "compile",
    "eval",
    "exec",
    "getattribute",
    "globals",
    "import",
    "locals",
    "setattr",
    "vars",
}
_ALLOWED_GETATTR_FIELDS = set()
_FORBIDDEN_NAMES = {
    "clr",
    "framework",
    "notify",
    "notifications",
    "system",
}
_FORBIDDEN_CALLS = {
    "buy",
    "calculateorderquantity",
    "comboleglimitorder",
    "combolimitorder",
    "combomarketorder",
    "debug",
    "deploy",
    "download",
    "error",
    "exerciseoption",
    "execl",
    "execle",
    "execlp",
    "execlpe",
    "execv",
    "execve",
    "execvp",
    "execvpe",
    "fork",
    "kill",
    "liquidate",
    "limitorder",
    "limitiftouchedorder",
    "log",
    "marketorder",
    "marketoncloseorder",
    "marketonopenorder",
    "popen",
    "order",
    "quit",
    "sell",
    "setbrokeragemodel",
    "setalpha",
    "setexecution",
    "setholdings",
    "setportfolioconstruction",
    "setriskmanagement",
    "setuniverseselection",
    "spawnl",
    "spawnle",
    "spawnlp",
    "spawnlpe",
    "spawnv",
    "spawnve",
    "spawnvp",
    "spawnvpe",
    "stoplimitorder",
    "stopmarketorder",
    "trailingstoporder",
    "system",
}
_FORBIDDEN_ATTRIBUTES = {
    "bases",
    "brokerage",
    "brokeragemodel",
    "class",
    "dict",
    "livemode",
    "notify",
    "notifications",
    "portfolio",
    "mro",
    "subclasses",
    "transactions",
}
_FORBIDDEN_OBJECT_STORE_WRITES = {
    "clear",
    "delete",
    "getfilepath",
    "save",
    "savebytes",
    "savestring",
}


def _normalized_capability_name(value: str) -> str:
    return value.casefold().replace("_", "")


def _audit_cloud_capabilities(text: str, project_path: str) -> None:
    try:
        tree = ast.parse(text, filename=project_path, feature_version=(3, 11))
    except SyntaxError as exc:
        raise AcceptedRiskPreliminaryQcProjectionError(
            "preliminary QC source is not valid Python AST"
        ) from exc
    locally_defined = {
        _normalized_capability_name(node.name)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    approved_getattr_references = {
        id(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and project_path == "accepted_risk_preliminary_rating_evaluator.py"
        and 2 <= len(node.args) <= 3
        and isinstance(node.args[1], ast.Constant)
        and type(node.args[1].value) is str
        and node.args[1].value in _ALLOWED_GETATTR_FIELDS
    }
    for node in ast.walk(tree):
        normalized_name = (
            _normalized_capability_name(node.id)
            if isinstance(node, ast.Name)
            else None
        )
        if (
            isinstance(node, ast.Name)
            and normalized_name in (_FORBIDDEN_DYNAMIC_CALLS | {"getattr"})
            and id(node) not in approved_getattr_references
        ):
            raise AcceptedRiskPreliminaryQcProjectionError(
                "preliminary QC source references a forbidden dynamic capability"
            )
        if (
            isinstance(node, ast.Name)
            and normalized_name in _FORBIDDEN_NAMES
        ):
            raise AcceptedRiskPreliminaryQcProjectionError(
                "preliminary QC source reaches a forbidden framework or notification capability"
            )
        if isinstance(node, ast.Import):
            modules = {item.name for item in node.names}
            roots = {item.split(".", 1)[0] for item in modules}
            if roots & _FORBIDDEN_IMPORT_ROOTS or not modules.issubset(
                _ALLOWED_IMPORT_MODULES
            ):
                raise AcceptedRiskPreliminaryQcProjectionError(
                    "preliminary QC source imports a forbidden network/process capability"
                )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".", 1)[0]
            imported_names = {
                _normalized_capability_name(item.name) for item in node.names
            }
            if (
                root in _FORBIDDEN_IMPORT_ROOTS
                or module not in _ALLOWED_IMPORT_MODULES
                or imported_names
                & (
                    _FORBIDDEN_CALLS
                    | _FORBIDDEN_DYNAMIC_CALLS
                    | _FORBIDDEN_OBJECT_STORE_WRITES
                    | _FORBIDDEN_ATTRIBUTES
                    | _FORBIDDEN_NAMES
                )
            ):
                raise AcceptedRiskPreliminaryQcProjectionError(
                    "preliminary QC source imports a forbidden network/process capability"
                )
        elif isinstance(node, ast.Attribute):
            name = _normalized_capability_name(node.attr)
            if name in (
                _FORBIDDEN_ATTRIBUTES
                | _FORBIDDEN_CALLS
                | _FORBIDDEN_OBJECT_STORE_WRITES
                | {"getattribute"}
            ):
                raise AcceptedRiskPreliminaryQcProjectionError(
                    "preliminary QC source reaches a forbidden trading/deployment capability"
                )
        elif isinstance(node, ast.Call):
            name = None
            if isinstance(node.func, ast.Attribute):
                name = _normalized_capability_name(node.func.attr)
            elif isinstance(node.func, ast.Name):
                name = _normalized_capability_name(node.func.id)
            if name in _FORBIDDEN_DYNAMIC_CALLS and (
                isinstance(node.func, ast.Name) or name == "getattribute"
            ):
                raise AcceptedRiskPreliminaryQcProjectionError(
                    "preliminary QC source calls a forbidden dynamic capability"
                )
            if name == "getattr":
                allowed_getattr = (
                    project_path == "accepted_risk_preliminary_rating_evaluator.py"
                    and 2 <= len(node.args) <= 3
                    and isinstance(node.args[1], ast.Constant)
                    and type(node.args[1].value) is str
                    and node.args[1].value in _ALLOWED_GETATTR_FIELDS
                )
                if not allowed_getattr:
                    raise AcceptedRiskPreliminaryQcProjectionError(
                        "preliminary QC source calls a forbidden dynamic capability"
                    )
            if name in _FORBIDDEN_CALLS and not (
                isinstance(node.func, ast.Name)
                and (
                    name in locally_defined
                    or node.func.id.startswith("_")
                )
            ):
                raise AcceptedRiskPreliminaryQcProjectionError(
                    "preliminary QC source calls a forbidden trading/network/log capability"
                )
            if name in _FORBIDDEN_OBJECT_STORE_WRITES:
                raise AcceptedRiskPreliminaryQcProjectionError(
                    "preliminary QC source calls a forbidden Object Store write capability"
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
        raise AcceptedRiskPreliminaryQcProjectionError(
            "preliminary QC projection is not canonical ASCII JSON"
        ) from exc


@dataclasses.dataclass(frozen=True, slots=True)
class PreliminaryQcSourceFile:
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
class AcceptedRiskPreliminaryQcProjection:
    schema: str
    projection_id: str
    projection_sha256: str
    package_id: str
    package_sha256: str
    activation_manifest_key: str
    activation_manifest_sha256: str
    activation_manifest_byte_count: int
    evaluation_profile_id: str | None
    evaluation_profile_sha256: str | None
    source_files: tuple[PreliminaryQcSourceFile, ...]
    total_source_byte_count: int
    train_work_units_per_slice: int
    maximum_train_slice_count: int
    preliminary: bool
    formal: bool
    outcome_result_transport: str
    orders: bool
    trading: bool

    def to_record(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "projection_id": self.projection_id,
            "projection_sha256": self.projection_sha256,
            "package_id": self.package_id,
            "package_sha256": self.package_sha256,
            "activation_manifest_key": self.activation_manifest_key,
            "activation_manifest_sha256": self.activation_manifest_sha256,
            "activation_manifest_byte_count": self.activation_manifest_byte_count,
            "evaluation_profile_id": self.evaluation_profile_id,
            "evaluation_profile_sha256": self.evaluation_profile_sha256,
            "source_files": [item.to_record() for item in self.source_files],
            "total_source_byte_count": self.total_source_byte_count,
            "train_work_units_per_slice": self.train_work_units_per_slice,
            "maximum_train_slice_count": self.maximum_train_slice_count,
            "preliminary": self.preliminary,
            "formal": self.formal,
            "outcome_result_transport": self.outcome_result_transport,
            "orders": self.orders,
            "trading": self.trading,
        }


def _main_source(
    *,
    activation_key: str,
    activation_sha256: str,
    activation_bytes: int,
    evaluation_profile_id: str | None,
) -> bytes:
    if evaluation_profile_id == etf_evaluator.PROFILE_ID:
        return _etf_main_source(
            activation_key=activation_key,
            activation_sha256=activation_sha256,
            activation_bytes=activation_bytes,
        )
    source = f'''from AlgorithmImports import *
from accepted_risk_preliminary_qc_runtime import (
    AcceptedRiskPreliminaryQcDriver,
    TRAIN_SLICE_SOFT_SECONDS,
    TRAIN_WORK_UNITS_PER_SLICE,
)


class ARV2AcceptedRiskPreliminaryAlgorithm(QCAlgorithm):
    def initialize(self):
        self.set_time_zone("America/New_York")
        self.settings.daily_precise_end_time = True
        self.set_start_date({ALGORITHM_START[0]}, {ALGORITHM_START[1]}, {ALGORITHM_START[2]})
        self.set_end_date({ALGORITHM_END[0]}, {ALGORITHM_END[1]}, {ALGORITHM_END[2]})
        benchmark = self.add_equity(
            "SPY",
            Resolution.DAILY,
            fill_forward=False,
            leverage=1,
            extended_market_hours=False,
            data_normalization_mode=DataNormalizationMode.TOTAL_RETURN,
        ).symbol
        self._arv2_driver = AcceptedRiskPreliminaryQcDriver(
            self,
            activation_manifest_key={activation_key!r},
            activation_manifest_sha256={activation_sha256!r},
            activation_manifest_byte_count={activation_bytes},
            benchmark_symbol=benchmark,
            trade_bar_type=TradeBar,
            daily_resolution=Resolution.DAILY,
            total_return_normalization=DataNormalizationMode.TOTAL_RETURN,
            evaluation_profile_id={evaluation_profile_id!r},
        )

    def on_data(self, _data):
        if not self._arv2_driver.completed:
            self._arv2_advance_training_slice()

    def _arv2_advance_training_slice(self):
        self._arv2_driver.advance_training_slice(
            maximum_work_units=TRAIN_WORK_UNITS_PER_SLICE,
            soft_seconds=TRAIN_SLICE_SOFT_SECONDS,
        )

    def on_end_of_algorithm(self):
        self._arv2_driver.require_completed_at_end()
'''
    return source.encode("ascii")


def _etf_main_source(
    *,
    activation_key: str,
    activation_sha256: str,
    activation_bytes: int,
) -> bytes:
    start = tuple(
        int(value)
        for value in etf_evaluator.WARMUP_START_SESSION.split("-")
    )
    end = tuple(
        int(value)
        for value in etf_evaluator.OUTCOME_MATURITY_END_SESSION.split("-")
    )
    source = f'''from AlgorithmImports import *
from accepted_risk_etf_baseline_evaluator import CANDIDATE_ETFS
from accepted_risk_etf_baseline_qc_runtime import AcceptedRiskEtfBaselineQcDriver


class ARV2AcceptedRiskEtfBaselineAlgorithm(QCAlgorithm):
    def initialize(self):
        self.set_time_zone("America/New_York")
        self.settings.daily_precise_end_time = True
        self.set_start_date({start[0]}, {start[1]}, {start[2]})
        self.set_end_date({end[0]}, {end[1]}, {end[2]})
        self.universe_settings.asynchronous = False
        self.universe_settings.resolution = Resolution.DAILY
        benchmark = self.add_equity(
            "SPY",
            Resolution.DAILY,
            fill_forward=False,
            leverage=1,
            extended_market_hours=False,
            data_normalization_mode=DataNormalizationMode.TOTAL_RETURN,
        ).symbol
        self._arv2_etf_symbols = {{}}
        for ticker in CANDIDATE_ETFS:
            self._arv2_etf_symbols[ticker] = self.add_equity(
                ticker,
                Resolution.DAILY,
                fill_forward=False,
                leverage=1,
                extended_market_hours=False,
                data_normalization_mode=DataNormalizationMode.TOTAL_RETURN,
            ).symbol
        self._arv2_driver = AcceptedRiskEtfBaselineQcDriver(
            self,
            activation_manifest_key={activation_key!r},
            activation_manifest_sha256={activation_sha256!r},
            activation_manifest_byte_count={activation_bytes},
            benchmark_symbol=benchmark,
            etf_symbols=self._arv2_etf_symbols,
        )
        self._arv2_universes = []
        for ticker in CANDIDATE_ETFS:
            self._arv2_universes.append(
                self.add_universe(
                    self.universe.etf(
                        self._arv2_etf_symbols[ticker],
                        self.universe_settings,
                        self._arv2_filter(ticker),
                    )
                )
            )

    def _arv2_filter(self, ticker):
        def selection(constituents):
            return self._arv2_driver.accept_constituents(ticker, constituents)
        return selection

    def on_data(self, data):
        self._arv2_driver.on_data(data)

    def on_end_of_algorithm(self):
        self._arv2_driver.require_completed_at_end()
'''
    return source.encode("ascii")


def _profile(evaluation_profile_id):
    if evaluation_profile_id is None:
        return None
    if evaluation_profile_id == etf_evaluator.PROFILE_ID:
        return etf_evaluator.require_etf_baseline_profile(
            evaluation_profile_id
        )
    if evaluation_profile_id == STOCK_PORTFOLIO_PROFILE_ID:
        return {
            "profile_id": STOCK_PORTFOLIO_PROFILE_ID,
            "profile_sha256": STOCK_PORTFOLIO_PROFILE_SHA256,
        }
    return regime_evaluator.require_regime_profile(evaluation_profile_id)


def project_source_paths_for_profile(evaluation_profile_id):
    _profile(evaluation_profile_id)
    if evaluation_profile_id == etf_evaluator.PROFILE_ID:
        return ETF_PROJECT_SOURCE_PATHS
    if evaluation_profile_id == STOCK_PORTFOLIO_PROFILE_ID:
        return STOCK_PORTFOLIO_PROJECT_SOURCE_PATHS
    return PROJECT_SOURCE_PATHS


def _validate_source(project_path: str, source: bytes) -> PreliminaryQcSourceFile:
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
        raise AcceptedRiskPreliminaryQcProjectionError(
            "preliminary QC source violates size, path, or future-import guard"
        )
    try:
        text = source.decode("ascii")
    except UnicodeDecodeError as exc:
        raise AcceptedRiskPreliminaryQcProjectionError(
            "preliminary QC source is not exact ASCII"
        ) from exc
    _audit_cloud_capabilities(text, project_path)
    try:
        compile(text, project_path, "exec")
        compile("QC_PRELUDE_SENTINEL = True\n" + text, project_path, "exec")
        compile("from AlgorithmImports import *\n" + text, project_path, "exec")
    except (SyntaxError, ValueError) as exc:
        raise AcceptedRiskPreliminaryQcProjectionError(
            "preliminary QC source does not compile raw and after QC prelude"
        ) from exc
    return PreliminaryQcSourceFile(
        SOURCE_SCHEMA,
        project_path,
        len(source),
        hashlib.sha256(source).hexdigest(),
        source,
    )


def build_accepted_risk_preliminary_qc_projection(
    package: package_builder.AcceptedRiskPreliminaryPackage,
    *,
    evaluation_profile_id: str | None = None,
) -> AcceptedRiskPreliminaryQcProjection:
    """Bind the compact activation to an exact flat QC source set."""

    package = package_builder.require_accepted_risk_preliminary_package(package)
    profile = _profile(evaluation_profile_id)
    activation = package.upload_objects[-1]
    if (
        activation.role != "activation_manifest"
        or activation.activation_manifest is not True
        or not activation.object_store_key.endswith("/transport-manifest.json")
    ):
        raise AcceptedRiskPreliminaryQcProjectionError(
            "preliminary package activation descriptor changed"
        )
    root = Path(__file__).resolve().parent
    files = []
    source_paths = project_source_paths_for_profile(evaluation_profile_id)
    for project_path in source_paths:
        try:
            source = (root / project_path).read_bytes()
        except OSError as exc:
            raise AcceptedRiskPreliminaryQcProjectionError(
                "preliminary QC source is unavailable"
            ) from exc
        files.append(_validate_source(project_path, source))
    files.append(
        _validate_source(
            MAIN_PROJECT_PATH,
            _main_source(
                activation_key=activation.object_store_key,
                activation_sha256=activation.content_sha256,
                activation_bytes=activation.byte_count,
                evaluation_profile_id=evaluation_profile_id,
            ),
        )
    )
    files.sort(key=lambda item: item.project_path)
    total = sum(item.byte_count for item in files)
    if total > MAX_TOTAL_SOURCE_BYTES:
        raise AcceptedRiskPreliminaryQcProjectionError(
            "preliminary QC source set exceeds reviewed total size"
        )
    semantic = {
        "schema": PROJECTION_SCHEMA,
        "projection_id": None,
        "projection_sha256": None,
        "package_id": package.package_id,
        "package_sha256": package.package_sha256,
        "activation_manifest_key": activation.object_store_key,
        "activation_manifest_sha256": activation.content_sha256,
        "activation_manifest_byte_count": activation.byte_count,
        "evaluation_profile_id": evaluation_profile_id,
        "evaluation_profile_sha256": (
            None if profile is None else profile["profile_sha256"]
        ),
        "source_files": [item.to_record() for item in files],
        "total_source_byte_count": total,
        "train_work_units_per_slice": runtime_builder.TRAIN_WORK_UNITS_PER_SLICE,
        "maximum_train_slice_count": runtime_builder.MAX_TRAIN_SLICE_COUNT,
        "preliminary": True,
        "formal": False,
        "outcome_result_transport": "aggregate_only_custom_summary_statistics",
        "orders": False,
        "trading": False,
    }
    digest = hashlib.sha256(_canonical(semantic)).hexdigest()
    value = AcceptedRiskPreliminaryQcProjection(
        PROJECTION_SCHEMA,
        "arv2-preliminary-qc-projection-" + digest[:24],
        digest,
        package.package_id,
        package.package_sha256,
        activation.object_store_key,
        activation.content_sha256,
        activation.byte_count,
        evaluation_profile_id,
        None if profile is None else profile["profile_sha256"],
        tuple(files),
        total,
        runtime_builder.TRAIN_WORK_UNITS_PER_SLICE,
        runtime_builder.MAX_TRAIN_SLICE_COUNT,
        True,
        False,
        "aggregate_only_custom_summary_statistics",
        False,
        False,
    )
    package_builder.require_accepted_risk_preliminary_package(package)
    return require_accepted_risk_preliminary_qc_projection(value)


def require_accepted_risk_preliminary_qc_projection(
    value: AcceptedRiskPreliminaryQcProjection,
) -> AcceptedRiskPreliminaryQcProjection:
    if type(value) is not AcceptedRiskPreliminaryQcProjection:
        raise AcceptedRiskPreliminaryQcProjectionError(
            "preliminary QC projection type changed"
        )
    profile = _profile(value.evaluation_profile_id)
    source_paths = project_source_paths_for_profile(value.evaluation_profile_id)
    if (
        value.schema != PROJECTION_SCHEMA
        or type(value.source_files) is not tuple
        or len(value.source_files) != len(source_paths) + 1
        or tuple(item.project_path for item in value.source_files)
        != tuple(sorted((*source_paths, MAIN_PROJECT_PATH)))
        or value.total_source_byte_count
        != sum(item.byte_count for item in value.source_files)
        or value.evaluation_profile_sha256
        != (None if profile is None else profile["profile_sha256"])
        or value.total_source_byte_count > MAX_TOTAL_SOURCE_BYTES
        or value.train_work_units_per_slice
        != runtime_builder.TRAIN_WORK_UNITS_PER_SLICE
        or type(value.train_work_units_per_slice) is not int
        or value.maximum_train_slice_count != runtime_builder.MAX_TRAIN_SLICE_COUNT
        or type(value.maximum_train_slice_count) is not int
        or value.preliminary is not True
        or value.formal is not False
        or value.outcome_result_transport
        != "aggregate_only_custom_summary_statistics"
        or value.orders is not False
        or value.trading is not False
    ):
        raise AcceptedRiskPreliminaryQcProjectionError(
            "preliminary QC projection disclosure or inventory changed"
        )
    rebuilt = tuple(
        _validate_source(item.project_path, item.source_bytes)
        for item in value.source_files
    )
    if rebuilt != value.source_files:
        raise AcceptedRiskPreliminaryQcProjectionError(
            "preliminary QC projected source identity changed"
        )
    main_source = next(
        item.source_bytes
        for item in value.source_files
        if item.project_path == MAIN_PROJECT_PATH
    )
    if main_source != _main_source(
        activation_key=value.activation_manifest_key,
        activation_sha256=value.activation_manifest_sha256,
        activation_bytes=value.activation_manifest_byte_count,
        evaluation_profile_id=value.evaluation_profile_id,
    ):
        raise AcceptedRiskPreliminaryQcProjectionError(
            "preliminary QC main source diverged from its bound activation or profile"
        )
    semantic = value.to_record()
    semantic["projection_id"] = None
    semantic["projection_sha256"] = None
    digest = hashlib.sha256(_canonical(semantic)).hexdigest()
    if (
        value.projection_sha256 != digest
        or value.projection_id
        != "arv2-preliminary-qc-projection-" + digest[:24]
    ):
        raise AcceptedRiskPreliminaryQcProjectionError(
            "preliminary QC projection identity changed"
        )
    return value


def iter_accepted_risk_preliminary_qc_sources(
    value: AcceptedRiskPreliminaryQcProjection,
):
    projection = require_accepted_risk_preliminary_qc_projection(value)
    for item in projection.source_files:
        yield item.project_path, item.source_bytes


__all__ = (
    "AcceptedRiskPreliminaryQcProjection",
    "AcceptedRiskPreliminaryQcProjectionError",
    "PreliminaryQcSourceFile",
    "build_accepted_risk_preliminary_qc_projection",
    "iter_accepted_risk_preliminary_qc_sources",
    "require_accepted_risk_preliminary_qc_projection",
    "project_source_paths_for_profile",
)
