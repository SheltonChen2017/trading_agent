"""
Legacy research demo: scan synthetic data -> score with a trained model
-> print hypothetical position sizes. It cannot submit orders.

Uses synthetic data by default — see README for switching to real data.
An absent model causes a safe refusal rather than being interpreted as
full confidence. Use scripts/run_personal_assistant.py for the approved,
policy-bound paper workflow.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import INITIAL_CAPITAL, LOOKBACK_DAYS, MODEL_PATH, UNIVERSE
from data.market_data import generate_synthetic  # swap for fetch_historical for real data
from signals.scanner import scan_dips_and_ups
from ml.model import load_model, score_signals
from risk.manager import allocate


def main():
    print(f"Generating synthetic data for {len(UNIVERSE)} tickers over {LOOKBACK_DAYS} days...")
    data = generate_synthetic(UNIVERSE, days=LOOKBACK_DAYS)

    print("Scanning for statistically unusual moves confirmed by volume...")
    signals = scan_dips_and_ups(data)
    if signals.empty:
        print("No dips/ups flagged today.")
        return
    print(f"{len(signals)} signal(s) flagged.")

    try:
        model = load_model(MODEL_PATH)
        signals = score_signals(model, signals)
        print(f"Scored with model at {MODEL_PATH}.")
    except FileNotFoundError:
        print(
            f"No trained model found at {MODEL_PATH}. Refusing to interpret "
            "unscored signals as full confidence."
        )
        return

    sized = allocate(signals, account_equity=INITIAL_CAPITAL)
    print("\nSized signals:")
    print(sized.to_string(index=False))

    print(
        "\nResearch output only — execution is disabled for this rejected "
        "scanner. Use scripts/run_personal_assistant.py for gated proposals."
    )


if __name__ == "__main__":
    main()
