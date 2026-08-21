"""Check ACER-2's data requirements against what this repository actually has.

Three rounds of ACER review found the same failure in my own prose: a claim
about what this repository contains, asserted from a partial look and
contradicted by code that was already here. The local-data audit called
yfinance the sole price source while ~130KB of reviewed Databento capture
code sat in `ml/`; a signal measurement approximated trading sessions as
`calendar_days * 252/365` while `pandas_market_calendars` was pinned in
`requirements.txt` and already used by `data/market_data.py`.

So this module replaces the assertion with a check. Each ACER-2 data
requirement is resolved by reading a contract, an import, or a pinned
dependency, and the finding carries the evidence it read. Re-running it is
cheap, and a capability that silently disappears turns a finding from
`AVAILABLE` to `UNAVAILABLE` instead of quietly leaving a stale sentence in a
document.

Boundaries, which are the point of putting this in `research/acer/`:

- **No network call and no vendor contact.** Availability is decided from
  code and configuration, never by hitting an API.
- **No credential is read or reported.** Presence of a key is deliberately
  not treated as capability, because a key proves nothing about coverage.
- **`UNMEASURED` is a real answer**, distinct from `UNAVAILABLE`. Databento
  capture code exists and has never been exercised for ACER; calling that
  either "available" or "unavailable" would be a claim nobody has earned.
"""
from __future__ import annotations

import importlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

STATUS_AVAILABLE = "available"
STATUS_UNAVAILABLE = "unavailable"
STATUS_UNMEASURED = "unmeasured"

_VALID_STATUSES = frozenset(
    {STATUS_AVAILABLE, STATUS_UNAVAILABLE, STATUS_UNMEASURED}
)

_REQ_SESSION_CALENDAR = "NYSE trading-session calendar"
_REQ_PIT_PRICES = "point-in-time daily bars (production read path)"
_REQ_DATABENTO = "Databento point-in-time bars and reference"
_REQ_DELISTING_RETURNS = "terminal returns for delisted securities"
_REQ_ISSUER_IDENTITY = "durable point-in-time issuer identity"
_REQ_VALUE_CONTROL = "book-to-market value control"
_REQ_SECTOR = "sector classification (ACER-0A.7 proposes GICS)"
_REQ_EARNINGS_SURPRISE = "point-in-time earnings-surprise control"

_REQUIRED_REQUIREMENTS = frozenset(
    {
        _REQ_SESSION_CALENDAR,
        _REQ_PIT_PRICES,
        _REQ_DATABENTO,
        _REQ_DELISTING_RETURNS,
        _REQ_ISSUER_IDENTITY,
        _REQ_VALUE_CONTROL,
        _REQ_SECTOR,
        _REQ_EARNINGS_SURPRISE,
    }
)

# ACER-0A.7 names eight controls. Five of them -- momentum, size, liquidity,
# volatility, and analyst coverage -- are arithmetic over point-in-time prices,
# share counts, and the ratings corpus itself, so they carry no data
# requirement beyond `_REQ_PIT_PRICES` and the already-audited corpus. The
# three that need their own source are value, sector, and earnings surprise,
# and each has its own check below. This mapping is written down because the
# summary refuses anything but the *complete* set, and a checklist that
# asserts completeness while omitting a frozen control makes the omission
# harder to notice rather than easier.
_CONTROLS_COVERED_BY_PRICES = (
    "momentum",
    "size",
    "liquidity",
    "volatility",
    "analyst coverage",
)


