"""
Win-probability model for flagged scanner signals.

Trains on backtest.engine.run_backtest() output: given the features known
AT THE MOMENT a signal fired (return_zscore, volume_zscore, direction),
predict the probability that "going long the signal" would have been a
net winner (net_return_pct > 0) after the configured hold period.

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

from config import MODEL_PATH

FEATURE_COLUMNS = ["return_zscore", "volume_zscore", "direction_up"]


def build_features(backtest_results: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """
    Turn backtest.engine.run_backtest() output into (X, y) for training.
    X uses only information available at signal time; y is the realized
    outcome (net_return_pct > 0) which is only known in hindsight.
    """
    ordered = backtest_results.sort_values("date").reset_index(drop=True)
    X = pd.DataFrame(
        {
            "return_zscore": ordered["return_zscore"].astype(float),
            "volume_zscore": ordered["volume_zscore"].astype(float),
            "direction_up": (ordered["direction"] == "up").astype(int),
        }
    )
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


def score_signals(model: RandomForestClassifier, signals: pd.DataFrame) -> pd.DataFrame:
    """
    Attach a `win_probability` column to a scanner-style signals DataFrame
    (as returned by scan_dips_and_ups) using the trained model.
    """
    if signals.empty:
        return signals.assign(win_probability=pd.Series(dtype=float))

    X = pd.DataFrame(
        {
            "return_zscore": signals["return_zscore"].astype(float),
            "volume_zscore": signals["volume_zscore"].astype(float),
            "direction_up": (signals["direction"] == "up").astype(int),
        }
    )
    probabilities = model.predict_proba(X)[:, list(model.classes_).index(1)]
    return signals.assign(win_probability=[round(p, 3) for p in probabilities])
