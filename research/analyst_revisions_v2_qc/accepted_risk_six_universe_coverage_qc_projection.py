"""Exact, outcome-free QC source for the six-universe coverage census.

This host-only builder reads the authenticated local package and closes the
small source graph needed for one 2021--2025 counts-only diagnostic. It makes
no network call and grants the projected algorithm no order or price-history
capability.
"""

import ast
import dataclasses
import hashlib
import json
from pathlib import Path

from . import accepted_risk_delta_order_package as _delta
from . import accepted_risk_preliminary_package as _package
from . import accepted_risk_six_universe_coverage_qc_runtime as _runtime
from . import accepted_risk_six_universe_gate as _gate


class SixUniverseCoverageQcProjectionError(ValueError):
    """The input, source closure, or diagnostic capability changed."""


PROJECTION_SCHEMA = "arv2-six-universe-coverage-qc-projection-v1"
SOURCE_FILE_SCHEMA = "arv2-six-universe-coverage-qc-source-file-v1"
MAIN_PROJECT_PATH = "main.py"
MAXIMUM_SOURCE_FILE_BYTES = 64 * 1024
MAXIMUM_TOTAL_SOURCE_BYTES = 320 * 1024
ALGORITHM_START = (2020, 11, 1)
ALGORITHM_END = (2025, 12, 30)
_SOURCE_PATHS = (
    "accepted_risk_preliminary_rating_policy.py",
    "accepted_risk_preliminary_rating_evaluator.py",
    "accepted_risk_sequential_r055_score.py",
    "accepted_risk_order_level_input_runtime.py",
    "accepted_risk_preliminary_qc_figi.py",
    "accepted_risk_six_universe_gate.py",
    "accepted_risk_six_universe_gate_evaluator.py",
    "accepted_risk_six_universe_coverage_qc_runtime.py",
)
_FORBIDDEN_IMPORT_ROOTS = frozenset({
    "aiohttp", "ftplib", "http", "os", "requests", "shutil",
    "socket", "subprocess", "urllib",
})
_FORBIDDEN_CALLS = frozenset({
    "buy", "cancel_order", "delete", "download", "eval", "exec",
    "history", "limit_order", "liquidate", "market_on_open_order",
    "market_order", "open", "quit", "save", "save_bytes", "sell",
    "set_brokerage_model", "set_holdings", "stop_market_order", "system",
    "update_order", "write", "write_bytes",
})


def _error(message):
    raise SixUniverseCoverageQcProjectionError(message)


def _canonical(value):
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise SixUniverseCoverageQcProjectionError(
            "coverage projection is not canonical ASCII JSON"
        ) from exc


def _audit_source(project_path, source):
    try:
        content = source.decode("ascii")
        tree = ast.parse(content, filename=project_path)
        compile(content, project_path, "exec")
        compile("from AlgorithmImports import *\n" + content, project_path, "exec")
    except (SyntaxError, UnicodeDecodeError) as exc:
        raise SixUniverseCoverageQcProjectionError(
            "coverage source is not QC-prelude-safe Python"
        ) from exc
    if "from __future__" in content:
        _error("coverage source retained a future import")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.split(".", 1)[0] in _FORBIDDEN_IMPORT_ROOTS
                   for alias in node.names):
                _error("coverage source imported an external capability")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".", 1)[0] in _FORBIDDEN_IMPORT_ROOTS:
                _error("coverage source imported an external capability")
        elif isinstance(node, ast.Call):
            method = node.func
            name = method.id if isinstance(method, ast.Name) else (
                method.attr if isinstance(method, ast.Attribute) else None
            )
            if name in _FORBIDDEN_CALLS:
                _error("coverage source called an outcome or execution capability")


@dataclasses.dataclass(frozen=True, slots=True)
class CoverageSourceFile:
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
class SixUniverseCoverageQcProjection:
    schema: str
    projection_id: str
    projection_sha256: str
    profile_id: str
    profile_sha256: str
    package_id: str
    package_sha256: str
    package_lineage_sha256: str
    activation_manifest_key: str
    activation_manifest_sha256: str
    activation_manifest_byte_count: int
    source_files: tuple[CoverageSourceFile, ...]
    total_source_byte_count: int
    statistic_names: tuple[str, ...]

    def to_record(self):
        return {
            "schema": self.schema,
            "projection_id": self.projection_id,
            "projection_sha256": self.projection_sha256,
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
            "statistic_names": list(self.statistic_names),
            "outcome_access": False,
            "price_access": False,
            "orders": False,
            "backtest_only": True,
            "deployment": False,
            "trading": False,
        }


def _source_file(project_path, source):
    if (
        type(project_path) is not str or not project_path.endswith(".py")
        or type(source) is not bytes or not source
        or len(source) > MAXIMUM_SOURCE_FILE_BYTES
    ):
        _error("coverage source file exceeded its bound")
    _audit_source(project_path, source)
    return CoverageSourceFile(
        SOURCE_FILE_SCHEMA, project_path, len(source),
        hashlib.sha256(source).hexdigest(), source,
    )


