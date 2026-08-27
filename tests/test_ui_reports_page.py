"""GR-7a: the Reports page's tax export through the real Streamlit app.

Seeds one round-trip fill in a test-isolated database, builds the
report through the actual page, and pins the honesty contract the artifact
depends on: coverage status is stated, wash-sale wording stays advisory,
the export is downloadable, and the page proposes nothing.

Run with: python -m pytest tests/test_ui_reports_page.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.storage import AssistantStore

_APP_PATH = Path(__file__).resolve().parents[1] / "scripts" / "personal_assistant_ui.py"
UTC = timezone.utc
_BUY_AT = datetime(2026, 1, 6, 15, 0, tzinfo=UTC)
_SELL_AT = datetime(2026, 2, 9, 15, 0, tzinfo=UTC)


def _seed_fill(store, fill_id, ticker, side, qty, price, at):
    from assistant.order_lifecycle import journal_broker_order_update

    proposal_id = f"p-{fill_id}"
    store.save_proposal(
        {
            "proposal_id": proposal_id,
            "created_at": at.isoformat(),
            "expires_at": (at + timedelta(hours=4)).isoformat(),
            "status": "filled",
            "idempotency_key": f"idem-{proposal_id}",
            "intent": {
                "ticker": ticker,
                "side": side,
                "shares": qty,
                "order_type": "market",
                "limit_price": None,
            },
        }
    )
    journal_broker_order_update(
        store,
        proposal_id,
        {
            "order_id": f"o-{fill_id}",
            "client_order_id": f"idem-{proposal_id}",
            "ticker": ticker,
            "shares": float(qty),
            "side": side,
            "type": "market",
            "limit_price": None,
            "time_in_force": "day",
            "status": "filled",
            "filled_qty": float(qty),
            "filled_avg_price": float(price),
            "submitted_at": at.isoformat(),
            "updated_at": None,
        },
        event_type="fill",
        event_at=at.isoformat(),
        fill_qty=float(qty),
        fill_price=float(price),
    )


@pytest.fixture()
def seeded_round_trip(tmp_path, monkeypatch):
    """One completed AAPL round trip: 10 @ 100 bought, 10 @ 150 sold."""
    database = tmp_path / "assistant.db"
    monkeypatch.setenv("TRADING_ASSISTANT_DB", str(database))
    # ``personal_assistant_ui._store`` is a cached no-argument resource. Clear
    # it after changing the environment so AppTest honors this private path,
    # then clear it again so later UI tests reopen the restored session path.
    st.cache_resource.clear()
    store = AssistantStore(database)
    _seed_fill(store, "gr7a-buy", "AAPL", "buy", 10, 100.0, _BUY_AT)
    _seed_fill(store, "gr7a-sell", "AAPL", "sell", 10, 150.0, _SELL_AT)
    try:
        yield store
    finally:
        st.cache_resource.clear()


def _reports_app() -> AppTest:
    app = AppTest.from_file(str(_APP_PATH), default_timeout=180)
    app.session_state["nav_page"] = "Reports"
    app.run()
    assert not app.exception
    return app


def _build_2026(app: AppTest) -> AppTest:
    app.number_input(key="tax_report_year").set_value(2026).run()
    app.button(key="tax_report_build").click().run()
    assert not app.exception
    return app


def test_reports_page_renders_without_building_anything(seeded_round_trip):
    """Opening the page must not compute or fetch: reporting is on demand."""
    app = _reports_app()
    assert "tax_report" not in app.session_state
    infos = " ".join(str(i.value) for i in app.info)
    captions = " ".join(str(c.value) for c in app.caption)
    assert "not tax advice" in captions.lower()


def test_building_the_report_shows_totals_and_the_realized_row(seeded_round_trip):
    app = _build_2026(_reports_app())

    report = app.session_state["tax_report"]
    assert report.tax_year == 2026
    assert report.total.sale_count == 1
    # Decimal comparison, not string: Decimal("500.0") == Decimal("500"),
    # and the exported TEXT is canonicalized separately by decimal_text.
    assert report.total.realized_pnl == Decimal("500")

    frames = [f.value for f in app.dataframe if hasattr(f.value, "columns")]
    bucket_frames = [f for f in frames if "Bucket" in f.columns]
    assert bucket_frames, "totals table did not render"
    row_frames = [f for f in frames if "realized_pnl" in f.columns]
    assert row_frames, "per-lot rows did not render"
    assert "AAPL" in list(row_frames[0]["ticker"])


def test_page_states_coverage_and_keeps_wash_sale_wording_advisory(
    seeded_round_trip,
):
    app = _build_2026(_reports_app())
    surfaces = " ".join(
        [str(w.value) for w in app.warning]
        + [str(e.value) for e in app.error]
        + [str(s.value) for s in app.success]
    )
    # Without a live broker, Build must stay UNVERIFIED -- never COMPLETE
    # against SAMPLE_POSITIONS.
    assert "Coverage UNVERIFIED" in surfaces
    assert "Coverage COMPLETE" not in surfaces
    captions = " ".join(str(c.value) for c in app.caption)
    assert "advisory only" in captions
    assert "cost basis is never adjusted" in captions.lower()


def test_building_the_report_does_not_write_provider_fetch_rows(seeded_round_trip):
    store = seeded_round_trip
    with store._connect() as connection:
        before = connection.execute(
            "SELECT COUNT(*) FROM data_provider_fetches"
        ).fetchone()[0]
    _build_2026(_reports_app())
    with store._connect() as connection:
        after = connection.execute(
            "SELECT COUNT(*) FROM data_provider_fetches"
        ).fetchone()[0]
    assert after == before


def test_report_is_downloadable_in_both_formats(seeded_round_trip):
    app = _build_2026(_reports_app())
    # AppTest declares `download_button` but this Streamlit build raises on
    # the attribute; the generic element accessor is the stable path.
    labels = [str(b.label) for b in app.get("download_button")]
    assert "Download CSV" in labels
    assert "Download JSON" in labels


def test_a_year_with_no_sales_says_so_rather_than_showing_an_empty_table(
    seeded_round_trip,
):
    app = _reports_app()
    app.number_input(key="tax_report_year").set_value(2019).run()
    app.button(key="tax_report_build").click().run()
    assert not app.exception
    assert app.session_state["tax_report"].total.sale_count == 0
    infos = " ".join(str(i.value) for i in app.info)
    assert "No realized sales recorded in tax year 2019" in infos


def test_reports_page_has_no_action_shaped_controls(seeded_round_trip):
    """The read-only boundary: nothing here may lead toward a trade."""
    app = _build_2026(_reports_app())
    labels = [str(b.label).lower() for b in app.button]
    for forbidden in ("approve", "submit", "cancel", "propose", "dismiss"):
        assert not any(forbidden in label for label in labels), forbidden
