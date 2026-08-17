"""Deterministic acceptance rules for committee output."""
from __future__ import annotations

import dataclasses
import re

from assistant.ai_advisor import (
    _contains_action_language,
    _mentions_unknown_ticker,
    _unsupported_numbers,
)
from assistant.llm.schemas import (
    CommitteeInput,
    CommitteeReview,
    ConfidenceLabel,
    FactAvailability,
    Verdict,
)

_SOURCE_TICKER_PATTERN = re.compile(r"\b[A-Z]{1,5}\b")

# Committee prose has a formal third-person register that the shared advisor
# filter does not cover well.  Keep this second layer scoped to directive
# *framing* rather than allocation vocabulary alone: words such as "reduction"
# and "smaller" are also needed for neutral descriptions of the candidate and
# its measured effects.
_COMMITTEE_DIRECTIVE_PATTERN = re.compile(
    r"\b(?:"
    r"best\s+brought\s+down\b|"
    r"the\s+appropriate\s+response\b.{0,80}?\b(?:smaller|less|lower|lighter)\b|"
    r"the\s+evidence\s+points\s+toward\s+(?:paring|lightening|reducing)\b|"
    r"the\s+committee\s+endorses\b.{0,80}?\b(?:lighter|smaller|less|lower)\b|"
    r"the\s+committee\s+sees\s+a\s+case\s+for\s+(?:unwinding|paring|reducing)\b|"
    r"the\s+committee(?:'s)?\s+recommendation\b.{0,80}?\b(?:smaller|lighter|less|lower)\b|"
    r"the\s+indicated\s+course\b.{0,80}?\b(?:lighten|reduce|pare|unwind)\b|"
    r"the\s+natural\s+remedy\b.{0,80}?\b(?:sale|reduction|smaller|lighter)\b|"
    r"corrective\s+action\b|"
    r"the\s+data\s+supports\s+stepping\s+back\b|"
    r"better\s+served\s+by\s+less\b|"
    r"\breduction\s+in\b.{0,40}?\b(?:holding|position|allocation|exposure)\b"
    r".{0,60}?\bfollows\s+from\b|"
    r"\bbringing\b.{0,60}?\bcloser\s+to\s+target\b|"
    r"\brightsizing\b.{0,60}?\bwould\s+resolve\b"
    r")",
    re.IGNORECASE,
)


def _contains_committee_action_language(
    text: str, allowed_tickers: set[str]
) -> bool:
    """Reject advisor-style actions and committee-specific directives.

    This remains a deterministic presentation filter, not a semantic proof
    that arbitrary prose contains no advice.  The committee is still bounded
    by its read-only architecture and mandatory human approval/revalidation.
    """

    return bool(
        _contains_action_language(text, allowed_tickers)
        or _COMMITTEE_DIRECTIVE_PATTERN.search(text)
    )


@dataclasses.dataclass(frozen=True)
class ValidationIssue:
    code: str
    path: str
    message: str


@dataclasses.dataclass(frozen=True)
class ValidationReport:
    accepted: bool
    issues: tuple[ValidationIssue, ...]


