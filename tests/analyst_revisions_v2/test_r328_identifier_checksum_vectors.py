"""Section 328: letter and special-character identifier checksum vectors.

The crosswalk and ISIN tests used only all-digit CUSIPs and one all-digit
ISIN, so a broken letter or '*'/'@'/'#' mapping would still pass them. The
expected check digits below were computed by hand from the CUSIP, ISIN
(ISO 6166 Luhn) and FIGI rules, independently of the module under test.
"""
import pytest

from scripts import arv2_r298_eodhd_crosswalk as m


@pytest.mark.parametrize('value', ('78462F103', '82509L107', '12*4@6#87', '*@#ABC124'))
def test_letter_and_special_character_cusips_validate(value):
    assert m._cusip(value)


@pytest.mark.parametrize('value', ('78462F104', '82509L106', '12*4@6#88', '*@#ABC125',
    '@*#ABC124', '1*24@6#87', '78462G103'))
def test_wrong_check_digit_or_transposed_special_characters_refuse(value):
    assert not m._cusip(value)


@pytest.mark.parametrize('value', ('US78462F1030', 'CA82509L1076'))
def test_letter_bearing_isins_validate(value):
    assert m._isin(value)


@pytest.mark.parametrize('value', ('US78462F1031', 'CA82509L1077', 'US78462G1030', 'CA82509L1067'))
def test_letter_bearing_isins_with_altered_letter_or_check_digit_refuse(value):
    assert not m._isin(value)


def test_letter_figi_vectors_and_check_digit():
    assert m._figi('BBG000BLNNH6') and m._figi('BBG000B9XRY4')
    assert not m._figi('BBG000BLNNH7') and not m._figi('BBG000BLNMH6')
