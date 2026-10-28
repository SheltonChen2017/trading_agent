"""Claude review section 341: route guards that in-memory mutants survived.

Invented payloads only. Kept outside the route's pinned test files so these
pins do not change the binder/observer code-dependency hashes.
"""
import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "nc_route_v1_test_helpers", Path(__file__).with_name("test_insider_buying_sec_feed_nc_route_v1.py"))
t = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(t)
m = t.m


def test_TEXT_opening_before_a_later_qualified_header_still_refuses_the_batch():
    # Without the front's TEXT barrier check, scanning would run on to the
    # later qualified header and report a complete shadow front.
    raw = t._payload().replace(b"<SUBMISSION>\n", b"<SUBMISSION>\n<TEXT>\n", 1)
    assert t._assess(raw).claim is None
    with pytest.raises(m.NCRouteError) as caught:
        t._batch((t._payload(accession=t.OTHER), raw))
    assert (caught.value.phase, caught.value.code) == ("structure", "shadow_front_unqualified")


@pytest.mark.parametrize("docs", [
    lambda: t._doc(seq=b"2"),
    lambda: t._doc(seq=b"1") + t._doc(form=b"EX-99", seq=b"3"),
])
def test_document_sequence_must_count_from_one_without_gaps(docs):
    count = b"2" if docs().count(b"<DOCUMENT>") == 2 else b"1"
    assert t._assess(t._payload(docs=docs(), count=count)).claim is None
    assert t._assess(t._payload(docs=t._doc(seq=b"1") + t._doc(form=b"EX-99", seq=b"2"), count=b"2")).claim is not None
