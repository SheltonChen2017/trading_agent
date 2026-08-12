"""Tests for assistant/ticker_verification.py. Run with:
python tests/test_ticker_verification.py"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import pytest

from assistant import ticker_verification
from assistant.ticker_verification import SecurityEligibilityPolicy

_ELIGIBLE_INFO = {"longName": "Apple Inc.", "quoteType": "EQUITY", "exchange": "NMS", "sector": "Technology"}


def _df(rows=70, close=100.0, volume=50_000_000):
    """A history shaped to pass DEFAULT_ELIGIBILITY_POLICY by default:
    70 sessions (>= 60 minimum), $100 close (>= $5 minimum), 50M share
    volume at $100 -> $5B median dollar volume (>= $1M minimum)."""
    return pd.DataFrame(
        {"close": [close] * rows, "volume": [volume] * rows},
        index=pd.bdate_range("2026-01-01", periods=rows),
    )


def test_verify_tickers_keeps_valid_ticker():
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"AAPL": _df()}
        mock_info.return_value = _ELIGIBLE_INFO
        verified, dropped = ticker_verification.verify_tickers(["AAPL"])
    assert dropped == []
    assert len(verified) == 1
    assert verified[0]["ticker"] == "AAPL"
    assert verified[0]["longName"] == "Apple Inc."
    assert verified[0]["history_sessions"] == 70
    assert verified[0]["last_price"] == 100.0
    assert verified[0]["median_dollar_volume"] == 100.0 * 50_000_000


def test_verify_tickers_drops_ticker_not_in_fetch_historical_result():
    # The hallucinated/delisted/typo case: fetch_historical simply omits it.
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch:
        mock_fetch.return_value = {}
        verified, dropped = ticker_verification.verify_tickers(["FAKETIX"])
    assert verified == []
    assert dropped == ["FAKETIX"]


def test_verify_tickers_drops_ticker_with_empty_info():
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"ZZZZ": _df()}
        mock_info.return_value = {}
        verified, dropped = ticker_verification.verify_tickers(["ZZZZ"])
    assert verified == []
    assert dropped == ["ZZZZ"]


def test_verify_tickers_one_bad_ticker_does_not_abort_batch():
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"AAPL": _df()}
        mock_info.return_value = _ELIGIBLE_INFO
        verified, dropped = ticker_verification.verify_tickers(["AAPL", "BOGUS"])
    assert [v["ticker"] for v in verified] == ["AAPL"]
    assert dropped == ["BOGUS"]


def test_verify_tickers_respects_max_checks_cap():
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"A": _df(), "B": _df()}
        mock_info.return_value = _ELIGIBLE_INFO
        verified, dropped = ticker_verification.verify_tickers(["A", "B", "C", "D"], max_checks=2)
    assert mock_fetch.call_args[0][0] == ["A", "B"]
    assert {v["ticker"] for v in verified} == {"A", "B"}
    assert set(dropped) == {"C", "D"}


# --- Eligibility policy: quote type, history length, price, liquidity

def test_verify_tickers_rejects_non_equity_quote_type():
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"SPY": _df()}
        mock_info.return_value = {**_ELIGIBLE_INFO, "quoteType": "ETF"}
        verified, dropped = ticker_verification.verify_tickers(["SPY"])
    assert verified == []
    assert dropped == ["SPY"]


def test_verify_tickers_rejects_short_history():
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"NEWIPO": _df(rows=10)}
        mock_info.return_value = _ELIGIBLE_INFO
        verified, dropped = ticker_verification.verify_tickers(["NEWIPO"])
    assert verified == []
    assert dropped == ["NEWIPO"]


def test_verify_tickers_rejects_price_below_minimum():
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"PENNY": _df(close=1.0)}
        mock_info.return_value = _ELIGIBLE_INFO
        verified, dropped = ticker_verification.verify_tickers(["PENNY"])
    assert verified == []
    assert dropped == ["PENNY"]


def test_verify_tickers_rejects_illiquid_ticker():
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"THIN": _df(close=10.0, volume=100)}  # $1,000 median dollar volume
        mock_info.return_value = _ELIGIBLE_INFO
        verified, dropped = ticker_verification.verify_tickers(["THIN"])
    assert verified == []
    assert dropped == ["THIN"]


def test_verify_tickers_rejects_missing_company_name():
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"NONAME": _df()}
        mock_info.return_value = {**_ELIGIBLE_INFO, "longName": ""}
        verified, dropped = ticker_verification.verify_tickers(["NONAME"])
    assert verified == []
    assert dropped == ["NONAME"]


def test_verify_tickers_rejects_non_us_exchange():
    # independent review: nothing enforced the "US tickers"/"US stocks"
    # framing already used in prompts/UI copy -- a sufficiently liquid
    # foreign or OTC listing could pass every other check.
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"FOREIGN": _df()}
        mock_info.return_value = {**_ELIGIBLE_INFO, "exchange": "LSE"}
        verified, dropped = ticker_verification.verify_tickers(["FOREIGN"])
    assert verified == []
    assert dropped == ["FOREIGN"]


def test_verify_tickers_allowed_exchanges_none_disables_the_check():
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"FOREIGN": _df()}
        mock_info.return_value = {**_ELIGIBLE_INFO, "exchange": "LSE"}
        no_exchange_restriction = SecurityEligibilityPolicy(allowed_exchanges=None)
        verified, dropped = ticker_verification.verify_tickers(["FOREIGN"], policy=no_exchange_restriction)
    assert dropped == []
    assert len(verified) == 1


def test_verify_tickers_custom_policy_can_relax_defaults():
    lenient_policy = SecurityEligibilityPolicy(
        allowed_quote_types=("EQUITY", "ETF"), minimum_history_sessions=5,
        minimum_price=0.0, minimum_median_dollar_volume=0.0, require_company_name=False,
    )
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"SPY": _df(rows=5, close=1.0, volume=1)}
        mock_info.return_value = {"quoteType": "ETF", "exchange": "PCX", "longName": ""}
        verified, dropped = ticker_verification.verify_tickers(["SPY"], policy=lenient_policy)
    assert dropped == []
    assert len(verified) == 1


def test_partition_by_universe_splits_correctly():
    candidates = [{"ticker": "AAPL", "reason": "r1"}, {"ticker": "ZZZFAKE", "reason": "r2"}]
    from_universe, wildcard = ticker_verification.partition_by_universe(candidates, universe=["AAPL", "MSFT"])
    assert from_universe == [{"ticker": "AAPL", "reason": "r1"}]
    assert wildcard == [{"ticker": "ZZZFAKE", "reason": "r2"}]


def test_partition_by_universe_is_case_insensitive():
    candidates = [{"ticker": "aapl", "reason": "r1"}]
    from_universe, wildcard = ticker_verification.partition_by_universe(candidates, universe=["AAPL"])
    assert from_universe == [{"ticker": "aapl", "reason": "r1"}]
    assert wildcard == []


if __name__ == "__main__":
    test_verify_tickers_keeps_valid_ticker()
    test_verify_tickers_drops_ticker_not_in_fetch_historical_result()
    test_verify_tickers_drops_ticker_with_empty_info()
    test_verify_tickers_one_bad_ticker_does_not_abort_batch()
    test_verify_tickers_respects_max_checks_cap()
    test_verify_tickers_rejects_non_equity_quote_type()
    test_verify_tickers_rejects_short_history()
    test_verify_tickers_rejects_price_below_minimum()
    test_verify_tickers_rejects_illiquid_ticker()
    test_verify_tickers_rejects_missing_company_name()
    test_verify_tickers_rejects_non_us_exchange()
    test_verify_tickers_allowed_exchanges_none_disables_the_check()
    test_verify_tickers_custom_policy_can_relax_defaults()
    test_partition_by_universe_splits_correctly()
    test_partition_by_universe_is_case_insensitive()
    print("All ticker_verification tests passed.")


# --- Company-name resolution across yfinance's three name fields.
#
# Live-observed 2026-08-12: NBIS (Nebius Group N.V., Nasdaq NMS, ~$3.6B median
# daily dollar volume) returns longName=None across repeated fetches while
# carrying shortName and displayName. Reading only longName made a provider
# metadata gap look like a security with no identity, and require_company_name
# dropped it.

def test_verify_tickers_resolves_name_from_short_name_when_long_name_missing():
    info = {"longName": None, "shortName": "Nebius Group N.V.", "quoteType": "EQUITY", "exchange": "NMS"}
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"NBIS": _df()}
        mock_info.return_value = info
        verified, dropped = ticker_verification.verify_tickers(["NBIS"])
    assert dropped == []
    assert verified[0]["longName"] == "Nebius Group N.V."


def test_verify_tickers_resolves_name_from_display_name_when_others_missing():
    info = {"longName": None, "shortName": None, "displayName": "Nebius", "quoteType": "EQUITY", "exchange": "NMS"}
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"NBIS": _df()}
        mock_info.return_value = info
        verified, dropped = ticker_verification.verify_tickers(["NBIS"])
    assert dropped == []
    assert verified[0]["longName"] == "Nebius"


def test_verify_tickers_still_drops_when_every_name_field_is_missing():
    """require_company_name must still mean something: widening the lookup to
    three fields must not make it unfalsifiable."""
    info = {"longName": None, "shortName": None, "displayName": None, "quoteType": "EQUITY", "exchange": "NMS"}
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"NONAME": _df()}
        mock_info.return_value = info
        verified, dropped = ticker_verification.verify_tickers(["NONAME"])
    assert verified == []
    assert dropped == ["NONAME"]


# --- SUGGESTION_DISCLOSURE_POLICY: shows thin rows, still enforces identity.

def test_disclosure_policy_admits_a_young_but_hugely_liquid_listing():
    """The SPCX case that started this: 41 sessions against a 60-session floor,
    despite a ~$1.9T market cap and ~$10.7B median daily dollar volume. The
    strict policy must still reject it, so the difference is attributable to
    the policy and not to the fixture."""
    info = {"longName": "Space Exploration Technologies Corp.", "quoteType": "EQUITY", "exchange": "NMS"}
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"SPCX": _df(rows=41, close=144.91)}
        mock_info.return_value = info
        lenient, lenient_dropped = ticker_verification.verify_tickers(
            ["SPCX"], policy=ticker_verification.SUGGESTION_DISCLOSURE_POLICY
        )
        strict, strict_dropped = ticker_verification.verify_tickers(["SPCX"])
    assert lenient_dropped == [] and lenient[0]["history_sessions"] == 41
    assert strict == [] and strict_dropped == ["SPCX"]


def test_disclosure_policy_admits_a_low_priced_listing():
    """PLUG at $2.27 against the $5.00 floor."""
    info = {"longName": "Plug Power Inc.", "quoteType": "EQUITY", "exchange": "NCM"}
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"PLUG": _df(close=2.27)}
        mock_info.return_value = info
        verified, dropped = ticker_verification.verify_tickers(
            ["PLUG"], policy=ticker_verification.SUGGESTION_DISCLOSURE_POLICY
        )
    assert dropped == []
    assert verified[0]["last_price"] == 2.27


def test_disclosure_policy_still_drops_non_equity_and_non_us_listings():
    """The identity floor is what stops an LLM-authored symbol from rendering
    as a suggestion; relaxing the size screen must not relax this."""
    etf = {"longName": "SPDR S&P 500 ETF Trust", "quoteType": "ETF", "exchange": "PCX"}
    foreign = {"longName": "Some Foreign Listing", "quoteType": "EQUITY", "exchange": "LSE"}
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"SPY": _df(), "FGN": _df()}
        mock_info.side_effect = lambda t: etf if t == "SPY" else foreign
        verified, dropped = ticker_verification.verify_tickers(
            ["SPY", "FGN"], policy=ticker_verification.SUGGESTION_DISCLOSURE_POLICY
        )
    assert verified == []
    assert sorted(dropped) == ["FGN", "SPY"]


def test_disclosure_policy_still_drops_a_symbol_that_does_not_resolve():
    with patch("assistant.ticker_verification.fetch_historical", return_value={}):
        verified, dropped = ticker_verification.verify_tickers(
            ["HALLUCINATED"], policy=ticker_verification.SUGGESTION_DISCLOSURE_POLICY
        )
    assert verified == []
    assert dropped == ["HALLUCINATED"]


def test_disclosure_policy_still_requires_a_company_identity():
    """AP-8 removed size/age/price judgments, not the company identity floor."""
    info = {
        "longName": None,
        "shortName": None,
        "displayName": None,
        "quoteType": "EQUITY",
        "exchange": "NMS",
    }
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"NONAME": _df()}
        mock_info.return_value = info
        verified, dropped = ticker_verification.verify_tickers(
            ["NONAME"], policy=ticker_verification.SUGGESTION_DISCLOSURE_POLICY
        )
    assert verified == []
    assert dropped == ["NONAME"]


@pytest.mark.parametrize("bad_close", [0.0, float("inf"), float("-inf")])
def test_disclosure_policy_rejects_invalid_close_as_not_verified(bad_close):
    """Removing the $5 screen must not turn invalid market data into identity."""
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"BAD": _df(close=bad_close)}
        mock_info.return_value = _ELIGIBLE_INFO
        verified, dropped = ticker_verification.verify_tickers(
            ["BAD"], policy=ticker_verification.SUGGESTION_DISCLOSURE_POLICY
        )
    assert verified == []
    assert dropped == ["BAD"]


def test_malformed_close_drops_only_that_ticker_instead_of_aborting_batch():
    frames = {"BAD": _df(close="not-a-price"), "GOOD": _df()}
    with patch("assistant.ticker_verification.fetch_historical", return_value=frames), \
         patch("assistant.ticker_verification._safe_ticker_info", return_value=_ELIGIBLE_INFO):
        verified, dropped = ticker_verification.verify_tickers(
            ["BAD", "GOOD"], policy=ticker_verification.SUGGESTION_DISCLOSURE_POLICY
        )
    assert [row["ticker"] for row in verified] == ["GOOD"]
    assert dropped == ["BAD"]


def test_disclosure_policy_preserves_unavailable_liquidity_as_unavailable():
    """No volume column is not measured zero-dollar volume."""
    frame = _df().drop(columns=["volume"])
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"NOVOL": frame}
        mock_info.return_value = _ELIGIBLE_INFO
        verified, dropped = ticker_verification.verify_tickers(
            ["NOVOL"], policy=ticker_verification.SUGGESTION_DISCLOSURE_POLICY
        )
    assert dropped == []
    assert verified[0]["median_dollar_volume"] is None


def test_recent_ipo_policy_import_remains_available_for_compatibility():
    """AP-8 changes the caller policy; it need not break the prior import."""
    policy = ticker_verification.RECENT_IPO_ELIGIBILITY_POLICY
    assert policy.minimum_history_sessions == 3
    assert policy.require_company_name is True


def test_unusable_index_drops_only_that_ticker_instead_of_aborting_batch():
    """Counter-review AP8CR-002. The review restored batch isolation for a
    malformed close, but first_session_date was still derived unguarded, so a
    frame with an unexpected index raised out of the loop and took every good
    ticker in the batch with it."""
    odd = pd.DataFrame({"close": [100.0] * 70, "volume": [50_000_000] * 70})  # no datetime index
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"ODD": odd, "AAPL": _df()}
        mock_info.return_value = _ELIGIBLE_INFO
        verified, dropped = ticker_verification.verify_tickers(
            ["ODD", "AAPL"], policy=ticker_verification.SUGGESTION_DISCLOSURE_POLICY
        )
    assert [v["ticker"] for v in verified] == ["AAPL"]
    assert dropped == ["ODD"]


def test_verified_first_session_date_is_the_frames_first_bar():
    """The drop path above must not be reachable for ordinary frames, and the
    value must still be the real first bar -- _is_ipo_identity_mismatch()
    treats a missing date as 'no mismatch', so a silent '' would disarm the
    reused/renamed-symbol guard rather than trip it."""
    with patch("assistant.ticker_verification.fetch_historical") as mock_fetch, \
         patch("assistant.ticker_verification._safe_ticker_info") as mock_info:
        mock_fetch.return_value = {"AAPL": _df()}
        mock_info.return_value = _ELIGIBLE_INFO
        verified, dropped = ticker_verification.verify_tickers(["AAPL"])
    assert dropped == []
    assert verified[0]["first_session_date"] == "2026-01-01"
