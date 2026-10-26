"""Freeze the owner-directed offline scope, not empirical/QC acceptance."""
from pathlib import Path
import re

import pytest

RECORD = Path(__file__).resolve().parents[2] / 'docs/Strategy Description/TARGET_PRICE_REVISION_IMPLEMENTATION_RECORD.md'
EXPECTED = (
    ('Provider access', 'Thirteen fresh bounded Sharadar GETs; redacted metadata only'),
    ('QC access', 'Forbidden; zero API, UI, Mia, notebook, upload or launch effects'),
    ('Offline build', 'Pure runtime-successor and coverage-diagnostic software with synthetic tests'),
    ('Executed strategy and inputs', 'Unchanged; no provider substitution or unit conversion'),
    ('Attempts and looks', 'OFF three spent; ON zero; 33 observed looks unchanged'),
    ('Subscription changes', 'None; owner confirms 5 Years; no purchase or upgrade performed'),
    ('Canonical gates', 'Unchanged; no PIT, rights, registry or TR0-I admission'),
)


def _section():
    text = RECORD.read_text(encoding='utf-8')
    return text[text.index('## 96. Sharadar history diagnosis and offline preparation'):]


def _assert_scope(section):
    start = section.index('<!-- TPR-OFFLINE96-SCOPE:START -->')
    end = section.index('<!-- TPR-OFFLINE96-SCOPE:END -->', start)
    rows = tuple(tuple(p.strip() for p in line.strip('|').split('|'))
                 for line in section[start:end].splitlines() if line.startswith('| '))[1:]
    assert rows == EXPECTED, 'offline scope changed'
    for phrase in ('Not backtesting-ready', 'No fourth Codex OFF attempt',
                   'No QC access occurred', 'Account invoice and provider attestation were not read',
                   'TPR-CCR28-003 remains OPEN', 'Full History is not required for the frozen dates'):
        assert phrase in section, phrase
    assert re.search(r'\b(?:backtesting.ready|canonical acceptance)\s+(?:is|are)\s+(?:proved|granted)', section, re.I) is None


def test_offline_continuation_preserves_no_qc_and_attempt_boundaries():
    _assert_scope(_section())


@pytest.mark.parametrize('old,new', (
    ('Forbidden; zero API, UI, Mia, notebook, upload or launch effects', 'QC access is allowed'),
    ('OFF three spent; ON zero; 33 observed looks unchanged', 'OFF attempts reset; ON may launch'),
    ('Unchanged; no provider substitution or unit conversion', 'Replace native inputs with Sharadar'),
    ('None; owner confirms 5 Years; no purchase or upgrade performed', 'Upgrade was purchased'),
    ('TPR-CCR28-003 remains OPEN', 'TPR-CCR28-003 is closed'),
))
def test_offline_scope_guard_detects_clean_first_drift(old, new):
    section = _section(); _assert_scope(section)
    assert old in section
    with pytest.raises(AssertionError):
        _assert_scope(section.replace(old, new, 1))


OFFLINE98_SCOPE = (
    ('Review checkpoint', 'Skipped by owner for this round; no formal counter-review disposition'),
    ('External access', 'Zero QC, provider, credential or operator-state access'),
    ('Local capture census', 'Fresh scopes for one pinned repair index and eight exact projections only; no D0 or raw wire'),
    ('Implementation', 'Prospective exact-program controller and standalone builder; synthetic execution only'),
    ('Active native permission or adapter', 'None; no current native permit, dispatch, notebook or job'),
    ('Executed inputs and economics', 'Unchanged; no recapture, unit conversion or candidate reset'),
    ('Native baseline verified', 'False; OFF three attempts spent; ON zero; 33 looks retained'),
    ('Purchase and subscription changes', 'None'),
)


def _section98():
    text = RECORD.read_text(encoding='utf-8')
    start = text.index('## 98. Owner-waived offline controller and program preparation')
    end = text.find('\n## ', start + 4)
    return text[start:] if end == -1 else text[start:end]


