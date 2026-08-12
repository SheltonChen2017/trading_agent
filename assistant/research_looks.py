"""QC-2: an honest denominator for the multiplicity correction.

Every backtest configuration a human examines is a statistical test, whether
or not its result was liked. Testing many configurations and reporting the
best one inflates false discovery, and the correction for that
(`backtest.engine.bonferroni_threshold`) needs a count of how many were
looked at. Until now nothing recorded that count: `ml/experiments.py` counts
looks declared *inside one frozen spec*, but the interactive Backtest surface
-- the one a person clicks repeatedly while exploring -- counted nothing.

Design constraints, and why:

  - **Recording is not gating.** This is an accounting record, never a
    permission check. It must never block, delay, or alter a backtest, and it
    holds no execution, proposal, or policy authority.

  - **A look cannot be un-looked.** There is no delete and no configuration
    update. Discarding looks whose results disappointed is precisely the
    behaviour the correction exists to price in.

  - **Re-running an identical configuration is not a new test.** The engine
    is deterministic, so the same configuration returns the same answer;
    counting it twice would inflate the denominator and make the threshold
    unfairly strict. Identical configurations increment `repeat_count`.
    Change any parameter and it is a new look, because that is a new test.

  - **This lives in `assistant/`, not `backtest/`.** `backtest.interactive`
    is a research surface forbidden (by AST test) from importing storage, so
    the registry cannot live beside it. The UI composes the two, which is the
    repository's standing preference for script-level composition over making
    core packages import one another.

The correction reported here is Bonferroni over the WHOLE registry, which is
deliberately conservative and deliberately crude. It is an accounting aid,
not a substitute for the confirmation discipline in `backtest/engine.py`
(out-of-sample, confirmation-only, by-date AND by-block significance). A
p-value that clears this threshold is still not a finding.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from assistant.storage import AssistantStore
from backtest.engine import bonferroni_threshold


class ResearchLookError(ValueError):
    """Malformed or incomplete research-look input."""


def _required_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ResearchLookError(f"{field} is required to record a research look")
    return text


def look_fingerprint(
    *,
    surface: str,
    signal_key: str,
    configuration: dict[str, Any],
    data_source: str,
) -> str:
    """Content identity of one examined configuration.

    Everything that changes what was tested belongs in here. `surface` and
    `data_source` are included because the same signal and parameters run on
    synthetic data is not the same test as on real history, and must not
    collapse into one look.
    """
    material = {
        "surface": _required_text(surface, "surface"),
        "signal_key": _required_text(signal_key, "signal_key"),
        "data_source": _required_text(data_source, "data_source"),
        "configuration": configuration,
    }
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def record_research_look(
    store: AssistantStore,
    *,
    surface: str,
    signal_key: str,
    configuration: dict[str, Any],
    data_source: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Record that one configuration was examined.

    Call this BEFORE the result is known, so a look cannot be skipped once
    its outcome turns out to be uninteresting. The return value includes
    `is_new_look` so a caller can tell an added test from a repeat.
    """
    if not isinstance(configuration, dict):
        raise ResearchLookError("configuration must be an object")
    fingerprint = look_fingerprint(
        surface=surface,
        signal_key=signal_key,
        configuration=configuration,
        data_source=data_source,
    )
    seen_at = (now or datetime.now(timezone.utc))
    if seen_at.tzinfo is None:
        raise ResearchLookError("research-look time must be timezone-aware")
    record = store.record_research_look(
        look_fingerprint=fingerprint,
        surface=_required_text(surface, "surface"),
        signal_key=_required_text(signal_key, "signal_key"),
        configuration=configuration,
        data_source=_required_text(data_source, "data_source"),
        seen_at=seen_at.isoformat(),
    )
    record["is_new_look"] = record["repeat_count"] == 1
    return record


def research_look_summary(
    store: AssistantStore, *, alpha: float = 0.05
) -> dict[str, Any]:
    """Total distinct looks and the multiplicity-corrected threshold.

    `alpha` is the uncorrected significance level a single test would use.
    With zero looks recorded the corrected threshold is reported as the
    uncorrected `alpha`: no tests have been run, so there is nothing to
    correct for -- and reporting a stricter number would imply a penalty
    that has not been earned.
    """
    if not isinstance(alpha, float) and not isinstance(alpha, int):
        raise ResearchLookError("alpha must be numeric")
    if isinstance(alpha, bool) or not 0 < float(alpha) < 1:
        raise ResearchLookError(f"alpha must be between 0 and 1, got {alpha!r}")
    total = store.count_research_looks()
    threshold = (
        float(alpha) if total == 0 else bonferroni_threshold(total, alpha=float(alpha))
    )
    return {
        "total_looks": total,
        "alpha": float(alpha),
        "corrected_alpha_threshold": threshold,
        "correction": "bonferroni",
        # Said plainly because the number invites over-reading: clearing this
        # threshold is a necessary condition, not a finding.
        "interpretation": (
            f"{total} distinct configuration(s) examined. A p-value must be "
            f"below {threshold:.6g} to survive multiplicity correction at "
            f"alpha={float(alpha)}. That is necessary, not sufficient: a "
            "claim still needs out-of-sample, confirmation-only, by-date and "
            "by-block significance."
        ),
    }
