"""
End-to-end run: scan for today's signals -> score with the trained model
(if one exists) -> size positions with the risk manager -> execute on
Alpaca paper trading (only if APCA_API_KEY_ID/APCA_API_SECRET_KEY are set).

Uses synthetic data by default — see README for switching to real data.
Safe to run with no setup at all: without a trained model it sizes at
full confidence, and without Alpaca credentials it just prints what WOULD
be sized/traded instead of executing.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import INITIAL_CAPITAL, LOOKBACK_DAYS, MODEL_PATH, UNIVERSE
from data.market_data import generate_synthetic  # swap for fetch_historical for real data
from signals.scanner import scan_dips_and_ups
from ml.model import load_model, score_signals
from risk.manager import allocate
from execution.alpaca_broker import AlpacaNotConfigured, execute_allocation, get_account, is_configured


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
        print(f"No trained model found at {MODEL_PATH} (run scripts/train_model.py first) — sizing at full confidence.")

    account_equity = INITIAL_CAPITAL
    if is_configured():
        try:
            account = get_account()
            account_equity = account["equity"]
            print(f"Connected to Alpaca ({'paper' if account['paper'] else 'LIVE'}) — equity=${account_equity:,.2f}")
        except AlpacaNotConfigured:
            pass

    sized = allocate(signals, account_equity=account_equity)
    print("\nSized signals:")
    print(sized.to_string(index=False))

    tradeable = sized[sized["shares"] > 0]
    if tradeable.empty:
        print("\nNothing sized above zero shares — no orders to place.")
        return

    if not is_configured():
        print(
            "\nAPCA_API_KEY_ID/APCA_API_SECRET_KEY not set — not executing. "
            "Sign up free at https://alpaca.markets to enable paper trading."
        )
        return

    print("\nSubmitting orders to Alpaca...")
    results = execute_allocation(tradeable)
    for r in results:
        print(f"  {r['ticker']}: buy={r['buy_order']['status']} stop={r['stop_order']['status']}")


if __name__ == "__main__":
    main()