def _assert98(text):
    start = text.index('<!-- TPR-OFFLINE98-SCOPE:START -->')
    end = text.index('<!-- TPR-OFFLINE98-SCOPE:END -->', start)
    rows = tuple(tuple(p.strip() for p in line.strip('|').split('|'))
        for line in text[start:end].splitlines() if line.startswith('| '))[1:]
    assert rows == OFFLINE98_SCOPE, 'offline98 scope changed'
    for required in ('No formal counter-review is claimed',
        'No QC access occurred', 'Native backtesting readiness remains unproved',
        'Current entitlement does not prove historical entitlement',
        'TICKERS is a current-vintage snapshot', 'No fourth Codex OFF attempt'):
        assert required in text, required


def test_offline98_preserves_waiver_no_access_and_unproved_native_readiness():
    _assert98(_section98())


@pytest.mark.parametrize('before,after', (
    (OFFLINE98_SCOPE[0][1], 'Independently accepted by Codex counter-review'),
    (OFFLINE98_SCOPE[1][1], 'QC access is allowed'),
    (OFFLINE98_SCOPE[2][1], 'All old captures may be reopened'),
    (OFFLINE98_SCOPE[4][1], 'Current native permit is active'),
    (OFFLINE98_SCOPE[6][1], 'True; attempts reset'),
    ('Current entitlement does not prove historical entitlement', 'Past entitlement is independently proved'),
))
def test_offline98_guards_reject_clean_first_authority_and_provenance_drift(before, after):
    text = _section98(); _assert98(text)
    assert before in text
    with pytest.raises(AssertionError):
        _assert98(text.replace(before, after, 1))


CENSUS98_FACTS = (
    ('Census source commit', '`35edf3cb0f158b3ea0a54b9149620235fc698b9d`'),
    ('Authenticated projection bytes', '8,381,144 across eight files; all hashes verified before fields'),
    ('TICKERS rows / distinct tickers / distinct permatickers', '21,007 / 21,007 / 21,007; current-vintage only'),
    ('ACTIONS rows / earliest / latest', '49,716 / 2025-10-13 / 2026-10-09'),
    ('ACTIONS years 2020 / 2021 / 2022 / 2023 / 2024 / 2025 / 2026', '0 / 0 / 0 / 0 / 0 / 12,803 / 36,913'),
    ('Warm-up / before 2021-10-11 / missing dates / invalid dates', '0 / 0 / 0 / 0'),
    ('Modified original inputs / provider requests / QC access / new looks', '0 / 0 / 0 / 0'),
    ('Native baseline / ON admission / historical entitlement / PIT completeness', 'Unproved / unproved / unproved / unproved'),
)


def _assert98_census(text):
    start = text.index('<!-- TPR-OFFLINE98-CENSUS:START -->')
    end = text.index('<!-- TPR-OFFLINE98-CENSUS:END -->', start)
    rows = tuple(tuple(p.strip() for p in line.strip('|').split('|'))
        for line in text[start:end].splitlines() if line.startswith('| '))[1:]
    assert rows == CENSUS98_FACTS, 'offline98 census facts changed'
    for phrase in ('No lower date bound was sent', 'an upgrade alone would not correct that query',
                   'No historical packet is overwritten', 'no additional provider purchase is justified'):
        assert phrase in text, phrase


def test_offline98_census_separates_retained_rows_from_entitlement_and_readiness():
    _assert98_census(_section98())


@pytest.mark.parametrize('before,after', (
    (CENSUS98_FACTS[1][1], 'All captures were read'),
    (CENSUS98_FACTS[3][1], '49,716 / 2020-09-01 / 2026-10-09'),
    (CENSUS98_FACTS[4][1], 'Complete history in every year'),
    (CENSUS98_FACTS[6][1], '0 / 0 / 1 / 1'),
    (CENSUS98_FACTS[7][1], 'Valid / admitted / proved / complete'),
    ('an upgrade alone would not correct that query', 'an upgrade repairs all inputs automatically'),
))
def test_offline98_census_guard_rejects_clean_first_coverage_and_acceptance_inflation(before, after):
    text = _section98(); _assert98_census(text)
    assert before in text
    with pytest.raises(AssertionError):
        _assert98_census(text.replace(before, after, 1))
