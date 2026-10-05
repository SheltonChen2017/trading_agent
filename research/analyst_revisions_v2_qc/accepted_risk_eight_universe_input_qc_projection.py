"""Exact, input-only QC source projection for R267's eight-ETF readiness census.

This diagnostic is intentionally not order-based: it measures historical
constituent callback and identity availability, not a trading strategy.
It cannot report returns, fills or performance.  The outcome candidates use
separate reviewed order-based source and distinct research looks.
"""

import dataclasses
import hashlib
from pathlib import Path

from . import accepted_risk_eight_universe_input_qc_runtime as _runtime
from . import accepted_risk_six_universe_coverage_qc_projection as _six


class EightUniverseInputQcProjectionError(ValueError):
    """The source graph, profile or input package changed."""


PROJECTION_SCHEMA = "arv2-eight-universe-input-qc-projection-v1"
MAIN_PROJECT_PATH = "main.py"
MAXIMUM_TOTAL_SOURCE_BYTES = 320 * 1024
MAXIMUM_SOURCE_FILE_BYTES = _six.MAXIMUM_SOURCE_FILE_BYTES
PROJECT_NAME = "117 ARV2 EIGHT INPUT R267 2021 2025"
CANDIDATE_ID = "R267"
MAXIMUM_QC_ATTEMPTS = 3


def _error(message):
    raise EightUniverseInputQcProjectionError(message)


def _main_source(activation):
    return f'''from AlgorithmImports import *
from accepted_risk_eight_universe_input_qc_runtime import EightUniverseInputQcDriver


class ARV2EightUniverseInputDiagnostic(QCAlgorithm):
    def initialize(self):
        self.set_time_zone("America/New_York")
        self.settings.daily_precise_end_time = True
        self.set_start_date(2020, 11, 1)
        # The terminal callback lands on 2025-12-31 after the final 12-30 session.
        self.set_end_date(2025, 12, 30)
        self.universe_settings.asynchronous = False
        self.universe_settings.resolution = Resolution.DAILY
        self.universe_settings.data_normalization_mode = DataNormalizationMode.RAW
        self._arv2_etf_symbols = {{}}
        for ticker in {_runtime.UNIVERSE_IDS!r}:
            self._arv2_etf_symbols[ticker] = self.add_equity(
                ticker, Resolution.DAILY, fill_forward=False, leverage=1,
                extended_market_hours=False,
                data_normalization_mode=DataNormalizationMode.RAW,
            ).symbol
        self._arv2_fundamental_universe = self.add_universe(self._accept_fundamentals)
        self._arv2_constituent_universes = {{}}
        for ticker in {_runtime.UNIVERSE_IDS!r}:
            callback = lambda rows, ticker=ticker: self._accept_constituents(ticker, rows)
            self._arv2_constituent_universes[ticker] = self.add_universe(
                self.universe.etf(self._arv2_etf_symbols[ticker], self.universe_settings, callback)
            )
        self._arv2_driver = EightUniverseInputQcDriver(
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

    def _accept_fundamentals(self, rows):
        return self._arv2_driver.accept_fundamentals(rows) if hasattr(self, "_arv2_driver") else []

    def _accept_constituents(self, ticker, rows):
        return self._arv2_driver.accept_constituents(ticker, rows) if hasattr(self, "_arv2_driver") else []

    def on_end_of_algorithm(self):
        self._arv2_driver.on_end_of_algorithm()
'''.encode("ascii")


@dataclasses.dataclass(frozen=True, slots=True)
class EightUniverseInputQcProjection:
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
    source_files: tuple
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


def build_eight_universe_input_qc_projection(delta_package):
    """Reauthenticate the reviewed six-file closure, adding only R267 source."""
    prior = _six.build_six_universe_coverage_qc_projection(delta_package)
    activation = delta_package.package.upload_objects[-1]
    root = Path(__file__).resolve().parent
    new_runtime_path = "accepted_risk_eight_universe_input_qc_runtime.py"
    source = (root / new_runtime_path).read_bytes()
    files = [item for item in prior.source_files if item.project_path != MAIN_PROJECT_PATH]
    files.append(_six._source_file(new_runtime_path, source))
    files.append(_six._source_file(MAIN_PROJECT_PATH, _main_source(activation)))
    files.sort(key=lambda item: item.project_path)
    if len(files) != 10 or len({item.project_path for item in files}) != 10:
        _error("eight-universe diagnostic source closure changed")
    total = sum(item.byte_count for item in files)
    if total > MAXIMUM_TOTAL_SOURCE_BYTES or any(
        item.byte_count > MAXIMUM_SOURCE_FILE_BYTES for item in files
    ):
        _error("eight-universe diagnostic source exceeded its byte bound")
    profile = _runtime.require_eight_universe_input_profile()
    semantic = {
        "schema": PROJECTION_SCHEMA,
        "profile_id": profile["profile_id"],
        "profile_sha256": profile["profile_sha256"],
        "package_id": prior.package_id,
        "package_sha256": prior.package_sha256,
        "package_lineage_sha256": prior.package_lineage_sha256,
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
    digest = hashlib.sha256(_six._canonical(semantic)).hexdigest()
    projection = EightUniverseInputQcProjection(
        PROJECTION_SCHEMA, "arv2-eight-universe-input-r267-qc-projection-" + digest[:24],
        digest, profile["profile_id"], profile["profile_sha256"],
        prior.package_id, prior.package_sha256, prior.package_lineage_sha256,
        activation.object_store_key, activation.content_sha256,
        activation.byte_count, tuple(files), total,
        _runtime.expected_custom_summary_statistic_names(),
    )
    if projection.to_record()["projection_sha256"] != digest:
        _error("eight-universe diagnostic projection did not self-authenticate")
    return projection


__all__ = (
    "EightUniverseInputQcProjection", "EightUniverseInputQcProjectionError",
    "PROJECT_NAME", "CANDIDATE_ID", "MAXIMUM_QC_ATTEMPTS",
    "build_eight_universe_input_qc_projection",
)
