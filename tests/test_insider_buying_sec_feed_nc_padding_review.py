"""Claude review section 342 (IBNC-CR34201): a member whose padding the frozen
shape observer flagged as non-zero is neither examined nor routed.

Invented prefixes only, in a separate file so pinned test hashes are unchanged.
"""
import importlib.util
from pathlib import Path

from research import insider_buying_sec_feed_nc_source_binding_observe_v1 as observe

_SPEC = importlib.util.spec_from_file_location(
    "nc_structure_test_helpers", Path(__file__).with_name("test_insider_buying_sec_feed_prefix_nc_structure_v1.py"))
t = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(t)


def _decoded(first_padding_byte):
    payload = t._payload()
    padding = (-len(payload)) % 512
    assert padding > 1
    return t._header(len(payload)) + payload + bytes([first_padding_byte]) + bytes(padding - 1) + bytes(1024)


def test_nonzero_padding_member_is_not_examined_by_the_structure_diagnostic():
    clean = t._qualify(decoded=_decoded(0))
    assert clean["members"][0]["inspection_disposition"] == "examined_complete_observed_NC_payload"
    flagged = t._qualify(decoded=_decoded(1))
    member = flagged["members"][0]
    assert member["inspection_disposition"] == "nonzero_padding_member_not_examined"
    assert (member["NC_structure"]["status"], member["NC_structure"]["reason"]) == ("not_examined", "nonzero_padding_member_not_examined")
    assert flagged["accounting"]["complete_NC_payloads_examined"] == 0


def test_nonzero_padding_member_is_not_collected_for_routing():
    collected, geometry = observe._collect(t._gzip(_decoded(0)), t.CONTACT, True)
    assert len(collected) == 1
    collected, geometry = observe._collect(t._gzip(_decoded(1)), t.CONTACT, True)
    assert collected == () and geometry["member_dispositions"] == ["nonzero_padding_member_not_examined"]
    assert "nonzero_padding_member_not_examined" in observe._REASONS
