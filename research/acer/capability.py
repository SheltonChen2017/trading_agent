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
_REQ_RATINGS_CORPUS = "verified normalized analyst-ratings event corpus"
_REQ_PIT_PRICES = "point-in-time daily bars (production read path)"
_REQ_DATABENTO = "Databento point-in-time bars and reference"
_REQ_DELISTING_RETURNS = "terminal returns for delisted securities"
_REQ_ISSUER_IDENTITY = "durable point-in-time issuer identity"
_REQ_SECURITY_ELIGIBILITY = (
    "point-in-time security type and primary-listing eligibility"
)
_REQ_CORPORATE_ACTIONS = (
    "point-in-time corporate actions for total-return outcomes"
)
_REQ_SIZE_CONTROL = (
    "point-in-time shares outstanding for log market-cap size control"
)
_REQ_VALUE_CONTROL = "book-to-market value control"
_REQ_SECTOR = "point-in-time sector classification (taxonomy not yet frozen)"
_REQ_EARNINGS_SURPRISE = "point-in-time earnings-surprise control"

_REQUIRED_REQUIREMENTS = frozenset(
    {
        _REQ_SESSION_CALENDAR,
        _REQ_RATINGS_CORPUS,
        _REQ_PIT_PRICES,
        _REQ_DATABENTO,
        _REQ_DELISTING_RETURNS,
        _REQ_ISSUER_IDENTITY,
        _REQ_SECURITY_ELIGIBILITY,
        _REQ_CORPORATE_ACTIONS,
        _REQ_SIZE_CONTROL,
        _REQ_VALUE_CONTROL,
        _REQ_SECTOR,
        _REQ_EARNINGS_SURPRISE,
    }
)

# The owner-frozen control contract lives here. The later completion document
# contains candidate formulas and taxonomies, but the governing freeze says
# explicitly that those proposals are not owner decisions.
_CONTROL_CONTRACT_PATH = "docs/research/ACER_2026-08-20_ACER0A_FREEZE.md"

# Every owner-frozen control, mapped to the exact declared data requirements
# it consumes. This is dependency accounting, not explanatory prose: every
# value is a set of members of `_REQUIRED_REQUIREMENTS`, so an arbitrary claim
# such as "derived from prices" cannot satisfy the guard. Size needs both a
# price and point-in-time shares; analyst coverage comes from the ratings
# corpus, not from prices.
#
# Tests derive the names from `_CONTROL_CONTRACT_PATH` and assert the entire
# dependency map exactly. This guards both dimensions that failed in the
# submitted counter-review: the authority being read and what each control
# actually depends on.
_CONTROL_ACCOUNTING = {
    "momentum": frozenset({_REQ_PIT_PRICES}),
    "liquidity": frozenset({_REQ_PIT_PRICES}),
    "volatility": frozenset({_REQ_PIT_PRICES}),
    "analyst coverage": frozenset({_REQ_RATINGS_CORPUS}),
    "size": frozenset({_REQ_PIT_PRICES, _REQ_SIZE_CONTROL}),
    "value": frozenset({_REQ_VALUE_CONTROL}),
    "sector": frozenset({_REQ_SECTOR}),
    "earnings surprise": frozenset({_REQ_EARNINGS_SURPRISE}),
}


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


