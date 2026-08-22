"""QC-2: an honest denominator for the multiplicity correction.

Every backtest configuration a human examines is a statistical test, whether
or not its result was liked. Testing many configurations and reporting the
best one inflates false discovery, and the correction for that
(`data.research_statistics.bonferroni_threshold`) needs a count of how many were
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

  - **Only identical code, data, and configuration are a repeat.** The engine
    is deterministic for those exact inputs. Real history grows/corrects,
    synthetic dates move, and runtime code changes; all are new looks even
    when the widgets retain the same labels. Exact repeats increment
    `repeat_count` instead of the hypothesis denominator.

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
import math
import re
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from assistant.storage import AssistantStore
from data.research_statistics import bonferroni_threshold


class ResearchLookError(ValueError):
    """Malformed or incomplete research-look input."""


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ResearchLookError(f"{field} must be text")
    text = value.strip()
    if not text:
        raise ResearchLookError(f"{field} is required to record a research look")
    return text


def _required_identity(value: Any, field: str, pattern: re.Pattern[str]) -> str:
    text = _required_text(value, field)
    if pattern.fullmatch(text) is None:
        raise ResearchLookError(f"{field} is not a canonical lowercase digest")
    return text


def _canonical_configuration(configuration: Any) -> tuple[str, dict[str, Any]]:
    """Strict finite JSON identity; never stringify unsupported objects.

    ``default=str`` is unsafe for evidence identity: a Decimal and a string
    can collapse to the same JSON text, while NaN/Infinity are not JSON at
    all. String-only object keys also prevent ``1`` and ``"1"`` from sharing
    an identity after JSON key coercion.
    """
    if not isinstance(configuration, dict):
        raise ResearchLookError("configuration must be an object")

    def _validate(value: Any, path: str) -> None:
        if value is None or isinstance(value, (str, bool, int)):
            return
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ResearchLookError(f"configuration {path} must be finite")
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                _validate(item, f"{path}[{index}]")
            return
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str):
                    raise ResearchLookError(
                        f"configuration {path} keys must be strings"
                    )
                _validate(item, f"{path}.{key}")
            return
        raise ResearchLookError(
            f"configuration {path} has unsupported type {type(value).__name__}"
        )

    _validate(configuration, "$")
    try:
        canonical = json.dumps(
            configuration,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:  # defence in depth after validation
        raise ResearchLookError("configuration is not canonical finite JSON") from exc
    return canonical, json.loads(canonical)


def research_data_fingerprint(data: Any) -> str:
    """SHA-256 identity of the exact dated frames supplied to the engine.

    The engine is deterministic only for identical data *and* code. Real
    history grows and may be provider-corrected; synthetic dates also move
    with the session. Widget settings alone therefore cannot define a repeat.
    """
    if not isinstance(data, dict) or not data:
        raise ResearchLookError("research data must be a non-empty ticker mapping")
    normalized: dict[str, pd.DataFrame] = {}
    for raw_ticker, frame in data.items():
        ticker = _required_text(raw_ticker, "research data ticker").upper()
        if ticker in normalized:
            raise ResearchLookError(f"research data repeats ticker {ticker!r}")
        if not isinstance(frame, pd.DataFrame):
            raise ResearchLookError(f"research data {ticker} must be a DataFrame")
        if frame.columns.has_duplicates:
            raise ResearchLookError(f"research data {ticker} repeats a column")
        normalized[ticker] = frame

    digest = hashlib.sha256()

    def _add(value: bytes) -> None:
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)

    for ticker in sorted(normalized):
        frame = normalized[ticker]
        ordered_columns = sorted(str(column) for column in frame.columns)
        if len(ordered_columns) != len(frame.columns) or any(
            not isinstance(column, str) for column in frame.columns
        ):
            raise ResearchLookError(
                f"research data {ticker} columns must be unique strings"
            )
        ordered = frame.loc[:, ordered_columns]
        metadata = json.dumps(
            {
                "ticker": ticker,
                "columns": ordered_columns,
                "dtypes": [str(dtype) for dtype in ordered.dtypes],
                "index_dtype": str(ordered.index.dtype),
                "index_names": [str(name) if name is not None else None for name in ordered.index.names],
                "rows": len(ordered),
            },
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        _add(metadata)
        try:
            row_hashes = pd.util.hash_pandas_object(
                ordered, index=True, categorize=False
            ).to_numpy(dtype="uint64", copy=False)
        except (TypeError, ValueError) as exc:
            raise ResearchLookError(
                f"research data {ticker} cannot be canonically hashed"
            ) from exc
        _add(row_hashes.tobytes())
    return digest.hexdigest()


def look_fingerprint(
    *,
    surface: str,
    signal_key: str,
    configuration: dict[str, Any],
    data_source: str,
    data_fingerprint: str,
    code_commit: str,
    hypothesis_count: int = 1,
) -> str:
    """Content identity of one examined configuration.

    Everything that changes what was tested belongs in here: surface, signal,
    exact configuration, exact dated data, code commit, source class, and the
    number of horizon-by-direction hypothesis cells scanned.
    """
    _, normalized_configuration = _canonical_configuration(configuration)
    if isinstance(hypothesis_count, bool) or not isinstance(hypothesis_count, int):
        raise ResearchLookError("hypothesis_count must be a positive integer")
    if hypothesis_count <= 0:
        raise ResearchLookError("hypothesis_count must be a positive integer")
    material = {
        "surface": _required_text(surface, "surface"),
        "signal_key": _required_text(signal_key, "signal_key"),
        "data_source": _required_text(data_source, "data_source"),
        "data_fingerprint": _required_identity(
            data_fingerprint, "data_fingerprint", _SHA256
        ),
        "code_commit": _required_identity(code_commit, "code_commit", _COMMIT),
        "hypothesis_count": hypothesis_count,
        "configuration": normalized_configuration,
    }
    canonical = json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def record_research_look(
    store: AssistantStore,
    *,
    surface: str,
    signal_key: str,
    configuration: dict[str, Any],
    data_source: str,
    data_fingerprint: str,
    code_commit: str,
    hypothesis_count: int = 1,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Record that one configuration was examined.

    Call this BEFORE the result is known, so a look cannot be skipped once
    its outcome turns out to be uninteresting. The return value includes
    `is_new_look` so a caller can tell an added test from a repeat.
    """
    _, normalized_configuration = _canonical_configuration(configuration)
    fingerprint = look_fingerprint(
        surface=surface,
        signal_key=signal_key,
        configuration=normalized_configuration,
        data_source=data_source,
        data_fingerprint=data_fingerprint,
        code_commit=code_commit,
        hypothesis_count=hypothesis_count,
    )
    seen_at = (now or datetime.now(timezone.utc))
    if seen_at.tzinfo is None or seen_at.utcoffset() is None:
        raise ResearchLookError("research-look time must be timezone-aware")
    seen_at = seen_at.astimezone(timezone.utc)
    record = store.record_research_look(
        look_fingerprint=fingerprint,
        surface=_required_text(surface, "surface"),
        signal_key=_required_text(signal_key, "signal_key"),
        configuration=normalized_configuration,
        data_source=_required_text(data_source, "data_source"),
        data_fingerprint=_required_identity(
            data_fingerprint, "data_fingerprint", _SHA256
        ),
        code_commit=_required_identity(code_commit, "code_commit", _COMMIT),
        hypothesis_count=hypothesis_count,
        seen_at=seen_at.isoformat(),
    )
    record["is_new_look"] = record["repeat_count"] == 1
    return record


