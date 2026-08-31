"""Issuer-identity ambiguity detection over normalized ACER events.

The ACER-1 audit established that the ratings feed carries **no ISIN and no
exchange**, so a ticker is not a durable issuer key: FB has zero rows because
its history was re-keyed to META, ANTM kept its history through the same kind
of rename, and BBBY merges a dead retailer with an unrelated later reuse of
the symbol. Joining events to securities by raw ticker would silently assign
one company's ratings to another.

Resolving that fully needs an external security master. This module does the
half that does **not**: it measures, from the audited corpus alone, which
tickers carry name-based evidence of ambiguity. The resulting flags are a
diagnostic lower bound, never an allowlist: a ticker without a flag is not
established as safe, as the known BBBY false negative demonstrates. Nothing
here reaches a network, a price, or an outcome.

Two signals are computable from the vendor's own fields:

- **More than one company name under one ticker.** Split into date-ordered
  *name eras*, the gap between eras separates the two cases: a short gap
  looks like a rename (the same issuer, relabelled), a long gap looks like a
  reuse (a new issuer taking a freed symbol). Both are refused for a naive
  join; the report says which pattern it is.
- **One company name under more than one ticker.** That is the rename
  signature seen from the other side, and it means neither ticker alone
  identifies the issuer.

Company names are compared case-insensitively with collapsed whitespace and
nothing else. Punctuation and corporate suffixes (``Inc`` versus ``Inc.``,
``Corp`` versus ``Corporation``) are deliberately **not** aliased: deciding
that two spellings are the same issuer is a specification decision that
belongs to a reviewed security master, exactly as the rating scale belongs to
ACER-0. Under-merging here produces a refusal, which is safe; over-merging
would silently fuse two issuers, which is not.

The thresholds below are structural detection parameters, not research
parameters: they select which rows a human must adjudicate and never enter a
signal, a statistic, or a gate. Running this consumes no research look.
"""
from __future__ import annotations

import collections
import datetime as dt
import re
from dataclasses import dataclass
from typing import Any, Iterable

from ml.hashing import hash_payload
from research.acer.dataset import ValidatedDatasetIdentity

# A symbol freed by delisting is not normally reassigned quickly. A year of
# silence between two different company names under one ticker is the BBBY
# pattern (dead retailer, then an unrelated reuse); a short gap is the ANTM
# pattern (same issuer, new name). Both refuse; only the label differs.
REUSE_GAP_DAYS = 365

VERDICT_NO_AMBIGUITY_EVIDENCE = "no_name_based_ambiguity_evidence"
VERDICT_AMBIGUITY_EVIDENCE = "name_based_ambiguity_evidence"

