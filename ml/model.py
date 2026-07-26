"""
Win-probability model for flagged scanner signals.

Trains on backtest.engine.run_backtest() output: given the features known
AT THE MOMENT a signal fired (return_zscore, volume_zscore, direction,
and optionally the market's own recent trend), predict the probability
that "going long the signal" would have been a net winner (net_return_pct
> 0) after the configured hold period.

Uses a walk-forward (time-ordered) split rather than a random train/test
split, per the project's own known pitfall: markets change regime, so a
random split leaks future information into training and overstates
accuracy. See README "Known pitfalls".

IMPORTANT: on the repo's synthetic random-walk data, forward returns are
by construction independent of the flagged z-scores — there is no real
edge to find. A model trained on synthetic data should score close to
50/50. That's the CORRECT, expected result: it confirms the training/eval
pipeline isn't manufacturing fake signal out of noise. Point this at real
historical data (fetch_historical) before drawing any conclusion about
actual edge.
"""
from __future__ import annotations

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score
from sklearn.model_selection import TimeSeriesSplit

from config import MODEL_PATH, REGIME_LOOKBACK_DAYS

BASE_FEATURE_COLUMNS = ["return_zscore", "volume_zscore", "direction_up"]
REGIME_FEATURE_COLUMN = "market_trend_pct"


def compute_trailing_market_trend(
    benchmark_df: pd.DataFrame, as_of: pd.Timestamp, lookback_days: int = REGIME_LOOKBACK_DAYS
) -> float | None:
    """
    The market benchmark's (e.g. SPY) own return over the `lookback_days`
    trading days ending at (and including) `as_of` — a simple regime
    indicator: was the broad market trending up or down heading into this
    signal? Purely backward-looking (never uses data after `as_of`), so
    it's safe to use as a model feature without introducing look-ahead
    bias. Returns None if `as_of` isn't in the benchmark's history or
    there isn't enough trailing history yet.
    """
    if as_of not in benchmark_df.index:
        return None
    idx = benchmark_df.index.get_loc(as_of)
    start_idx = idx - lookback_days
    if start_idx < 0:
        return None

    start_price = float(benchmark_df["close"].iloc[start_idx])
    end_price = float(benchmark_df["close"].iloc[idx])
    if start_price <= 0:
        return None
    return (end_price - start_price) / start_price * 100


def build_features(
    backtest_results: pd.DataFrame,
    benchmark_df: pd.DataFrame | None = None,
    regime_lookback_days: int = REGIME_LOOKBACK_DAYS,
) -> tuple[pd.DataFrame, pd.Series]:
    """
    Turn backtest.engine.run_backtest() output into (X, y) for training.
    X uses only information available at signal time; y is the realized
    outcome (net_return_pct > 0) which is only known in hindsight.

    Pass `benchmark_df` (e.g. SPY history) to add a market-regime feature
    (the benchmark's own trailing trend as of each signal's date) —
    omitted by default to stay backward-compatible with a model trained
    on just the original 3 features.
    """
    ordered = backtest_results.sort_values("date").reset_index(drop=True)
    X = pd.DataFrame(
        {
            "return_zscore": ordered["return_zscore"].astype(float),
            "volume_zscore": ordered["volume_zscore"].astype(float),
            "direction_up": (ordered["direction"] == "up").astype(int),
        }
    )
    if benchmark_df is not None:
        X[REGIME_FEATURE_COLUMN] = ordered["date"].apply(
            lambda d: compute_trailing_market_trend(benchmark_df, d, regime_lookback_days)
        )
        X = X.dropna(subset=[REGIME_FEATURE_COLUMN]).reset_index(drop=True)
        ordered = ordered.loc[X.index].reset_index(drop=True) if len(X) != len(ordered) else ordered

    y = ordered["win"].astype(int)
    return X, y