def research_look_summary(
    store: AssistantStore,
    *,
    alpha: float = 0.05,
    surface: str | None = None,
    data_source: str | None = None,
) -> dict[str, Any]:
    """Total hypothesis cells and the multiplicity-corrected threshold.

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
    total = store.count_research_looks(
        surface=surface, data_source=data_source
    )
    threshold = (
        float(alpha) if total == 0 else bonferroni_threshold(total, alpha=float(alpha))
    )
    family_parts = []
    if surface is not None:
        family_parts.append(f"surface={surface}")
    if data_source is not None:
        family_parts.append(f"data_source={data_source}")
    family = ", ".join(family_parts) or "all recorded research"
    return {
        "total_looks": total,
        "alpha": float(alpha),
        "corrected_alpha_threshold": threshold,
        "correction": "bonferroni",
        "family": {"surface": surface, "data_source": data_source},
        # Said plainly because the number invites over-reading: clearing this
        # threshold is a necessary condition, not a finding.
        "interpretation": (
            f"{total} hypothesis cell(s) examined in {family}. A p-value must be "
            f"below {threshold:.6g} to survive multiplicity correction at "
            f"alpha={float(alpha)}. That is necessary, not sufficient: a "
            "claim still needs out-of-sample, confirmation-only, by-date and "
            "by-block significance."
        ),
    }
