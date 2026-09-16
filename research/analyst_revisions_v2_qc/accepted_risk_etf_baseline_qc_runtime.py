"""QuantConnect adapter for the accepted-risk unlevered ETF baseline."""

from decimal import Decimal, InvalidOperation

try:
    import accepted_risk_etf_baseline_evaluator as etf_evaluator
    import accepted_risk_preliminary_qc_figi as figi_authority
    import accepted_risk_preliminary_qc_runtime as package_runtime
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_etf_baseline_evaluator as etf_evaluator,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_preliminary_qc_figi as figi_authority,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_preliminary_qc_runtime as package_runtime,
    )


class AcceptedRiskEtfBaselineQcRuntimeError(ValueError):
    """The QC constituent or price envelope was not the frozen shape."""


RUNTIME_META_STATISTIC = "ARV2_RUNTIME_META"


def expected_custom_summary_statistic_names(profile_id=etf_evaluator.PROFILE_ID):
    etf_evaluator.require_etf_baseline_profile(profile_id)
    return tuple(
        sorted(
            (
                *etf_evaluator.expected_custom_summary_statistic_names(
                    profile_id
                ),
                RUNTIME_META_STATISTIC,
            )
        )
    )


def _error(message):
    raise AcceptedRiskEtfBaselineQcRuntimeError(message)


def _decimal(value, name, *, positive=False, nonnegative=False):
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise AcceptedRiskEtfBaselineQcRuntimeError(
            name + " is not decimal"
        ) from exc
    if not parsed.is_finite():
        _error(name + " is not finite")
    if positive and parsed <= 0:
        _error(name + " is not positive")
    if nonnegative and parsed < 0:
        _error(name + " is negative")
    return parsed