def check_ratings_event_corpus() -> CapabilityFinding:
    """ACER's signal input must be a verified, normalized local dataset.

    The committed code proves that a fail-closed build/load path exists. It
    does not prove that the execution environment contains the licensed raw
    snapshot and a canonical normalized dataset whose hashes verify, so the
    capability remains unmeasured until the run preflight loads that identity.
    No licensed row or credential is read here.
    """
    modules = (
        "research/acer/snapshot.py",
        "research/acer/normalize.py",
        "research/acer/dataset.py",
    )
    present = [name for name in modules if (REPO_ROOT / name).is_file()]
    dataset_root = (REPO_ROOT / "artifacts" / "acer_datasets").is_dir()
    if len(present) != len(modules):
        return CapabilityFinding(
            requirement=_REQ_RATINGS_CORPUS,
            status=STATUS_UNAVAILABLE,
            evidence=f"required ratings pipeline modules present={present}",
            blocks_acer2=True,
        )
    return CapabilityFinding(
        requirement=_REQ_RATINGS_CORPUS,
        status=STATUS_UNMEASURED,
        evidence=(
            "verified snapshot, normalization, and content-addressed dataset "
            "modules are present; artifacts/acer_datasets "
            f"present={dataset_root}; "
            "no canonical normalized dataset identity was loaded by this "
            "network-free, licensed-row-free check"
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


def check_point_in_time_security_eligibility() -> CapabilityFinding:
    """ACER admits only historical US primary-listed common stocks.

    A durable issuer key answers *which company* a row belongs to. It does not
    answer whether the historical instrument was the primary listing or an
    ETF, fund, preferred share, warrant, ADR, or OTC security. ACER-0A.10
    requires those security semantics as a separate point-in-time input.
    """
    universe_source = _read("data/pit_universe.py")
    if not universe_source:
        return CapabilityFinding(
            requirement=_REQ_SECURITY_ELIGIBILITY,
            status=STATUS_UNAVAILABLE,
            evidence="no point-in-time security eligibility source found",
            blocks_acer2=True,
        )
    current_ticker_map = "still have a listed ticker today" in universe_source
    states_missing = "security-type screens" in universe_source
    return CapabilityFinding(
        requirement=_REQ_SECURITY_ELIGIBILITY,
        status=STATUS_UNAVAILABLE if states_missing else STATUS_UNMEASURED,
        evidence=(
            "data/pit_universe.py explicitly states that it does not apply "
            "venue or security-type screens; "
            f"current_ticker_map_only={current_ticker_map}"
            if states_missing
            else "no point-in-time security-type/primary-listing source is "
            "bound; re-verify before use"
        ),
        blocks_acer2=True,
    )


def check_point_in_time_corporate_actions() -> CapabilityFinding:
    """The frozen open-to-open outcome is a split/dividend total return."""
    modules = (
        "ml/databento_pit.py",
        "ml/databento_authoritative.py",
        "data/corporate_actions.py",
    )
    present = [name for name in modules if (REPO_ROOT / name).is_file()]
    local_artifact = (REPO_ROOT / "artifacts" / "databento").is_dir()
    if not present:
        return CapabilityFinding(
            requirement=_REQ_CORPORATE_ACTIONS,
            status=STATUS_UNAVAILABLE,
            evidence="no corporate-action or point-in-time adjustment module found",
            blocks_acer2=True,
        )
    return CapabilityFinding(
        requirement=_REQ_CORPORATE_ACTIONS,
        status=STATUS_UNMEASURED,
        evidence=(
            f"candidate modules present ({', '.join(present)}); "
            f"artifacts/databento present={local_artifact}; ACER coverage, "
            "as-of semantics, dividend cash treatment, and split adjustment "
            "have not been audited"
        ),
        blocks_acer2=True,
    )


def check_size_control_source() -> CapabilityFinding:
    """The frozen size control is log market cap, not price alone."""
    source = _read("data/pit_universe.py")
    has_share_tag = "EntityCommonStockSharesOutstanding" in source
    respects_availability = 'shares["known_from"] <= as_of' in source
    current_identity_hole = "still have a listed ticker today" in source
    if not (has_share_tag and respects_availability):
        return CapabilityFinding(
            requirement=_REQ_SIZE_CONTROL,
            status=STATUS_UNAVAILABLE,
            evidence=(
                f"EDGAR shares tag present={has_share_tag} and "
                f"known-from filter present={respects_availability}"
            ),
            blocks_acer2=True,
        )
    return CapabilityFinding(
        requirement=_REQ_SIZE_CONTROL,
        status=STATUS_UNMEASURED,
        evidence=(
            "data/pit_universe.py has filing-date-filtered EDGAR shares "
            "outstanding, but ACER coverage is unmeasured and the join still "
            f"uses a current-only ticker map={current_identity_hole}"
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
    """A local SIC candidate exists, but the taxonomy is not owner-frozen."""
    source = _read("data/pit_universe.py")
    sic = "SIC codes are the sector proxy" in source
    return CapabilityFinding(
        requirement=_REQ_SECTOR,
        status=STATUS_UNMEASURED if sic else STATUS_UNAVAILABLE,
        evidence=(
            "data/pit_universe.py supplies SIC as a candidate sector proxy; "
            "ACER-0A.7's GICS choice remains an unaccepted proposal, so the "
            "taxonomy cannot be promoted to available or rejected as wrong"
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
    check_ratings_event_corpus,
    check_point_in_time_prices,
    check_databento_path,
    check_delisting_returns,
    check_durable_issuer_identity,
    check_point_in_time_security_eligibility,
    check_point_in_time_corporate_actions,
    check_size_control_source,
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