@dataclass(frozen=True)
class CapabilityFinding:
    """One ACER-2 data requirement and what the repository can actually do.

    ``blocks_acer2`` is deliberately separate from ``status``: an
    ``UNMEASURED`` requirement blocks just as firmly as an ``UNAVAILABLE``
    one, because a study may not run on a capability nobody has verified.
    """

    requirement: str
    status: str
    evidence: str
    blocks_acer2: bool

    def __post_init__(self) -> None:
        if self.status not in _VALID_STATUSES:
            raise ValueError(f"unknown status {self.status!r}")
        if not self.evidence.strip():
            raise ValueError(
                f"{self.requirement}: a finding must carry the evidence it read"
            )
        if self.status == STATUS_AVAILABLE and self.blocks_acer2:
            raise ValueError(
                f"{self.requirement}: an available capability cannot block"
            )
        if self.status != STATUS_AVAILABLE and not self.blocks_acer2:
            raise ValueError(
                f"{self.requirement}: a non-available requirement must block"
            )

    def to_payload(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


def _read(relative: str) -> str:
    path = REPO_ROOT / relative
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _pinned(package: str) -> str | None:
    """Return the pinned version of a requirement, or None if unpinned."""
    pattern = re.compile(
        rf"^{re.escape(package)}\s*==\s*([^\s#]+)", re.IGNORECASE | re.MULTILINE
    )
    match = pattern.search(_read("requirements.txt"))
    return match.group(1) if match else None


def check_trading_session_calendar() -> CapabilityFinding:
    """ACER counts decay, outcome horizon, and folds in trading sessions."""
    version = _pinned("pandas_market_calendars")
    try:
        calendar_module = importlib.import_module("pandas_market_calendars")
        calendar_module.get_calendar("NYSE")
    except (ImportError, AttributeError, RuntimeError, ValueError):
        importable = False
    else:
        importable = True
    used = 'mcal.get_calendar("NYSE")' in _read("data/market_data.py")
    if version and importable and used:
        return CapabilityFinding(
            requirement=_REQ_SESSION_CALENDAR,
            status=STATUS_AVAILABLE,
            evidence=(
                f"pandas_market_calendars=={version} pinned and importable; "
                'data/market_data.py builds mcal.get_calendar("NYSE")'
            ),
            blocks_acer2=False,
        )
    return CapabilityFinding(
        requirement=_REQ_SESSION_CALENDAR,
        status=STATUS_UNAVAILABLE,
        evidence=(
            f"pinned={version!r} importable={importable} "
            f"used_in_market_data={used}"
        ),
        blocks_acer2=True,
    )


def check_point_in_time_prices() -> CapabilityFinding:
    """The production read-path provider declares its own PIT status."""
    source = _read("data/price_source.py")
    declares_not_pit = "provides_point_in_time_lineage = False" in source
    if declares_not_pit:
        return CapabilityFinding(
            requirement=_REQ_PIT_PRICES,
            status=STATUS_UNAVAILABLE,
            evidence=(
                "data/price_source.py: YFinanceDailyBars declares "
                "provides_point_in_time_lineage = False; its bars are "
                "adjusted as of fetch date"
            ),
            blocks_acer2=True,
        )
    return CapabilityFinding(
        requirement=_REQ_PIT_PRICES,
        status=STATUS_UNMEASURED,
        evidence=(
            "data/price_source.py no longer declares "
            "provides_point_in_time_lineage = False; re-verify before use"
        ),
        blocks_acer2=True,
    )


def check_databento_path() -> CapabilityFinding:
    """Capture code exists; coverage for ACER has never been exercised.

    Credential presence is deliberately NOT consulted. A key proves access,
    not history depth, delisted coverage, or terminal-return semantics, and
    treating it as capability is how an unmeasured path gets called ready.
    """
    modules = (
        "ml/databento_source.py",
        "ml/databento_pit.py",
        "ml/databento_authoritative.py",
    )
    present = [name for name in modules if (REPO_ROOT / name).is_file()]
    captured = (REPO_ROOT / "artifacts" / "databento").is_dir()
    if not present:
        return CapabilityFinding(
            requirement=_REQ_DATABENTO,
            status=STATUS_UNAVAILABLE,
            evidence="no ml/databento_*.py modules found",
            blocks_acer2=True,
        )
    return CapabilityFinding(
        requirement=_REQ_DATABENTO,
        status=STATUS_UNMEASURED,
        evidence=(
            f"{len(present)} capture modules present ({', '.join(present)}); "
            f"artifacts/databento present={captured}; history depth, delisted "
            "coverage, terminal-return semantics, licence and cost are "
            "unaudited for ACER"
        ),
        blocks_acer2=True,
    )


def check_delisting_returns() -> CapabilityFinding:
    """The universe rule keeps delisted names; the outcome needs their return."""
    source = _read("data/pit_universe.py")
    states_missing = "No delisting returns" in source
    return CapabilityFinding(
        requirement=_REQ_DELISTING_RETURNS,
        status=STATUS_UNAVAILABLE if states_missing else STATUS_UNMEASURED,
        evidence=(
            "data/pit_universe.py states 'No delisting returns, so a company "
            "that leaves the universe leaves without a final return'"
            if states_missing
            else "data/pit_universe.py no longer states the delisting-return "
            "limitation; re-verify before relying on it"
        ),
        blocks_acer2=True,
    )


def check_durable_issuer_identity() -> CapabilityFinding:
    """EDGAR CIK is durable, but its ticker map omits dead issuers."""
    source = _read("data/pit_universe.py")
    cik_primary = "`cik` is the primary key, never the ticker" in source
    current_only = "still have a listed ticker today" in source
    if cik_primary and current_only:
        return CapabilityFinding(
            requirement=_REQ_ISSUER_IDENTITY,
            status=STATUS_UNMEASURED,
            evidence=(
                "data/pit_universe.py keys on CIK, but fetch_ticker_map covers "
                "only companies that 'still have a listed ticker today', so "
                "delisted issuers are unresolved"
            ),
            blocks_acer2=True,
        )
    return CapabilityFinding(
        requirement=_REQ_ISSUER_IDENTITY,
        status=STATUS_UNMEASURED,
        evidence=(
            f"data/pit_universe.py cik_primary={cik_primary} "
            f"current_ticker_map_only={current_only}; re-verify"
        ),
        blocks_acer2=True,
    )


def check_value_control_source() -> CapabilityFinding:
    """ACER-0A.7 proposes a book-to-market control."""
    hits = [
        name
        for name in ("book_value", "bookValue", "shareholders_equity", "book_to_market")
        for module in Path(REPO_ROOT / "data").glob("*.py")
        if name in module.read_text(encoding="utf-8", errors="ignore")
    ]
    if hits:
        return CapabilityFinding(
            requirement=_REQ_VALUE_CONTROL,
            status=STATUS_UNMEASURED,
            evidence=f"candidate fields found under data/: {sorted(set(hits))}",
            blocks_acer2=True,
        )
    return CapabilityFinding(
        requirement=_REQ_VALUE_CONTROL,
        status=STATUS_UNAVAILABLE,
        evidence="no book-value or shareholders-equity field in any data/ module",
        blocks_acer2=True,
    )


def check_sector_classification() -> CapabilityFinding:
    """ACER-0A.7 proposes GICS; only SIC is available."""
    source = _read("data/pit_universe.py")
    sic = "SIC codes are the sector proxy" in source
    return CapabilityFinding(
        requirement=_REQ_SECTOR,
        status=STATUS_UNAVAILABLE if sic else STATUS_UNMEASURED,
        evidence=(
            "data/pit_universe.py: 'SIC codes are the sector proxy' — SIC is "
            "not GICS, and substituting one for the other silently would be a "
            "specification change"
            if sic
            else "no sector source identified under data/"
        ),
        blocks_acer2=True,
    )


def check_earnings_surprise_control() -> CapabilityFinding:
    """ACER-0A.7 requires a point-in-time standardized earnings surprise.

    `data/earnings_data.py` does supply an earnings history, but it reads
    yfinance and exposes the vendor's own `surprise_pct`. That fails the
    requirement twice over: the provider is pinned `point_in_time_data=false`
    across this repository, and ACER-0A.5's proposal explicitly declines to
    trust a vendor-computed surprise percentage, requiring actual and
    estimated EPS to be preserved so this project can freeze its own formula.
    """
    source = _read("data/earnings_data.py")
    if not source:
        return CapabilityFinding(
            requirement=_REQ_EARNINGS_SURPRISE,
            status=STATUS_UNAVAILABLE,
            evidence="no data/earnings_data.py module found",
            blocks_acer2=True,
        )
    vendor_percentage = "surprise_pct" in source
    yfinance_backed = "yfinance" in source
    return CapabilityFinding(
        requirement=_REQ_EARNINGS_SURPRISE,
        status=STATUS_UNAVAILABLE,
        evidence=(
            "data/earnings_data.py is yfinance-backed="
            f"{yfinance_backed} and exposes the vendor percentage "
            f"surprise_pct={vendor_percentage}; ACER-0A.2 requires a "
            "point-in-time estimate available before the report and a "
            "surprise formula frozen by this project, neither of which this "
            "module supplies"
        ),
        blocks_acer2=True,
    )


_CHECKS = (
    check_trading_session_calendar,
    check_point_in_time_prices,
    check_databento_path,
    check_delisting_returns,
    check_durable_issuer_identity,
    check_value_control_source,
    check_sector_classification,
    check_earnings_surprise_control,
)


def assess_capabilities() -> list[CapabilityFinding]:
    """Run every check. Output order is the declaration order, not sorted."""
    return [check() for check in _CHECKS]


def summarize_capabilities(findings: list[CapabilityFinding]) -> dict[str, Any]:
    """Summarize one complete ACER-2 checklist, never a caller-selected subset."""
    requirements = [finding.requirement for finding in findings]
    if (
        len(requirements) != len(_REQUIRED_REQUIREMENTS)
        or set(requirements) != _REQUIRED_REQUIREMENTS
    ):
        raise ValueError(
            "findings must contain the complete ACER-2 requirement set "
            "exactly once"
        )
    blocking = [f for f in findings if f.blocks_acer2]
    return {
        "requirements": len(findings),
        "available": sum(1 for f in findings if f.status == STATUS_AVAILABLE),
        "unavailable": sum(1 for f in findings if f.status == STATUS_UNAVAILABLE),
        "unmeasured": sum(1 for f in findings if f.status == STATUS_UNMEASURED),
        "blocking": len(blocking),
        "acer2_runnable": not blocking,
        "blocking_requirements": [f.requirement for f in blocking],
    }