def walk_forward_evaluate(X: pd.DataFrame, y: pd.Series, n_splits: int = 5) -> dict:
    """
    Time-ordered cross-validation: each fold trains only on data that
    precedes the test fold chronologically, never on future signals.
    Returns per-fold and mean accuracy/precision.
    """
    n_splits = max(2, min(n_splits, len(X) - 1)) if len(X) > 2 else 0
    if n_splits < 2:
        return {"folds": [], "mean_accuracy": None, "mean_precision": None}

    splitter = TimeSeriesSplit(n_splits=n_splits)
    folds = []
    for train_idx, test_idx in splitter.split(X):
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

        if y_train.nunique() < 2:
            continue  # can't train a classifier on a single-class fold

        clf = RandomForestClassifier(n_estimators=100, max_depth=4, random_state=0)
        clf.fit(X_train, y_train)
        preds = clf.predict(X_test)

        folds.append(
            {
                "accuracy": round(accuracy_score(y_test, preds), 3),
                "precision": round(precision_score(y_test, preds, zero_division=0), 3),
                "test_size": len(X_test),
            }
        )

    if not folds:
        return {"folds": [], "mean_accuracy": None, "mean_precision": None}

    mean_accuracy = round(sum(f["accuracy"] for f in folds) / len(folds), 3)
    mean_precision = round(sum(f["precision"] for f in folds) / len(folds), 3)
    return {"folds": folds, "mean_accuracy": mean_accuracy, "mean_precision": mean_precision}


def train_final_model(X: pd.DataFrame, y: pd.Series) -> RandomForestClassifier:
    """Fit on ALL available data — call this only after walk-forward
    evaluation has already told you how the model performs out-of-sample."""
    clf = RandomForestClassifier(n_estimators=100, max_depth=4, random_state=0)
    clf.fit(X, y)
    return clf


def save_model(model: RandomForestClassifier, path: str = MODEL_PATH) -> None:
    joblib.dump(model, path)


def load_model(path: str = MODEL_PATH) -> RandomForestClassifier:
    return joblib.load(path)


def score_signals(
    model: RandomForestClassifier,
    signals: pd.DataFrame,
    benchmark_df: pd.DataFrame | None = None,
    regime_lookback_days: int = REGIME_LOOKBACK_DAYS,
) -> pd.DataFrame:
    """
    Attach a `win_probability` column to a scanner-style signals DataFrame
    (as returned by scan_dips_and_ups) using the trained model.

    If `model` was trained with the market-regime feature (i.e. built via
    build_features(..., benchmark_df=...)), pass the SAME kind of
    `benchmark_df` here too — the feature set at scoring time must match
    training time. Passing a benchmark_df when the model wasn't trained
    with one (or vice versa) raises a clear error rather than silently
    scoring on the wrong features.
    """
    if signals.empty:
        return signals.assign(win_probability=pd.Series(dtype=float))

    expects_regime = getattr(model, "n_features_in_", len(BASE_FEATURE_COLUMNS)) == len(BASE_FEATURE_COLUMNS) + 1
    if expects_regime and benchmark_df is None:
        raise ValueError(
            "This model was trained with the market-regime feature "
            "(4 features) but no benchmark_df was passed to score_signals()."
        )
    if not expects_regime and benchmark_df is not None:
        raise ValueError(
            "A benchmark_df was passed to score_signals(), but this model was "
            "trained without the market-regime feature (3 features) — retrain "
            "with build_features(..., benchmark_df=...) first, or omit benchmark_df here."
        )

    X = pd.DataFrame(
        {
            "return_zscore": signals["return_zscore"].astype(float),
            "volume_zscore": signals["volume_zscore"].astype(float),
            "direction_up": (signals["direction"] == "up").astype(int),
        }
    )
    if benchmark_df is not None:
        X[REGIME_FEATURE_COLUMN] = signals["date"].apply(
            lambda d: compute_trailing_market_trend(benchmark_df, d, regime_lookback_days)
        )
        missing_regime = X[REGIME_FEATURE_COLUMN].isna()
        if missing_regime.any():
            # Can't score signals whose date falls outside the benchmark's
            # own history — drop them rather than feed the model a NaN.
            X = X.loc[~missing_regime]
            signals = signals.loc[~missing_regime]

    if X.empty:
        return signals.assign(win_probability=pd.Series(dtype=float))

    probabilities = model.predict_proba(X)[:, list(model.classes_).index(1)]
    return signals.assign(win_probability=[round(p, 3) for p in probabilities])
