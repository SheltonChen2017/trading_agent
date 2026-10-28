"""Section 328: a real QC success envelope may omit `errors` (W5 result parser).

Every lane reader that consumed actual QC responses accepts an absent
`errors` key, and the record retains a real HTTP200/success=true envelope
with `errors` missing. Requiring the key would refuse all six spent reads.
"""
import copy

import pytest

from scripts import arv2_r327_available_history_result as m
from tests.analyst_revisions_v2.test_r327_available_history_result import (  # noqa: F401
    case, checked, family, refused, select)


def test_success_envelope_without_errors_key_selects_and_validates_identically(case):
    response = copy.deepcopy(case['response'])
    del response['errors']
    selected, selected_pin = select(case, response)
    assert (selected, selected_pin) == select(case)
    assert selected['response_error_count'] == 0
    assert checked(case, m.canonical(selected), selected_pin)['selected'] == selected


@pytest.mark.parametrize('value', (None, ['DO-NOT-OUTPUT'], {}, '', 0))
def test_present_errors_must_still_be_an_empty_list(case, value):
    response = copy.deepcopy(case['response'])
    response['errors'] = value
    refused('response_errors', lambda: select(case, response))
