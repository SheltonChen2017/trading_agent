"""Policy-neutral statistical primitives shared across both products."""
from __future__ import annotations

def bonferroni_threshold(n_tests: int, alpha: float = 0.05) -> float:
    """Return the Bonferroni threshold for simultaneous comparisons.

    The helper only performs ``alpha / n_tests`` (or returns ``alpha`` when no
    tests are counted). Research code remains responsible for defining the
    family and counting every look; assistant code may display the correction
    but cannot create evidence or choose the denominator through this helper.

    A pooled bootstrap over discovery and confirmation rows is exploratory,
    never confirmatory: a strong discovery effect can drag a misleading
    significant result out of a noisy confirmation period. Row-level
    resampling also treats correlated same-date signals as independent, and
    by-date resampling still misses serial dependence across nearby dates.
    Confirmation claims therefore require the repository's separately frozen
    out-of-sample, by-date/block-aware methods; this arithmetic threshold does
    not make a weak observation unit rigorous.
    """
    if n_tests <= 0:
        return alpha
    return alpha / n_tests


__all__ = ["bonferroni_threshold"]
