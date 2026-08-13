"""Behavioral coverage for the Buying page's AI allocation-review surface.

Owner-reported 2026-08-12: the page rendered NOTHING when Claude's review came
back rejected -- visually identical to never having ticked the checkbox. Two
real reviews were discarded that afternoon and there was no way to tell from
the screen whether the feature was broken, switched off, or somewhere the user
had not scrolled. These tests pin the fix behaviorally, in the real app.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from assistant.ai_advisor import (
    AllocationObservation,
    AllocationReview,
    AllocationReviewOutcome,
    REVIEW_REJECTED_ALL_OBSERVATIONS,
    allocation_review_input_hash,
)
from config import BASKETS


_APP_PATH = Path(__file__).resolve().parents[1] / "scripts" / "personal_assistant_ui.py"


@pytest.fixture()
def _offline_buying_environment(monkeypatch):
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)
    # Presence only -- it makes the checkbox selectable. No call is made:
    # every test seeds the outcome directly rather than reaching the network.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    import assistant.data_integrity as data_integrity

    monkeypatch.setattr(data_integrity, "fetch_daily_bars_recorded", lambda *a, **k: {})

    import data.event_data as event_data

    monkeypatch.setattr(
        event_data, "fetch_upcoming_earnings", lambda *a, **k: [], raising=False
    )


def _result_row(vol: float, price: float) -> dict:
    """One ticker's entry in session_state["watchlist_results"], shaped as the
    real cart check builds it. Two of these make the split -- and therefore the
    review slot -- render without any network call."""
    return {
        "own_trend": "flat",
        "own_vol": vol,
        "current_price": price,
        "price_as_of": "2026-08-12",
        "price_history": None,
        # A dict, not a string, and the page reads four specific keys of it.
        "explanation": {
            "currently_held": None,
            "triggered_today": False,
            "historical_evidence": [],
            "note": "",
        },
        "price_targets": [],
        "hold_range": None,
        "news": [],
        "news_summary": None,
        "news_summary_reason": None,
        "earnings": {"available": False},
    }


_REVIEW_CHECKBOX = "Get an AI review of the purchase split with Claude"


def _bound_outcome(review=None, rejection_reason=None) -> AllocationReviewOutcome:
    weights = {"NVDA": 66.7, "AMD": 33.3}
    vols = {"NVDA": 2.0, "AMD": 4.0}
    baskets = {
        ticker: [name for name, members in BASKETS.items() if ticker in members]
        for ticker in weights
    }
    return AllocationReviewOutcome(
        review,
        rejection_reason,
        allocation_review_input_hash(list(weights), weights, vols, baskets),
    )


def _buying_app(outcome, *, want_review: bool = True) -> AppTest:
    """Drive the page the way a user reaches this state.

    Two runs are required and the reason is load-bearing. The page CLEARS any
    stored review whenever the checkbox is unticked -- correct behavior, and
    also why seeding session_state before the first run proves nothing: the
    first run wipes it. So run once to create the widgets, tick the box, seed
    the review, and run again. A test that skipped this would assert against a
    page that never entered the branch at all, and would pass whatever the
    branch did.
    """
    app = AppTest.from_file(str(_APP_PATH), default_timeout=180)
    app.session_state["nav_page"] = "Buying"
    app.session_state["ai_pref_master"] = True
    app.session_state["ai_pref_allocation_commentary"] = True
    app.session_state["watchlist_results"] = {
        "NVDA": _result_row(2.0, 100.0),
        "AMD": _result_row(4.0, 50.0),
    }
    app.run()

    if want_review:
        box = next(c for c in app.checkbox if c.label.startswith(_REVIEW_CHECKBOX))
        box.check()
    app.session_state["watchlist_ai_review_outcome"] = outcome
    app.run()
    return app


def test_rejected_review_explains_itself_instead_of_rendering_nothing(
    _offline_buying_environment,
):
    app = _buying_app(_bound_outcome(None, REVIEW_REJECTED_ALL_OBSERVATIONS))

    assert not app.exception
    # Prove the branch under test actually rendered. Without this, every
    # absence assertion below would pass on a page that never got there.
    assert "Inverse-volatility purchase split" in [s.value for s in app.subheader]
    warnings = "\n".join(element.value for element in app.warning)
    assert "requested but is not being" in warnings
    assert REVIEW_REJECTED_ALL_OBSERVATIONS in warnings
    # The computed split is this project's own code and must be presented as
    # unaffected by an AI failure.
    assert "split above is unaffected" in warnings.replace("\n", " ")


def test_successful_review_renders_and_warns_about_nothing(
    _offline_buying_environment,
):
    review = AllocationReview(
        summary="This split leans on one industry.",
        observations=(
            AllocationObservation(
                type="concentration",
                severity="high",
                claim="Both are semiconductor names.",
                tickers=("NVDA", "AMD"),
            ),
        ),
    )
    app = _buying_app(_bound_outcome(review, None))

    assert not app.exception
    # Prove the branch under test actually rendered. Without this, every
    # absence assertion below would pass on a page that never got there.
    assert "Inverse-volatility purchase split" in [s.value for s in app.subheader]
    warnings = "\n".join(element.value for element in app.warning)
    assert "is not being shown" not in warnings


def test_never_asking_produces_neither_a_review_nor_a_warning(
    _offline_buying_environment,
):
    """The whole point of the fix is that these three states now LOOK
    different. A user who never ticked the box must not be told a review was
    rejected."""
    app = _buying_app(None, want_review=False)

    assert not app.exception
    # Prove the branch under test actually rendered. Without this, every
    # absence assertion below would pass on a page that never got there.
    assert "Inverse-volatility purchase split" in [s.value for s in app.subheader]
    warnings = "\n".join(element.value for element in app.warning)
    assert "is not being shown" not in warnings


def test_review_is_not_displayed_against_a_changed_split(
    _offline_buying_environment,
):
    """An AI claim that was checked against one split must never remain under
    a different split after a slider rerun."""
    summary = "This is the review of the original split."
    review = AllocationReview(summary=summary, observations=())
    app = _buying_app(_bound_outcome(review, None))
    assert summary in [element.value for element in app.markdown]

    slider = next(
        s for s in app.slider if s.label == "Max weight per ticker in the split (%)"
    )
    slider.set_value(50.0)
    app.run()

    assert not app.exception
    warnings = "\n".join(element.value for element in app.warning)
    assert "split changed since Claude reviewed it" in warnings
    assert summary not in [element.value for element in app.markdown]


def test_similar_suggestions_are_not_displayed_against_a_changed_cart(
    _offline_buying_environment,
):
    """Counter-review AP9CR-002 -- the generalized instance of AP9R-001 one
    block above it: suggestions and their measured-evidence columns computed
    for one cart rendered under an expander header naming whatever the cart
    says NOW."""
    app = AppTest.from_file(str(_APP_PATH), default_timeout=180)
    app.session_state["nav_page"] = "Buying"
    app.session_state["watchlist_typed"] = "NVDA, AMD"
    app.session_state["watchlist_ai_suggestions"] = {
        "cart": ["AMD", "NVDA"],
        "from_universe": [],
        "verified": [{"ticker": "TSM", "longName": "TSMC"}],
        "dropped": [],
        "reason_by_ticker": {"TSM": "similar business"},
        "evidence_by_ticker": {"TSM": "correlation vs old cart"},
    }
    app.run()
    assert not app.exception
    warnings = "\n".join(element.value for element in app.warning)
    assert "cart changed since Claude suggested" not in warnings, (
        "matching cart must not be reported stale"
    )

    # The user edits the cart without clicking Check cart.
    app.session_state["watchlist_typed"] = "NVDA, AMD, TSLA"
    app.run()
    assert not app.exception
    warnings = "\n".join(element.value for element in app.warning)
    assert "cart changed since Claude suggested" in warnings
    expanders = [e.label for e in app.expander]
    assert not any("Claude's own suggestions" in label for label in expanders), (
        "stale suggestions must be hidden, not just captioned"
    )


def test_legacy_suggestions_without_a_cart_key_fail_safe_as_stale(
    _offline_buying_environment,
):
    app = AppTest.from_file(str(_APP_PATH), default_timeout=180)
    app.session_state["nav_page"] = "Buying"
    app.session_state["watchlist_typed"] = "NVDA, AMD"
    app.session_state["watchlist_ai_suggestions"] = {
        "from_universe": [],
        "verified": [{"ticker": "TSM", "longName": "TSMC"}],
        "dropped": [],
        "reason_by_ticker": {"TSM": "similar business"},
        "evidence_by_ticker": {"TSM": "correlation vs unknown cart"},
    }
    app.run()
    assert not app.exception
    warnings = "\n".join(element.value for element in app.warning)
    assert "cart changed since Claude suggested" in warnings
