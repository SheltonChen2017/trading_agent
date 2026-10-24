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