class AcceptedRiskEtfBaselineQcDriver:
    """Read the authenticated package and emit aggregate-only ETF evidence."""

    def __init__(
        self,
        algorithm,
        *,
        activation_manifest_key,
        activation_manifest_sha256,
        activation_manifest_byte_count,
        benchmark_symbol,
        etf_symbols,
    ):
        if (
            type(etf_symbols) is not dict
            or tuple(sorted(etf_symbols)) != etf_evaluator.CANDIDATE_ETFS
        ):
            _error("ETF symbol inventory changed")
        self._algorithm = algorithm
        self._activation_manifest_key = activation_manifest_key
        self._activation_manifest_sha256 = activation_manifest_sha256
        self._activation_manifest_byte_count = activation_manifest_byte_count
        self._benchmark_symbol = benchmark_symbol
        self._etf_symbols = dict(etf_symbols)
        self._pending_snapshots = []
        self._package = None
        self._resolution = None
        self._runtime = None
        self._emitted = False

    def _initialize_once(self):
        if self._runtime is not None:
            return
        package = package_runtime.load_accepted_risk_preliminary_package(
            self._algorithm,
            activation_manifest_key=self._activation_manifest_key,
            activation_manifest_sha256=self._activation_manifest_sha256,
            activation_manifest_byte_count=self._activation_manifest_byte_count,
        )
        try:
            lineage = dict(package.evaluator_input.source_lineage_sha256s)
            resolution = figi_authority.resolve_preliminary_qc_figis(
                package.runtime_symbol_bindings,
                expected_security_master_admission_sha256=(
                    lineage["security_master_admission_sha256"]
                ),
                composite_figi=self._algorithm.composite_figi,
                benchmark_symbol=self._benchmark_symbol,
            )
        except Exception as exc:
            raise AcceptedRiskEtfBaselineQcRuntimeError(
                "ETF baseline composite-FIGI inventory did not resolve"
            ) from exc
        sid_map = {
            item["qc_security_id"]: item["security_id"]
            for item in resolution.resolved
        }
        runtime = etf_evaluator.AcceptedRiskEtfBaselineRuntime(
            package.evaluator_input,
            qc_sid_to_security_id=sid_map,
            package_id=package.package_id,
            package_sha256=package.package_sha256,
        )
        for snapshot in self._pending_snapshots:
            runtime.accept_holdings_snapshot(snapshot)
        self._pending_snapshots = []
        self._package = package
        self._resolution = resolution
        self._runtime = runtime

    def accept_constituents(self, ticker, constituents):
        if ticker not in etf_evaluator.CANDIDATE_ETFS or type(ticker) is not str:
            _error("ETF constituent callback ticker changed")
        try:
            session = self._algorithm.time.date().isoformat()
            materialized = tuple(constituents)
        except Exception as exc:
            raise AcceptedRiskEtfBaselineQcRuntimeError(
                "ETF constituent callback is unreadable"
            ) from exc
        if not materialized:
            return ()
        weights = {}
        for item in materialized:
            try:
                weight_value = item.weight
                symbol = item.symbol
                sid = str(symbol.id)
            except Exception as exc:
                raise AcceptedRiskEtfBaselineQcRuntimeError(
                    "ETF constituent row is unreadable"
                ) from exc
            if weight_value is None:
                continue
            weight = _decimal(weight_value, "ETF constituent weight")
            if weight <= 0:
                continue
            if sid in weights:
                _error("ETF constituent snapshot duplicated a QC SID")
            weights[sid] = weight
        if not weights:
            return ()
        snapshot = etf_evaluator.EtfHoldingsSnapshot(
            ticker,
            session,
            tuple(
                etf_evaluator.ConstituentWeight(sid, weight)
                for sid, weight in sorted(weights.items())
            ),
        )
        if self._runtime is None:
            self._pending_snapshots.append(snapshot)
        else:
            self._runtime.accept_holdings_snapshot(snapshot)
        return ()

    @staticmethod
    def _bar(bars, symbol, ticker, session):
        try:
            item = bars.get(symbol)
        except Exception as exc:
            raise AcceptedRiskEtfBaselineQcRuntimeError(
                "QC daily bar dictionary is unreadable"
            ) from exc
        if item is None:
            return None
        try:
            open_value = item.open
            close_value = item.close
            volume_value = item.volume
        except Exception as exc:
            raise AcceptedRiskEtfBaselineQcRuntimeError(
                "QC daily TradeBar is unreadable"
            ) from exc
        return etf_evaluator.EtfDailyBar(
            ticker,
            session,
            _decimal(open_value, "ETF adjusted open", positive=True),
            _decimal(close_value, "ETF adjusted close", positive=True),
            _decimal(volume_value, "ETF volume", nonnegative=True),
        )

    def on_data(self, data):
        self._initialize_once()
        try:
            session = self._algorithm.time.date().isoformat()
            bars = data.bars
        except Exception as exc:
            raise AcceptedRiskEtfBaselineQcRuntimeError(
                "QC Slice envelope is unreadable"
            ) from exc
        records = []
        benchmark = self._bar(
            bars,
            self._benchmark_symbol,
            "SPY",
            session,
        )
        # ETF-constituent universe updates can produce an additional Slice on
        # the same QC algorithm date before the daily equity TradeBars arrive.
        # SPY is the frozen session clock: only its one daily bar authorizes a
        # call into the strictly increasing session evaluator.
        if benchmark is None:
            return
        records.append(benchmark)
        for ticker in etf_evaluator.CANDIDATE_ETFS:
            row = self._bar(bars, self._etf_symbols[ticker], ticker, session)
            if row is not None:
                records.append(row)
        self._runtime.process_session(
            session,
            tuple(sorted(records, key=lambda row: row.ticker)),
        )

    @property
    def completed(self):
        return self._runtime is not None and self._runtime.completed

    def emit_completed_summary(self):
        if not self.completed:
            _error("ETF aggregate summary requested before completion")
        if self._emitted:
            return
        statistics = self._runtime.custom_summary_statistics()
        runtime_meta = {
            "schema": "arv2-accepted-risk-etf-sector-qc-runtime-meta-v1",
            "status": "PRELIMINARY_ACCEPTED_RISK_UNLEVERED_ETF_BASELINE_COMPLETED",
            "profile_id": etf_evaluator.PROFILE_ID,
            "profile_sha256": etf_evaluator.require_etf_baseline_profile(
                etf_evaluator.PROFILE_ID
            )["profile_sha256"],
            "package_id": self._package.package_id,
            "package_sha256": self._package.package_sha256,
            "activation_manifest_sha256": self._package.activation_manifest_sha256,
            "symbol_resolution_id": self._resolution.resolution_id,
            "symbol_resolution_sha256": self._resolution.resolution_sha256,
            "resolved_security_count": self._resolution.resolved_count,
            "named_security_refusal_count": self._resolution.named_refusal_count,
            "candidate_etf_count": len(etf_evaluator.CANDIDATE_ETFS),
            "result_transport": "aggregate_only_custom_summary_statistics",
            "host_object_store_export_required": False,
            "preliminary": True,
            "point_in_time": False,
            "formal": False,
            "control_residualized": False,
            "economic_portfolio": True,
            "etf": True,
            "leverage": False,
            "deployment": False,
            "orders": False,
            "trading": False,
        }
        statistics[RUNTIME_META_STATISTIC] = etf_evaluator._canonical(
            runtime_meta
        ).decode("ascii")
        if (
            tuple(sorted(statistics))
            != expected_custom_summary_statistic_names()
            or any(
                type(key) is not str
                or type(value) is not str
                or len(key) > 64
                or len(value) > 4096
                for key, value in statistics.items()
            )
        ):
            _error("ETF aggregate custom-statistic transport changed")
        try:
            for key, value in sorted(statistics.items()):
                self._algorithm.set_summary_statistic(key, value)
        except Exception as exc:
            raise AcceptedRiskEtfBaselineQcRuntimeError(
                "ETF custom summary statistic emission failed"
            ) from exc
        self._emitted = True

    def require_completed_at_end(self):
        self._initialize_once()
        self._runtime.complete()
        self.emit_completed_summary()
        if not self._emitted:
            _error("ETF baseline ended without aggregate completion")
        return True


__all__ = (
    "AcceptedRiskEtfBaselineQcDriver",
    "AcceptedRiskEtfBaselineQcRuntimeError",
    "RUNTIME_META_STATISTIC",
    "expected_custom_summary_statistic_names",
)
