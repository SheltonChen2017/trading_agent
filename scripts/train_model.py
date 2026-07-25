"""
Runs the backtest to generate training data, walk-forward evaluates a
win-probability classifier, then (if it evaluated on at least one fold)
fits a final model on all available signals and saves it to MODEL_PATH.

Uses synthetic data by default — see README for switching to real history.
Remember: on synthetic data, near-50% accuracy is the expected, correct
result (see ml/model.py docstring) — it means the pipeline isn't
manufacturing fake edge out of noise.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import LOOKBACK_DAYS, MODEL_PATH, UNIVERSE
from data.market_data import generate_synthetic  # swap for fetch_historical for real data
from backtest.engine import run_backtest
from ml.model import build_features, save_model, train_final_model, walk_forward_evaluate


def main():
    print(f"Generating synthetic data for {len(UNIVERSE)} tickers over {LOOKBACK_DAYS} days...")
    data = generate_synthetic(UNIVERSE, days=LOOKBACK_DAYS)

    print("Running backtest to build a labeled training set...")
    results = run_backtest(data)
    if results.empty:
        print("No signals flagged — nothing to train on. Try a longer lookback or a bigger universe.")
        return

    print(f"{len(results)} labeled signals. Building features...")
    X, y = build_features(results)

    print("Walk-forward evaluating (time-ordered folds, never trained on future data)...")
    metrics = walk_forward_evaluate(X, y)
    if not metrics["folds"]:
        print("Not enough signals for a walk-forward split. Need more history/signals before training.")
        return

    for i, fold in enumerate(metrics["folds"], 1):
        print(f"  fold {i}: accuracy={fold['accuracy']} precision={fold['precision']} (n={fold['test_size']})")
    print(f"mean accuracy={metrics['mean_accuracy']}  mean precision={metrics['mean_precision']}")
    print(
        "\nNote: on synthetic random-walk data, ~50% accuracy is expected and "
        "correct — it confirms there's no look-ahead leak manufacturing fake "
        "skill. Point this at real historical data before trusting the model."
    )

    print(f"\nFitting final model on all {len(X)} signals and saving to {MODEL_PATH}...")
    model = train_final_model(X, y)
    save_model(model, MODEL_PATH)
    print("Done.")


if __name__ == "__main__":
    main()