IDENTITY_DIAGNOSTIC_KIND = "acer-issuer-identity-diagnostic"
IDENTITY_DIAGNOSTIC_CONTRACT_VERSION = 1
IDENTITY_DIAGNOSTIC_WARNING = (
    "Name-only diagnostic lower bound. A ticker without a flag is not "
    "established as unambiguous and must not be admitted without an external "
    "point-in-time security master."
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")

REASON_MULTIPLE_COMPANY_NAMES = "multiple_company_names_under_one_ticker"
REASON_LIKELY_REUSE = "name_change_after_long_gap_suggests_symbol_reuse"
REASON_LIKELY_RENAME = "name_change_after_short_gap_suggests_rename"
REASON_INTERLEAVED_NAMES = "company_names_interleave_rather_than_succeed"
REASON_NAME_SHARED_WITH_OTHER_TICKER = "company_name_also_used_by_another_ticker"
REASON_MISSING_COMPANY_NAME = "events_without_a_company_name"


def comparison_name(value: Any) -> str | None:
    """Conservative comparison key: case and whitespace only, never aliases."""
    if not isinstance(value, str):
        return None
    return " ".join(value.split()).casefold() or None


@dataclass(frozen=True)
class NameEra:
    """A maximal run of consecutive events sharing one company name."""

    company_name: str
    first_action_date: str
    last_action_date: str
    event_count: int

    def to_payload(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class TickerIdentity:
    """What the corpus alone can say about one ticker's issuer identity."""

    ticker: str
    event_count: int
    first_action_date: str
    last_action_date: str
    distinct_company_names: int
    events_without_company_name: int
    name_eras: tuple[NameEra, ...]
    max_era_gap_days: int | None
    shared_names_with: tuple[str, ...]
    verdict: str
    reasons: tuple[str, ...]

    @property
    def has_ambiguity_evidence(self) -> bool:
        return self.verdict == VERDICT_AMBIGUITY_EVIDENCE

    def to_payload(self) -> dict[str, Any]:
        payload = {name: getattr(self, name) for name in self.__dataclass_fields__}
        payload["name_eras"] = [era.to_payload() for era in self.name_eras]
        payload["shared_names_with"] = list(self.shared_names_with)
        payload["reasons"] = list(self.reasons)
        return payload


def _eras_for(events: list[tuple[str, str | None]]) -> tuple[list[NameEra], int]:
    """Collapse date-ordered (date, name) pairs into maximal same-name runs.

    Returns the eras and the count of events carrying no company name. Events
    without a name never open or extend an era: an unnamed row cannot testify
    to identity in either direction.
    """
    eras: list[NameEra] = []
    unnamed = 0
    current_key: str | None = None
    current: list[Any] | None = None
    for action_date, raw_name in events:
        key = comparison_name(raw_name)
        if key is None:
            unnamed += 1
            continue
        if key != current_key:
            if current is not None:
                eras.append(
                    NameEra(
                        company_name=current[0],
                        first_action_date=current[1],
                        last_action_date=current[2],
                        event_count=current[3],
                    )
                )
            current_key = key
            current = [str(raw_name).strip(), action_date, action_date, 1]
        else:
            assert current is not None
            current[2] = action_date
            current[3] += 1
    if current is not None:
        eras.append(
            NameEra(
                company_name=current[0],
                first_action_date=current[1],
                last_action_date=current[2],
                event_count=current[3],
            )
        )
    return eras, unnamed


def comparison_ticker(value: Any) -> str:
    """Return the canonical comparison key for a validated ticker.

    Ticker case is presentation, not issuer identity. Keeping ``case`` and
    ``CASE`` in separate buckets would create an unsafe false negative.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError("ticker must be a non-empty string")
    return value.strip().upper()


def _gap_days(earlier: str, later: str) -> int:
    return (dt.date.fromisoformat(later) - dt.date.fromisoformat(earlier)).days


def assess_identities(events: Iterable[Any]) -> list[TickerIdentity]:
    """Assess every ticker in a normalized event corpus.

    Accepts ``NormalizedEvent`` objects or any object exposing ``ticker``,
    ``action_date`` and ``company_name``. Output is ordered by ticker so the
    report is deterministic.
    """
    by_ticker: dict[str, list[tuple[str, str | None]]] = collections.defaultdict(list)
    for event in events:
        ticker = comparison_ticker(event.ticker)
        action_date = event.action_date
        if not isinstance(action_date, str):
            raise ValueError("action_date must be an ISO date string")
        try:
            dt.date.fromisoformat(action_date)
        except ValueError as exc:
            raise ValueError("action_date must be an ISO date string") from exc
        by_ticker[ticker].append((action_date, event.company_name))

    # First pass: eras per ticker, and which tickers each company name touches.
    eras_by_ticker: dict[str, list[NameEra]] = {}
    unnamed_by_ticker: dict[str, int] = {}
    tickers_by_name: dict[str, set[str]] = collections.defaultdict(set)
    for ticker, rows in by_ticker.items():
        # Same-day vendor ids do not establish event chronology. Include the
        # conservative name key in the sort so page/order changes cannot alter
        # era counts, interleaving reasons, or the diagnostic content hash.
        rows.sort(
            key=lambda row: (
                row[0],
                comparison_name(row[1]) or "",
                str(row[1] or ""),
            )
        )
        eras, unnamed = _eras_for(rows)
        eras_by_ticker[ticker] = eras
        unnamed_by_ticker[ticker] = unnamed
        for era in eras:
            key = comparison_name(era.company_name)
            if key is not None:
                tickers_by_name[key].add(ticker)

    identities: list[TickerIdentity] = []
    for ticker in sorted(by_ticker):
        rows = by_ticker[ticker]
        eras = eras_by_ticker[ticker]
        unnamed = unnamed_by_ticker[ticker]
        reasons: list[str] = []

        distinct_keys = {
            key
            for key in (comparison_name(era.company_name) for era in eras)
            if key is not None
        }
        max_gap: int | None = None
        if len(eras) > 1:
            gaps = [
                _gap_days(a.last_action_date, b.first_action_date)
                for a, b in zip(eras, eras[1:])
            ]
            max_gap = max(gaps)

        if len(distinct_keys) > 1:
            reasons.append(REASON_MULTIPLE_COMPANY_NAMES)
            if max_gap is not None and max_gap >= REUSE_GAP_DAYS:
                reasons.append(REASON_LIKELY_REUSE)
            else:
                reasons.append(REASON_LIKELY_RENAME)
        if len(eras) > len(distinct_keys):
            # A name recurs after a different one: the vendor is alternating
            # labels rather than recording a clean succession.
            reasons.append(REASON_INTERLEAVED_NAMES)

        shared: set[str] = set()
        for key in distinct_keys:
            shared.update(tickers_by_name[key] - {ticker})
        if shared:
            reasons.append(REASON_NAME_SHARED_WITH_OTHER_TICKER)

        if unnamed:
            reasons.append(REASON_MISSING_COMPANY_NAME)

        identities.append(
            TickerIdentity(
                ticker=ticker,
                event_count=len(rows),
                first_action_date=rows[0][0],
                last_action_date=rows[-1][0],
                distinct_company_names=len(distinct_keys),
                events_without_company_name=unnamed,
                name_eras=tuple(eras),
                max_era_gap_days=max_gap,
                shared_names_with=tuple(sorted(shared)),
                verdict=(
                    VERDICT_AMBIGUITY_EVIDENCE
                    if reasons
                    else VERDICT_NO_AMBIGUITY_EVIDENCE
                ),
                reasons=tuple(reasons),
            )
        )
    return identities


def diagnostic_flagged_tickers(
    identities: Iterable[TickerIdentity],
) -> tuple[str, ...]:
    """Name-flagged tickers; deliberately not a security-master allowlist."""
    return tuple(
        sorted(item.ticker for item in identities if item.has_ambiguity_evidence)
    )


def summarize_identities(identities: list[TickerIdentity]) -> dict[str, Any]:
    """Counting only. No outcome, return, or ranking is computed here."""
    reason_counts: collections.Counter = collections.Counter()
    ambiguous_events = 0
    total_events = 0
    for item in identities:
        total_events += item.event_count
        if item.has_ambiguity_evidence:
            ambiguous_events += item.event_count
            for reason in item.reasons:
                reason_counts[reason] += 1
    ambiguous = [item for item in identities if item.has_ambiguity_evidence]
    return {
        "tickers": len(identities),
        "tickers_with_name_based_ambiguity_evidence": len(ambiguous),
        "tickers_without_name_based_ambiguity_evidence": (
            len(identities) - len(ambiguous)
        ),
        "events": total_events,
        "events_under_name_flagged_tickers": ambiguous_events,
        "share_of_events_flagged_by_name_evidence": (
            ambiguous_events / total_events if total_events else 0.0
        ),
        "tickers_by_reason": dict(sorted(reason_counts.items())),
    }


def build_diagnostic_report(
    identities: list[TickerIdentity],
    *,
    code_commit: str,
    normalized_dataset_identity: ValidatedDatasetIdentity,
) -> dict[str, Any]:
    """Bind a diagnostic measurement to exact source and code lineage."""
    if not isinstance(code_commit, str) or not _COMMIT_RE.fullmatch(code_commit):
        raise ValueError("code_commit must be one canonical Git commit hash")
    if type(normalized_dataset_identity) is not ValidatedDatasetIdentity:
        raise ValueError(
            "normalized_dataset_identity must come from the strict typed loader"
        )
    dataset_id = normalized_dataset_identity.dataset_id
    contract_version = normalized_dataset_identity.contract_version
    snapshot_name = normalized_dataset_identity.source_snapshot_name
    manifest_hash = normalized_dataset_identity.source_manifest_sha256
    event_count = normalized_dataset_identity.event_count
    ordered_identities = sorted(identities, key=lambda item: item.ticker)
    tickers = [item.ticker for item in ordered_identities]
    if len(tickers) != len(set(tickers)):
        raise ValueError("identity assessment contains duplicate tickers")
    summary = summarize_identities(ordered_identities)
    if event_count != summary["events"]:
        raise ValueError("identity assessment does not cover the normalized dataset")
    assessment_payloads = [item.to_payload() for item in ordered_identities]
    return {
        "kind": IDENTITY_DIAGNOSTIC_KIND,
        "contract_version": IDENTITY_DIAGNOSTIC_CONTRACT_VERSION,
        "code_commit": code_commit,
        "normalized_dataset_id": dataset_id,
        "normalization_contract_version": contract_version,
        "source_snapshot_name": snapshot_name,
        "source_manifest_sha256": manifest_hash,
        "normalized_content_hash": normalized_dataset_identity.content_hash,
        "normalized_events_sha256": normalized_dataset_identity.events_sha256,
        "normalized_refusals_sha256": normalized_dataset_identity.refusals_sha256,
        "identity_assessments_sha256": hash_payload(assessment_payloads),
        "warning": IDENTITY_DIAGNOSTIC_WARNING,
        "summary": summary,
    }
