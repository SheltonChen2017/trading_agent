"""Read-only anchor audit reproductions; all input evidence is fabricated."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
import test_short_interest_native_reported_anchor_plan as fixtures
import pytest


def test_gap_is_class_fence_even_when_same_class_returns_under_new_symbol():
    dates = ("2023-01-13", "2023-01-31", "2023-02-15")
    source = fixtures.plan(dates,
        reports=(fixtures.identity(dates[0]), fixtures.identity(dates[1], malformed=True),
                 fixtures.identity(dates[2], ticker="NEW")),
        cells=[("SYN", dates[0]), ("SYN", dates[1]), ("NEW", dates[2])])
    anchors = list(source.iter_anchors())
    assert source.to_payload()["exact_request_budget"] == 2
    assert {row["query_asof_date"] for row in anchors} == {dates[0], dates[2]}
    assert "first_valid_identity_after_gap" in next(row for row in anchors
        if row["query_asof_date"] == dates[2])["refresh_reasons"]


def test_count_registry_iter_cells_rechecks_seal_after_first_yield():
    source = fixtures.plan(("2023-01-13", "2023-04-14"))
    captures = [fixtures.response(query) for query in source.query_plan.iter_queries()]
    registry = fixtures.draft.qualify_native_reported_counts(source, captures)
    cells = registry.iter_cells()
    assert next(cells)["same_class_count"]["numerator"] == 100
    replacements = list(registry._records)
    changed = json.loads(replacements[1])
    changed["same_class_count"]["numerator"] = 999
    replacements[1] = json.dumps(changed).encode()
    object.__setattr__(registry, "_records", tuple(replacements))
    with pytest.raises(fixtures.draft.AnchorError, match="sealed_count_registry_changed"):
        next(cells)
