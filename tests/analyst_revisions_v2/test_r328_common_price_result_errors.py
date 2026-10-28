"""Section 328: a real QC success envelope may omit `errors` (R298 result parser).

The held R298 common-price result parser had the same strict `errors`
requirement as its W5 successor; absence is the shape real readers accept.
"""
import copy

import pytest

from scripts import arv2_r298_common_price_result as m
from tests.analyst_revisions_v2.test_r298_common_price_result import (  # noqa: F401
    case, refused, select, validate)


def test_success_envelope_without_errors_key_selects_and_validates_identically(case):
    response = copy.deepcopy(case['response'])
    del response['errors']
    selected, selected_pin = select(case, response)
    assert (selected, selected_pin) == select(case)
    assert validate(case, m.canonical(selected), selected_pin)['selected'] == selected


@pytest.mark.parametrize('value', (None, ['PRIVATE'], {}, '', 0))
def test_present_errors_must_still_be_an_empty_list(case, value):
    response = copy.deepcopy(case['response'])
    response['errors'] = value
    refused('response_errors', lambda: select(case, response))
