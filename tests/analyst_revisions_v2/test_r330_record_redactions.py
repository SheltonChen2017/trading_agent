"""Reversible fingerprints and the owner's display name stay out of the record.

Section 330 (ARV2R328-006 and -009). Five plain SHA-256 values of low-entropy
items (two raw price dates; a held security's SID, display ticker and SID date)
were withheld from sections 323.41 and 323.60. Only SHA-256 digests of those
64-hex strings appear here, which cannot be reversed. Git history is unchanged.
"""
import hashlib
import re
from pathlib import Path

RECORD = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2/docs/Strategy Description/'
    'ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md')
WITHHELD = frozenset((
    '0ef829a9dc2e9f01507feb24bd55418abb2ea77f525be468d565d55ee049514a',
    '2957aa5234fa445427b6d049c7b2efff31e4453dca139cba1d0d9ba969abe203',
    '84c7f6dc6753bc9eaebb219c9c078573079ca40dae14d540325275aa3b1978cb',
    'fccb482e0720b2090424061e144c0715316fb32709eb56c213e2a07927e2251c',
    '466e74aafd8ce606ef5eb90711cbccd403a8507e62656581f51226aefdfa1230',
))


def test_withheld_low_entropy_fingerprints_do_not_reappear():
    text = RECORD.read_text(encoding='utf-8')
    tokens = set(re.findall(r'(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])', text))
    assert not {hashlib.sha256(token.encode('ascii')).hexdigest() for token in tokens} & WITHHELD
    assert text.count('withheld in section330') == 3


def test_section_323_25_names_the_owner_by_role_only():
    text = RECORD.read_text(encoding='utf-8')
    start = text.index('### 323.25 ')
    section = text[start:text.index('### 323.26 ', start)]
    assert "the owner's account(Owner; display name withheld in section330)" in section
