"""Spent-caller pin closures see only the two approved EOF-merge replacements.

Section 330 (ARV2R328-007): historical pins stay unchanged. The helper maps an
entry only when both its path and its historical pin equal a REPLACEMENTS row
of Codex's post-merge manifest; nothing is refreshed from the current tree.
"""
import hashlib
from pathlib import Path

from scripts import arv2_r298_post_merge_source_pins as manifest
from tests.analyst_revisions_v2._post_merge_pins import current_pin

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
BOUNDARY = 'scripts/arv2_r298_plain_source_boundary.py'
READINESS = 'scripts/run_arv2_r298_plain_readiness.py'


def test_exactly_the_two_approved_replacements_map_to_their_post_merge_pins():
    assert [path for path, _, _ in manifest.REPLACEMENTS] == [BOUNDARY, READINESS]
    for path, old, new in manifest.REPLACEMENTS:
        assert current_pin(path, old) == new != old
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == new


def test_unlisted_paths_and_non_historical_pins_are_never_remapped():
    old_boundary = manifest.REPLACEMENTS[0][1]
    assert current_pin(READINESS, old_boundary) == old_boundary
    assert current_pin('scripts/arv2_r298_other.py', old_boundary) == old_boundary
    for path, _, new in manifest.REPLACEMENTS:
        assert current_pin(path, new) == new
        assert current_pin(path, 'f' * 64) == 'f' * 64
