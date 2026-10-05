"""Preparation-only, zero-I/O plan for 82 quarterly SEC master indexes.

This module has deliberately no transport, filesystem publication, or launch
entry point.  A future, independently reviewed runner must implement bounded
requests and fresh immutable output/journal/report before any SEC request.
The plan binds the exact retained noncanonical 82-ZIP census to one master.gz
URL per quarter; it does not establish SEC origin, index completeness,
canonical/PIT evidence, outcome access, or backtest authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re

from data.hashing import hash_payload
from research.insider_buying.sec_zip_corpus_census import (
    SecZipCensusQuarter,
    SecZipCorpusCensus,
)


MASTER82_PREPARATION_VERSION = "insider-buying-sec-master82-preparation-v1"
RETAINED_CENSUS_SHA256 = (
    "2c93041a1dd2641d80722bd90630c37e939fb10b65837659bb1893168bd83c33"
)
PINNED_MASTER_URL_INVENTORY_SHA256 = (
    "57d28aa3e7f1ca94204eaea84682947780221e72e8f8f40d3a23bbde96f801a4"
)
MAX_MASTER_GZIP_BYTES = 8 * 1024 * 1024
MAX_MASTER_INDEX_BYTES = 64 * 1024 * 1024
MAX_ATTEMPTS_PER_ARTIFACT = 3
MAX_DISTINCT_ARTIFACTS = 82
MAX_TOTAL_ATTEMPTS = 246
MIN_REQUEST_INTERVAL_NS = 500_000_000
RETAINED_FORM4_OR_4A_TARGET_COUNT = 4_034_227
_PERIODS = tuple(
    f"{year}Q{quarter}"
    for year in range(2006, 2027)
    for quarter in range(1, 5)
    if (year, quarter) <= (2026, 2)
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_CONTACT = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}\Z")


class SecMaster82PreparationError(ValueError):
    """The zero-I/O acquisition plan refused an input or mutation."""


def _refuse(message: str) -> None:
    raise SecMaster82PreparationError(f"REFUSED: {message}")


def _url(period: str) -> str:
    if type(period) is not str or period not in _PERIODS:
        _refuse("master request period is outside the exact 82-quarter scope")
    return (
        "https://www.sec.gov/Archives/edgar/full-index/"
        f"{period[:4]}/QTR{period[-1]}/master.gz"
    )


def _url_inventory_payload() -> list[dict[str, str]]:
    return [{"period": period, "url": _url(period)} for period in _PERIODS]


@dataclass(frozen=True)
class SecMaster82QuarterRequest:
    period: str
    url: str
    retained_zip_sha256: str
    form4_target_count: int
    form4a_target_count: int

    def __post_init__(self) -> None:
        if (
            type(self) is not SecMaster82QuarterRequest
            or type(self.period) is not str
            or self.period not in _PERIODS
            or type(self.url) is not str
            or self.url != _url(self.period)
            or type(self.retained_zip_sha256) is not str
            or _SHA256.fullmatch(self.retained_zip_sha256) is None
            or type(self.form4_target_count) is not int
            or self.form4_target_count < 0
            or type(self.form4a_target_count) is not int
            or self.form4a_target_count < 0
        ):
            _refuse("master request does not match its exact URL and ZIP-count binding")

    def to_payload(self) -> dict[str, object]:
        self.__post_init__()
        return {
            "period": self.period,
            "url": self.url,
            "retained_zip_sha256": self.retained_zip_sha256,
            "form4_target_count": self.form4_target_count,
            "form4a_target_count": self.form4a_target_count,
        }


@dataclass(frozen=True)
class SecMaster82AcquisitionPreparation:
    contact_email: str = field(repr=False)
    census_scope: str
    census_sha256: str
    requests: tuple[SecMaster82QuarterRequest, ...]
    request_inventory_sha256: str
    _source_census: SecZipCorpusCensus | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            type(self) is not SecMaster82AcquisitionPreparation
            or type(self.contact_email) is not str
            or len(self.contact_email) > 254
            or _CONTACT.fullmatch(self.contact_email) is None
            or type(self.census_scope) is not str
            or self.census_scope not in {
                "retained_noncanonical_zip_census", "synthetic_test_census"
            }
            or type(self.census_sha256) is not str
            or _SHA256.fullmatch(self.census_sha256) is None
            or type(self.requests) is not tuple
            or len(self.requests) != MAX_DISTINCT_ARTIFACTS
            or any(type(request) is not SecMaster82QuarterRequest for request in self.requests)
            or tuple(request.period for request in self.requests) != _PERIODS
            or type(self.request_inventory_sha256) is not str
            or _SHA256.fullmatch(self.request_inventory_sha256) is None
        ):
            _refuse("82-quarter preparation identity or scope is malformed")
        for request in self.requests:
            request.__post_init__()
        if hash_payload(_url_inventory_payload()) != PINNED_MASTER_URL_INVENTORY_SHA256:
            _refuse("literal master URL inventory changed")
        if hash_payload([request.to_payload() for request in self.requests]) != self.request_inventory_sha256:
            _refuse("request inventory fingerprint changed")
        if self.census_scope == "retained_noncanonical_zip_census" and (
            self.census_sha256 != RETAINED_CENSUS_SHA256
            or sum(
                request.form4_target_count + request.form4a_target_count
                for request in self.requests
            ) != RETAINED_FORM4_OR_4A_TARGET_COUNT
        ):
            _refuse("retained census fingerprint or target count changed")
        if self.census_scope == "retained_noncanonical_zip_census":
            census = self._source_census
            if type(census) is not SecZipCorpusCensus:
                _refuse("retained plan requires its validated source census")
            census.__post_init__()
            if (
                census.scope != self.census_scope
                or census.sha256 != self.census_sha256
                or tuple(
                    (
                        request.period, request.retained_zip_sha256,
                        request.form4_target_count, request.form4a_target_count,
                    )
                    for request in self.requests
                ) != tuple(
                    (
                        quarter.period, quarter.zip_sha256,
                        quarter.form4_accessions, quarter.form4a_accessions,
                    )
                    for quarter in census.quarters
                )
            ):
                _refuse("retained plan differs from its validated source census")
        elif self._source_census is not None:
            _refuse("synthetic plan may not carry a retained source census")

    def to_payload(self) -> dict[str, object]:
        self.__post_init__()
        return {
            "kind": "insider-buying-sec-master82-acquisition-preparation",
            "version": MASTER82_PREPARATION_VERSION,
            "scope": self.census_scope,
            "identifying_contact_provided": True,
            "source_census_sha256": self.census_sha256,
            "pinned_master_url_inventory_sha256": PINNED_MASTER_URL_INVENTORY_SHA256,
            "request_inventory_sha256": self.request_inventory_sha256,
            "requests": [request.to_payload() for request in self.requests],
            "request_policy_for_future_review": {
                "exact_distinct_artifacts": MAX_DISTINCT_ARTIFACTS,
                "max_attempts_per_artifact": MAX_ATTEMPTS_PER_ARTIFACT,
                "max_total_attempts": MAX_TOTAL_ATTEMPTS,
                "minimum_interval_between_transport_completions_and_next_dispatch_ns": (
                    MIN_REQUEST_INTERVAL_NS
                ),
                "ideal_first_to_last_dispatch_floor_ms_excluding_work_and_backoff": 40_500,
                "max_successful_master_gzip_bytes": MAX_MASTER_GZIP_BYTES,
                "max_expanded_master_index_bytes": MAX_MASTER_INDEX_BYTES,
                "stop_on_http_403_or_429": True,
                "redirects_forbidden": True,
                "fresh_outside_git_immutable_output_journal_report_required": True,
            },
            "authority": {
                "operational_runner_implemented": False,
                "network_request_made": False,
                "output_journal_report_published": False,
                "master_indexes_acquired": False,
                "quarter_population_complete": False,
                "sec_origin_authenticated": False,
                "canonical_evidence": False,
                "point_in_time_data": False,
                "complete_parent_or_acceptance_metadata": False,
                "outcome_access_authorized": False,
                "qc_backtest_authorized": False,
                "broker_or_trading_authorized": False,
                "research_looks": 0,
            },
        }

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


def _build_plan(
    *, census_scope: str, census_sha256: str,
    quarters: tuple[SecZipCensusQuarter, ...], contact_email: str,
    source_census: SecZipCorpusCensus | None = None,
) -> SecMaster82AcquisitionPreparation:
    """Construct only a plan; a synthetic scope is never public real evidence."""
    if (
        type(quarters) is not tuple
        or len(quarters) != MAX_DISTINCT_ARTIFACTS
        or any(type(quarter) is not SecZipCensusQuarter for quarter in quarters)
        or tuple(quarter.period for quarter in quarters) != _PERIODS
    ):
        _refuse("source census quarters are incomplete or reordered")
    for quarter in quarters:
        quarter.__post_init__()
    requests = tuple(
        SecMaster82QuarterRequest(
            period=quarter.period,
            url=_url(quarter.period),
            retained_zip_sha256=quarter.zip_sha256,
            form4_target_count=quarter.form4_accessions,
            form4a_target_count=quarter.form4a_accessions,
        )
        for quarter in quarters
    )
    return SecMaster82AcquisitionPreparation(
        contact_email=contact_email,
        census_scope=census_scope,
        census_sha256=census_sha256,
        requests=requests,
        request_inventory_sha256=hash_payload([request.to_payload() for request in requests]),
        _source_census=source_census,
    )


def prepare_retained_master82_acquisition(
    census: SecZipCorpusCensus, *, contact_email: str,
) -> SecMaster82AcquisitionPreparation:
    """Bind an already-loaded exact retained census to a non-executable plan."""
    if type(census) is not SecZipCorpusCensus:
        _refuse("an exact source-bound census receipt is required")
    census.__post_init__()
    if (
        census.scope != "retained_noncanonical_zip_census"
        or census.sha256 != RETAINED_CENSUS_SHA256
        or census.target_accessions != RETAINED_FORM4_OR_4A_TARGET_COUNT
    ):
        _refuse("the exact retained 82-quarter census is required")
    return _build_plan(
        census_scope=census.scope,
        census_sha256=census.sha256,
        quarters=census.quarters,
        contact_email=contact_email,
        source_census=census,
    )


__all__ = [
    "MASTER82_PREPARATION_VERSION",
    "RETAINED_CENSUS_SHA256",
    "PINNED_MASTER_URL_INVENTORY_SHA256",
    "SecMaster82AcquisitionPreparation",
    "SecMaster82PreparationError",
    "SecMaster82QuarterRequest",
    "prepare_retained_master82_acquisition",
]
