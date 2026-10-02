"""Read-only, noncanonical IB-1B preflight for the 82 retained ZIP quarters.

This is a staged *header and resource* check, not an IB-1B parser run. It
first obtains the exact 82-ZIP census, then re-reads one bounded archive at a
time through the census's pinned-directory reader. It checks every physical
TSV header against the unreviewed 82-quarter schema-profile candidate and
the unchanged per-quarter IB-1B expanded-input cap. No snapshot or report
file is written, so cancellation cannot leave a partial success artifact.

Neither local file timestamps nor matching ZIP/header hashes authenticate SEC
origin, filing acceptance time, complete parents, row-key uniqueness,
point-in-time availability, canonical evidence, or backtest readiness.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from data.hashing import hash_bytes, hash_payload
from research.insider_buying.sec_bulk_parsed_snapshot import (
    MAX_TOTAL_PARSED_INPUT_BYTES,
    SecTsvSchemaProfile,
)
from research.insider_buying.sec_bulk_snapshot import ALLOWED_SEC_TABLES, MAX_ARCHIVE_BYTES
from research.insider_buying.sec_ib1b_82q_schema_profile import (
    RETAINED_82Q_SCHEMA_PROFILE_SHA256,
    build_retained_82q_schema_profile_candidate,
    verify_retained_82q_schema_profile,
)
from research.insider_buying.sec_zip_corpus_census import (
    SecZipCorpusCensus,
    SecZipCorpusCensusError,
    _PinnedZipRoot,
    _plain_root,
    census_retained_sec_zip_corpus,
)


IB1B_82Q_HEADER_PREFLIGHT_KIND = "insider-buying-ib1b-82q-header-preflight"
IB1B_82Q_HEADER_PREFLIGHT_VERSION = 1
RETAINED_82Q_CENSUS_SHA256 = (
    "2c93041a1dd2641d80722bd90630c37e939fb10b65837659bb1893168bd83c33"
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_RETAINED_CONSTRUCTION_TOKEN = object()
_SYNTHETIC_CONSTRUCTION_TOKEN = object()


class Ib1b82qOfflinePreflightError(ValueError):
    """The bounded offline check refused before returning a success receipt."""


def _refuse(message: str) -> None:
    raise Ib1b82qOfflinePreflightError(f"REFUSED: {message}")


@dataclass(frozen=True)
class Ib1b82qHeaderQuarter:
    """One rehashed ZIP and eight observed physical headers, not parsed rows."""

    period: str
    zip_sha256: str
    zip_size_bytes: int
    expanded_table_bytes: int
    header_line_sha256: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            type(self) is not Ib1b82qHeaderQuarter
            or type(self.period) is not str
            or re.fullmatch(r"20[0-9]{2}Q[1-4]", self.period) is None
            or type(self.zip_sha256) is not str
            or _SHA256.fullmatch(self.zip_sha256) is None
            or type(self.zip_size_bytes) is not int
            or not 0 < self.zip_size_bytes <= MAX_ARCHIVE_BYTES
            or type(self.expanded_table_bytes) is not int
            or not 0 < self.expanded_table_bytes <= MAX_TOTAL_PARSED_INPUT_BYTES
            or type(self.header_line_sha256) is not tuple
            or len(self.header_line_sha256) != len(ALLOWED_SEC_TABLES)
            or any(type(value) is not str or _SHA256.fullmatch(value) is None
                   for value in self.header_line_sha256)
        ):
            _refuse("quarter header receipt is malformed")

    def to_payload(self) -> dict[str, object]:
        self.__post_init__()
        return {
            "period": self.period,
            "zip_sha256": self.zip_sha256,
            "zip_size_bytes": self.zip_size_bytes,
            "expanded_table_bytes": self.expanded_table_bytes,
            "header_line_sha256_by_table": dict(zip(
                ALLOWED_SEC_TABLES, self.header_line_sha256, strict=True
            )),
        }


@dataclass(frozen=True)
class Ib1b82qHeaderPreflight:
    """In-memory aggregate with deliberately zero downstream authority."""

    scope: str
    census_sha256: str
    schema_profile_sha256: str
    quarters: tuple[Ib1b82qHeaderQuarter, ...]
    compressed_zip_bytes: int
    expanded_table_bytes: int
    _validated_quarters_sha256: str = field(repr=False, compare=False)
    _construction_token: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            type(self) is not Ib1b82qHeaderPreflight
            or type(self.scope) is not str
            or self.scope not in {
                "retained_noncanonical_header_preflight",
                "synthetic_test_header_preflight",
            }
            or type(self.census_sha256) is not str
            or _SHA256.fullmatch(self.census_sha256) is None
            or (self.scope == "retained_noncanonical_header_preflight"
                and self.census_sha256 != RETAINED_82Q_CENSUS_SHA256)
            or self.schema_profile_sha256 != RETAINED_82Q_SCHEMA_PROFILE_SHA256
            or type(self.quarters) is not tuple
            or len(self.quarters) != 82
            or any(type(item) is not Ib1b82qHeaderQuarter for item in self.quarters)
            or type(self.compressed_zip_bytes) is not int
            or type(self.expanded_table_bytes) is not int
        ):
            _refuse("82-quarter header preflight receipt is malformed")
        if (
            (self.scope == "retained_noncanonical_header_preflight"
             and self._construction_token is not _RETAINED_CONSTRUCTION_TOKEN)
            or (self.scope == "synthetic_test_header_preflight"
                and self._construction_token is not _SYNTHETIC_CONSTRUCTION_TOKEN)
        ):
            _refuse("82-quarter header preflight receipt is malformed")
        for quarter in self.quarters:
            quarter.__post_init__()
        expected_periods = tuple(
            f"{year}Q{quarter}"
            for year in range(2006, 2027)
            for quarter in range(1, 5)
            if (year, quarter) <= (2026, 2)
        )
        if (
            tuple(item.period for item in self.quarters) != expected_periods
            or self.compressed_zip_bytes != sum(item.zip_size_bytes for item in self.quarters)
            or self.expanded_table_bytes != sum(item.expanded_table_bytes for item in self.quarters)
            or type(self._validated_quarters_sha256) is not str
            or _SHA256.fullmatch(self._validated_quarters_sha256) is None
            or self._validated_quarters_sha256 != hash_payload(
                [item.to_payload() for item in self.quarters]
            )
        ):
            _refuse("82-quarter header inventory changed after validation")

    def to_payload(self) -> dict[str, object]:
        self.__post_init__()
        return {
            "kind": IB1B_82Q_HEADER_PREFLIGHT_KIND,
            "version": IB1B_82Q_HEADER_PREFLIGHT_VERSION,
            "scope": self.scope,
            "census_sha256": self.census_sha256,
            "schema_profile_sha256": self.schema_profile_sha256,
            "quarters": [item.to_payload() for item in self.quarters],
            "compressed_zip_bytes": self.compressed_zip_bytes,
            "expanded_table_bytes": self.expanded_table_bytes,
            "tables_per_quarter": len(ALLOWED_SEC_TABLES),
            "parser_run_performed": False,
            "row_keys_or_counts_verified_by_ib1b": False,
            "snapshot_written": False,
            "authority": {
                "sec_origin_authenticated": False,
                "quarter_population_complete": False,
                "complete_text_coverage_verified": False,
                "acceptance_metadata_coverage_verified": False,
                "canonical_evidence": False,
                "point_in_time_data": False,
                "outcome_access_authorized": False,
                "qc_job_authorized": False,
                "broker_or_trading_authorized": False,
                "research_looks": 0,
                "authorized_outcome_looks": 0,
                "consumed_outcome_looks": 0,
            },
        }

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


def _quarter_headers(raw: bytes, period: str, profile: SecTsvSchemaProfile) -> Ib1b82qHeaderQuarter:
    year, quarter = int(period[:4]), int(period[-1])
    hashes: list[str] = []
    expanded_bytes = 0
    try:
        with zipfile.ZipFile(io.BytesIO(raw), "r") as archive:
            names = [item.filename for item in archive.infolist()]
            if len(names) != len(set(names)) or any(table not in names for table in ALLOWED_SEC_TABLES):
                _refuse("ZIP does not contain each required table exactly once")
            for table in ALLOWED_SEC_TABLES:
                variant = profile.variant_for(table, year, quarter)
                expected = ("\t".join(variant.headers) + "\n").encode("ascii")
                info = archive.getinfo(table)
                if (
                    info.is_dir()
                    or info.file_size < len(expected)
                    or info.file_size > MAX_TOTAL_PARSED_INPUT_BYTES - expanded_bytes
                ):
                    _refuse("ZIP expanded table inventory exceeds unchanged IB-1B cap")
                with archive.open(info, "r") as member:
                    physical = member.readline(len(expected) + 1)
                if physical != expected:
                    _refuse("physical TSV header differs from retained 82-quarter profile")
                expanded_bytes += info.file_size
                hashes.append(hash_bytes(physical))
    except Ib1b82qOfflinePreflightError:
        raise
    except (zipfile.BadZipFile, KeyError, OSError, EOFError, RuntimeError,
            UnicodeError, ValueError) as exc:
        raise Ib1b82qOfflinePreflightError(
            "REFUSED: ZIP header inventory cannot be decoded"
        ) from exc
    return Ib1b82qHeaderQuarter(
        period=period, zip_sha256=hash_bytes(raw), zip_size_bytes=len(raw),
        expanded_table_bytes=expanded_bytes, header_line_sha256=tuple(hashes),
    )


def _preflight_ib1b_82q_headers(
    root: str | Path,
    census: SecZipCorpusCensus,
    profile: SecTsvSchemaProfile,
) -> Ib1b82qHeaderPreflight:
    """Private synthetic seam; retained scope is issued only by the public entry."""
    if type(census) is not SecZipCorpusCensus:
        _refuse("source-bound ZIP census must be exact")
    try:
        census.__post_init__()
        verify_retained_82q_schema_profile(profile)
    except (SecZipCorpusCensusError, ValueError) as exc:
        raise Ib1b82qOfflinePreflightError(
            "REFUSED: source census or header-only profile is invalid"
        ) from exc
    if census.scope == "retained_noncanonical_zip_census":
        if census.sha256 != RETAINED_82Q_CENSUS_SHA256:
            _refuse("retained ZIP census identity differs from the observed 82 quarters")
        scope = "retained_noncanonical_header_preflight"
    elif census.scope == "synthetic_test_census":
        scope = "synthetic_test_header_preflight"
    else:
        _refuse("ZIP census scope is unsupported")
    source = _plain_root(root)
    receipts: list[Ib1b82qHeaderQuarter] = []
    with _PinnedZipRoot(source) as pinned:
        expected_names = {f"{item.period.lower()}_form345.zip" for item in census.quarters}
        if {name for name in pinned.names() if name.endswith(".zip")} != expected_names:
            _refuse("ZIP inventory differs from the source-bound census")
        for item in census.quarters:
            raw = pinned.read(
                f"{item.period.lower()}_form345.zip",
                max_bytes=item.zip_size_bytes,
            )
            if len(raw) != item.zip_size_bytes or hash_bytes(raw) != item.zip_sha256:
                _refuse("ZIP fingerprint differs from the source-bound census")
            receipt = _quarter_headers(raw, item.period, profile)
            if receipt.header_line_sha256[0] != item.submission_header_line_sha256:
                _refuse("SUBMISSION physical header differs from census observation")
            receipts.append(receipt)
            del raw
    frozen = tuple(receipts)
    return Ib1b82qHeaderPreflight(
        scope=scope,
        census_sha256=census.sha256,
        schema_profile_sha256=RETAINED_82Q_SCHEMA_PROFILE_SHA256,
        quarters=frozen,
        compressed_zip_bytes=sum(item.zip_size_bytes for item in frozen),
        expanded_table_bytes=sum(item.expanded_table_bytes for item in frozen),
        _validated_quarters_sha256=hash_payload([item.to_payload() for item in frozen]),
        _construction_token=(
            _RETAINED_CONSTRUCTION_TOKEN
            if scope == "retained_noncanonical_header_preflight"
            else _SYNTHETIC_CONSTRUCTION_TOKEN
        ),
    )


def preflight_retained_ib1b_82q_headers(root: str | Path) -> Ib1b82qHeaderPreflight:
    """Read the exact retained corpus with no output file or downstream authority.

    An accepted result proves only that the 82 already-retained ZIPs still
    match the census and their eight headers fit the unreviewed profile and
    the unchanged per-quarter expanded-input cap. It does not run IB-1B.
    """
    census = census_retained_sec_zip_corpus(root)
    return _preflight_ib1b_82q_headers(
        root, census, build_retained_82q_schema_profile_candidate()
    )


__all__ = [
    "IB1B_82Q_HEADER_PREFLIGHT_KIND",
    "IB1B_82Q_HEADER_PREFLIGHT_VERSION",
    "RETAINED_82Q_CENSUS_SHA256",
    "Ib1b82qHeaderQuarter",
    "Ib1b82qHeaderPreflight",
    "Ib1b82qOfflinePreflightError",
    "preflight_retained_ib1b_82q_headers",
]
