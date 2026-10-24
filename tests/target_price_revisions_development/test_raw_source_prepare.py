"""Synthetic source projection tests, without retained or operator inputs."""
from copy import deepcopy
import pytest
from research.target_price_revisions_development.raw_source_prepare import prepare_sources


def inputs():
    massive = {"schema": "tpr-raw-source-projection-v1", "complete": True, "capture_utc": "2026-10-08T01:00:00Z",
        "ratings": [{"date": "2025-01-02", "ticker": "TEST", "price_target": None}]}
    sharadar = {"schema": "tpr-sharadar-native-source-v1", "pagination_terminated": True,
        "capture_utc": "2026-10-08T02:00:00Z", "source_window": {"from": "2024-08-01", "to": "2025-03-31"},
        "refusals": {"tickers": [], "actions": []}, "tickers": [{"ticker": "TEST", "permaticker": "123",
        "figi": None, "category": "Domestic Common Stock", "exchange": "NYSE", "isdelisted": "N"}],
        "actions": [{"ticker": "TEST", "date": "2025-03-01", "action": "split", "contraticker": None}]}
    return massive, sharadar, [{"session_date": "2024-12-31"}, {"session_date": "2025-01-02"}]


def test_preserves_future_actions_missing_figi_and_invalid_target_for_later_disposition():
    m, s, c = inputs()
    result, report = prepare_sources(m, s, c)
    assert result["actions"] == [{"ticker": "TEST", "date": "2025-03-01", "action": "split"}]
    assert result["identities"][0]["figi"] is None
    assert result["identities"][0]["security_id"] == "SHARADAR:123"
    assert result["ratings"][0]["price_target"] is None
    assert report["real_backtest_ready"] is report["global_source_completeness_proven"] is False
    assert report["outcome_reads"] == report["development_looks"] == 0


@pytest.mark.parametrize("value", [None, 20250102, "2025-02-30", "2024-07-31", "2025-04-01", "20250102"])
def test_invalid_source_date_named_not_silently_repaired(value):
    m, s, c = inputs()
    m["ratings"].append(dict(m["ratings"][0], date=value))
    result, report = prepare_sources(m, s, c)
    assert len(result["ratings"]) == 1
    assert report["invalid_or_outside_source_date"] == 1


@pytest.mark.parametrize("change", [
    lambda m,s: m.update(complete=False), lambda m,s: s.update(pagination_terminated=False),
    lambda m,s: s["refusals"]["actions"].append({"reason": "invalid_native_date"}),
    lambda m,s: s["tickers"][0].update(isdelisted="unknown"),
    lambda m,s: s["actions"][0].update(value="2"),
])
def test_incomplete_or_unscoped_source_refuses(change):
    m, s, c = inputs()
    change(m,s)
    with pytest.raises(ValueError): prepare_sources(m,s,c)


def test_source_projection_does_not_mutate_authenticated_inputs():
    values = inputs()
    original = deepcopy(values)
    prepare_sources(*values)
    assert values == original