def _main_source(activation):
    source = f'''from AlgorithmImports import *
from accepted_risk_six_universe_coverage_qc_runtime import SixUniverseCoverageQcDriver


class ARV2SixUniverseCoverageDiagnostic(QCAlgorithm):
    def initialize(self):
        self.set_time_zone("America/New_York")
        self.settings.daily_precise_end_time = True
        self.set_start_date({ALGORITHM_START[0]}, {ALGORITHM_START[1]}, {ALGORITHM_START[2]})
        # The engine trades through the end of the end date and then fires
        # on_end_of_algorithm with the clock at 00:00 of the following day.
        # The frozen coverage census pins on_end_of_algorithm to the session
        # 2025-12-31 (EVALUATION_END_SESSION), so the end date must be the
        # prior trading day, 2025-12-30, to land the termination clock on it.
        self.set_end_date({ALGORITHM_END[0]}, {ALGORITHM_END[1]}, {ALGORITHM_END[2]})
        self.universe_settings.asynchronous = False
        self.universe_settings.resolution = Resolution.DAILY
        self.universe_settings.data_normalization_mode = DataNormalizationMode.RAW
        self._arv2_etf_symbols = {{}}
        for ticker in {_gate.UNIVERSE_IDS!r}:
            self._arv2_etf_symbols[ticker] = self.add_equity(
                ticker, Resolution.DAILY, fill_forward=False, leverage=1,
                extended_market_hours=False,
                data_normalization_mode=DataNormalizationMode.RAW,
            ).symbol
        self._arv2_fundamental_universe = self.add_universe(
            self._arv2_accept_fundamentals
        )
        self._arv2_constituent_universes = {{}}
        for ticker in {_gate.UNIVERSE_IDS!r}:
            callback = lambda rows, ticker=ticker: self._arv2_accept_constituents(ticker, rows)
            self._arv2_constituent_universes[ticker] = self.add_universe(
                self.universe.etf(
                    self._arv2_etf_symbols[ticker], self.universe_settings, callback,
                )
            )
        self._arv2_driver = SixUniverseCoverageQcDriver(
            self,
            activation_manifest_key={activation.object_store_key!r},
            activation_manifest_sha256={activation.content_sha256!r},
            activation_manifest_byte_count={activation.byte_count},
            benchmark_symbol=self._arv2_etf_symbols["SPY"],
            etf_symbols=self._arv2_etf_symbols,
            fundamental_universe=self._arv2_fundamental_universe,
            constituent_universes=self._arv2_constituent_universes,
        )
        self._arv2_driver.initialize()
        benchmark = self._arv2_etf_symbols["SPY"]
        self.schedule.on(
            self.date_rules.every_day(benchmark),
            self.time_rules.after_market_close(benchmark, 0),
            self._arv2_driver.on_after_close,
        )

    def _arv2_accept_fundamentals(self, rows):
        return self._arv2_driver.accept_fundamentals(rows) if hasattr(self, "_arv2_driver") else []

    def _arv2_accept_constituents(self, ticker, rows):
        return self._arv2_driver.accept_constituents(ticker, rows) if hasattr(self, "_arv2_driver") else []

    def on_end_of_algorithm(self):
        self._arv2_driver.on_end_of_algorithm()
'''
    return source.encode("ascii")


def build_six_universe_coverage_qc_projection(delta_package):
    if type(delta_package) is not _delta.AcceptedRiskDeltaOrderPackage:
        _error("coverage projection requires the exact delta package")
    if (
        delta_package.package.package_id != _delta.EXPECTED_DELTA_PACKAGE_ID
        or delta_package.package.package_sha256
        != _delta.EXPECTED_DELTA_PACKAGE_SHA256
        or delta_package.lineage_sha256
        != _delta.EXPECTED_DELTA_LINEAGE_SHA256
    ):
        _error("coverage delta package authority changed")
    package = _package.require_accepted_risk_preliminary_package(
        delta_package.package
    )
    activation = package.upload_objects[-1]
    if (
        activation.role != "activation_manifest"
        or activation.activation_manifest is not True
        or not activation.object_store_key.endswith("/transport-manifest.json")
    ):
        _error("coverage activation descriptor changed")
    root = Path(__file__).resolve().parent
    files = []
    for project_path in _SOURCE_PATHS:
        try:
            source = (root / project_path).read_bytes()
        except OSError as exc:
            raise SixUniverseCoverageQcProjectionError(
                "coverage source is unavailable"
            ) from exc
        files.append(_source_file(project_path, source))
    files.append(_source_file(MAIN_PROJECT_PATH, _main_source(activation)))
    files.sort(key=lambda item: item.project_path)
    total = sum(item.byte_count for item in files)
    if total > MAXIMUM_TOTAL_SOURCE_BYTES:
        _error("coverage source closure exceeded its bound")
    profile = _runtime.require_six_universe_coverage_profile()
    semantic = {
        "schema": PROJECTION_SCHEMA,
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
        "statistic_names": list(_runtime.expected_custom_summary_statistic_names()),
        "outcome_access": False,
        "price_access": False,
        "orders": False,
        "backtest_only": True,
        "deployment": False,
        "trading": False,
    }
    digest = hashlib.sha256(_canonical(semantic)).hexdigest()
    projection = SixUniverseCoverageQcProjection(
        PROJECTION_SCHEMA,
        "arv2-six-universe-coverage-qc-projection-" + digest[:24],
        digest,
        profile["profile_id"], profile["profile_sha256"],
        package.package_id, package.package_sha256,
        delta_package.lineage_sha256,
        activation.object_store_key, activation.content_sha256,
        activation.byte_count,
        tuple(files), total,
        _runtime.expected_custom_summary_statistic_names(),
    )
    if projection.to_record()["projection_sha256"] != digest:
        _error("coverage projection did not self-authenticate")
    return projection


__all__ = (
    "CoverageSourceFile", "SixUniverseCoverageQcProjection",
    "SixUniverseCoverageQcProjectionError", "PROJECTION_SCHEMA",
    "MAIN_PROJECT_PATH", "build_six_universe_coverage_qc_projection",
)
