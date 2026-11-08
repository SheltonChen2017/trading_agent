"""FirstRate price-format JSON helpers keep their finite refusal codes.

Claude review R337 (ARV2R337-001). `Refused` subclasses `ValueError`, so the
generic handlers in `canonical` and `loads` used to relabel an internal
`bound` refusal as `json`. Synthetic values only.
"""
import pytest

from research.analyst_revisions_v2_qc import newrule_firstrate_price_format as m


def code(operation):
    with pytest.raises(m.Refused) as caught:
        operation()
    return m.finite(caught.value)


def test_canonical_node_and_depth_limits_refuse_as_bound(monkeypatch):
    monkeypatch.setattr(m, 'MAX_JSON_NODES', 1)
    assert code(lambda: m.canonical({'a': [1]})) == 'bound'
    monkeypatch.setattr(m, 'MAX_JSON_NODES', 1000)
    monkeypatch.setattr(m, 'MAX_JSON_DEPTH', 0)
    assert code(lambda: m.canonical({'a': 1})) == 'bound'


def test_loads_reports_a_bounded_nested_payload_as_bound(monkeypatch):
    monkeypatch.setattr(m, 'MAX_JSON_DEPTH', 1)
    assert code(lambda: m.loads(b'{"a":{"b":1}}', 100)) == 'bound'


@pytest.mark.parametrize('raw', [b'{"a":1,"a":1}', b'{"a":NaN}', b'{"a":1.5}', b'{"a": 1}', b'\xff'])
def test_malformed_or_noncanonical_json_still_refuses_as_json(raw):
    assert code(lambda: m.loads(raw, 100)) == 'json'


def test_unsupported_types_still_refuse_as_json():
    assert code(lambda: m.canonical({'a': 1.5})) == 'json'
    assert code(lambda: m.canonical({1: 'a'})) == 'json'
