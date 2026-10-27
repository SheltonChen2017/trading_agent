"""Current offline handoff only; no private/QC/automation inspection."""
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / 'docs/Strategy Description/TARGET_PRICE_REVISION_IMPLEMENTATION_RECORD.md'
START = '## 103. Offline OFF recovery preparation before QC setup - 2026-10-26'
SCOPE = (
    ('Owner boundary', 'Offline build only; stop before QC/Safari setup or access'),
    ('Claude checkpoint', 'Skipped by the latest explicit owner direction'),
    ('Monitors', 'Analyst-push monitor deleted at owner request; no polling, rearm or consumed release'),
    ('Inputs', 'Public repository bytes and synthetic fixtures only'),
    ('Native admission', 'No active permit, genuine adapter, notebook, claim or QC job'),
    ('History', 'OFF three historical Codex failures; ON zero; 33 observed looks retained'),
    ('New effects', 'Zero private/provider/credential/operator reads; zero attempts, jobs and looks'),
    ('Publication', 'Exactly one non-force push to the matching Target-Price lane'),
)


def _section(text):
    assert text.count(START) == 1
    result = text.split(START, 1)[1]
    assert '\n## 104.' not in result
    return result


def _check(section):
    begin, end = '<!-- TPR-OFFLINE103-SCOPE:START -->', '<!-- TPR-OFFLINE103-SCOPE:END -->'
    assert section.count(begin) == section.count(end) == 1
    block = section.split(begin)[1].split(end)[0]
    rows = tuple(tuple(part.strip() for part in line.strip('|').split('|'))
        for line in block.splitlines() if line.startswith('| '))[1:]
    assert rows == SCOPE
    for required in (
        '990e53672533cf27e466235bfe4184cec0bd32bb',
        'extended_off_recovery_preparation.py', 'extended_off_recovery_cli.py',
        'extended_off_attempt_continuation.py',
        'Old effect controllers remain unchanged and still refuse attempt four',
        'A draft reservation is not a durable claim or native permission',
        'A validated witness is not a sufficient source-unit diagnosis',
        'No accepted OFF full-window result or paired performance is claimed',
        'Fresh source/tool metadata and custody must be verified at actual QC setup',
        '1449 valuations/301 decisions',
    ):
        assert required in section, required
    for unsupported in ('QC setup is complete.', 'OFF backtesting is accepted.',
                        'All prior attempts and looks are reset.', 'The monitor has been rearmed.'):
        assert unsupported not in section


def test_offline103_handoff_pins_actual_boundary_and_retained_history():
    _check(_section(RECORD.read_text(encoding='utf-8')))


@pytest.mark.parametrize('before,after', [
    (SCOPE[0][1], 'QC setup is complete.'),
    (SCOPE[1][1], 'Another Claude review is mandatory'),
    (SCOPE[2][1], 'The monitor has been rearmed.'),
    (SCOPE[5][1], 'All prior attempts and looks are reset.'),
    ('A draft reservation is not a durable claim or native permission', 'A draft grants native permission'),
    ('A validated witness is not a sufficient source-unit diagnosis', 'A validated witness proves the unit fix'),
    ('No accepted OFF full-window result or paired performance is claimed', 'OFF backtesting is accepted.'),
])
def test_offline103_clean_first_negative_controls(before, after):
    section = _section(RECORD.read_text(encoding='utf-8'))
    _check(section)
    assert before in section
    with pytest.raises(AssertionError):
        _check(section.replace(before, after, 1))
