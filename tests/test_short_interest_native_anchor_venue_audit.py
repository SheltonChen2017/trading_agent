"""Main's source-free, pre-request regressions; no factual listing admission."""
import pytest
import test_short_interest_native_reported_anchor_plan as fixtures
from data.hashing import canonical_json


def test_inactive_panel_relation_is_not_a_positive_asof_listing_for_count_budget():
    dates = ("2023-01-13", "2023-04-14")
    source = fixtures.identity(dates[1])
    value = source.to_payload()
    # Independently fabricate a previously qualified inactive-source relation.
    value["rows"][0][9] = False
    raw = canonical_json(value).encode()
    negative = object.__new__(fixtures.identities.DatedIdentityQualification)
    anchor = (raw,)
    for name, content in (("_bytes", raw), ("_anchor", anchor), ("_identity", anchor)):
        object.__setattr__(negative, name, content)
    plan = fixtures.plan(dates, reports=(fixtures.identity(dates[0]), negative))
    assert plan.to_payload()["exact_request_budget"] == 1
    assert "dated_source_inactive_or_unobserved_listing_status" in list(plan.iter_cells())[1]["refusal_reasons"]


@pytest.mark.parametrize("venue", [None, "OTCM", "TRFN", "ZZZZ"])
def test_unqualified_listing_namespace_cannot_consume_a_count_query(venue):
    dates = ("2023-01-13", "2023-04-14")
    source = fixtures.plan(dates, reports=(fixtures.identity(dates[0]),
                           fixtures.identity(dates[1], venue=venue)))
    assert source.to_payload()["exact_request_budget"] == 1
    cells = list(source.iter_cells())
    assert not cells[0]["refusal_reasons"]
    assert "source_listing_venue_namespace_unqualified" in cells[1]["refusal_reasons"]
    assert cells[1]["anchor_original_query_ordinal"] is None
    assert cells[1]["source_origin"]["row_index"] == 1


@pytest.mark.parametrize("method,part", [("iter_cells", "_cells"), ("iter_anchors", "_anchors"),
                                       ("iter_parts", "_cells")])
def test_plan_stream_rechecks_original_seal_at_every_yield(method, part):
    source = fixtures.plan(("2023-01-13", "2023-04-14"))
    stream = getattr(source, method)()
    next(stream)
    object.__setattr__(source, part, bytes(bytearray(getattr(source, part))))
    with pytest.raises(fixtures.draft.AnchorError, match="sealed_anchor_plan_changed"):
        next(stream)