def validate_committee_review(
    committee_input: CommitteeInput, review: CommitteeReview
) -> ValidationReport:
    """Fail closed on unsupported sources, figures, tickers, or authority.

    Numeric and ticker validation is citation-scoped: a number or ticker is
    not licensed merely because it appeared somewhere else in the packet.  It
    must appear in at least one source cited by that exact point.

    MEASURED LIMITATION -- action-language checking is a presentation filter,
    NOT the safety boundary (2026-07-30).  The shared advisor filter originally
    missed 14 of 24 directives written in formal committee voice.  A separate
    committee-specific layer now rejects all 24 measured directives while
    preserving the descriptive corpus, including neutral descriptions of the
    candidate's weight change and drawdown effects.  See
    tests/test_committee_action_language_probe.py.

    This is still lexical enforcement over free prose.  It cannot prove the
    absence of every semantically equivalent recommendation, and passing the
    probe must not be represented as such a proof.  A future constrained
    output surface would reduce that residual ambiguity further.

    What actually contains the risk is architectural, per
    docs/architecture/ADR_INVESTMENT_COMMITTEE_BOUNDARY.md: the committee is read-only,
    cannot create or modify a proposal, cannot reach a broker, and every
    execution path still requires human approval plus revalidation.  Do not
    treat a clean pass here as evidence the prose carries no advice.
    """

    facts = committee_input.fact_by_id
    issues: list[ValidationIssue] = []

    def issue(code: str, path: str, message: str) -> None:
        issues.append(ValidationIssue(code=code, path=path, message=message))

    if len(facts) != len(committee_input.facts):
        issue("duplicate_source_id", "input.facts", "Input contains duplicate source IDs.")

    for section, point in review.all_cited_points():
        path = f"review.{section}"
        missing = [source_id for source_id in point.source_ids if source_id not in facts]
        if missing:
            issue(
                "unknown_source_id",
                path,
                f"Unknown source IDs: {', '.join(missing)}.",
            )
            continue
        cited = [facts[source_id] for source_id in point.source_ids]
        source_text = "\n".join(fact.grounding_text() for fact in cited)
        unsupported = _unsupported_numbers(point.text, source_text)
        if unsupported:
            issue(
                "unsupported_number",
                path,
                f"Numbers absent from cited sources: {', '.join(unsupported[:8])}.",
            )

        # Allow source-grounded acronyms/tickers plus the small common-acronym
        # allowlist in ai_advisor.  A ticker from an unrelated fact cannot be
        # reassigned to this point merely because it exists elsewhere.
        cited_upper_tokens = set(_SOURCE_TICKER_PATTERN.findall(source_text))
        if _mentions_unknown_ticker(point.text, cited_upper_tokens):
            issue(
                "unsupported_ticker_or_acronym",
                path,
                "Point contains an uppercase ticker/acronym absent from its cited sources.",
            )
        if _contains_committee_action_language(
            point.text, set(committee_input.portfolio_tickers)
        ):
            issue(
                "forbidden_action_language",
                path,
                "Committee prose may analyze facts but must not direct a portfolio change.",
            )

    if review.verdict in (Verdict.SUPPORT, Verdict.SUPPORT_WITH_CAUTION):
        if not review.supporting_points:
            issue(
                "missing_support",
                "review.supporting_points",
                "A supportive verdict requires at least one supporting point.",
            )
        if not review.counterarguments:
            issue(
                "missing_counterargument",
                "review.counterarguments",
                "A supportive verdict requires at least one counterargument.",
            )
        if not review.invalidation_conditions:
            issue(
                "missing_invalidation_condition",
                "review.invalidation_conditions",
                "A supportive verdict requires an invalidation condition.",
            )

    for index, point in enumerate(review.supporting_points):
        for source_id in point.source_ids:
            fact = facts.get(source_id)
            if fact is not None and not fact.production_authoritative:
                issue(
                    "non_authoritative_support",
                    f"review.supporting_points[{index}]",
                    f"{source_id} is context-only and cannot support the verdict.",
                )

    if review.verdict in (Verdict.SUPPORT, Verdict.SUPPORT_WITH_CAUTION):
        for section, point in (
            ("summary", review.summary),
            ("confidence_basis", review.confidence_basis),
        ):
            context_only = [
                source_id
                for source_id in point.source_ids
                if source_id in facts
                and not facts[source_id].production_authoritative
            ]
            if context_only:
                issue(
                    "non_authoritative_support",
                    f"review.{section}",
                    "A supportive verdict cannot rely on context-only sources in "
                    f"{section}: {', '.join(context_only)}.",
                )

    required_warning_ids = {
        fact.source_id
        for fact in committee_input.facts
        if fact.critical
        and (
            fact.category == "warning"
            or fact.availability != FactAvailability.AVAILABLE
        )
    }
    cited_warning_ids = {
        source_id
        for point in review.data_quality_warnings
        for source_id in point.source_ids
    }
    concealed = sorted(required_warning_ids - cited_warning_ids)
    if concealed:
        issue(
            "concealed_critical_warning",
            "review.data_quality_warnings",
            f"Critical input warnings were not surfaced: {', '.join(concealed)}.",
        )

    if (
        required_warning_ids
        and review.verdict == Verdict.SUPPORT
        and review.confidence_label == ConfidenceLabel.HIGH
    ):
        issue(
            "overconfident_with_missing_data",
            "review.confidence_label",
            "High-confidence support is not accepted while critical warnings are present.",
        )

    return ValidationReport(accepted=not issues, issues=tuple(issues))
