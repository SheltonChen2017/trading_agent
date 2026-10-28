"""Claude review section 342 (IBNC-CR34202): the binder's NC member accounting
flag is derived from the route batch, not a tautology.

Kept outside the binder's pinned test file so its pinned hash is unchanged.
"""
from research import insider_buying_sec_feed_nc_source_binding_v1 as binder


def _public(*, members, eligible, dispositions, records):
    batch = {"members": members, "eligible_private_claims": eligible, "disposition_counts": dispositions}
    body = {"fixture_only": True, "counts": {}, "context_form_counts": {}, "pilot_form_counts": {}}
    rows = tuple((index, (), "invented_disposition") for index in range(records))
    return binder._public(batch, body, {}, rows)["all_input_NC_members_accounted"]


def test_member_accounting_flag_reflects_the_route_batch():
    assert _public(members=3, eligible=2, dispositions={"a": 2, "b": 1}, records=2) is True
    assert _public(members=3, eligible=2, dispositions={"a": 2, "b": 1}, records=1) is False
    assert _public(members=3, eligible=2, dispositions={"a": 2}, records=2) is False
