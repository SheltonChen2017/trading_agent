from __future__ import annotations

from pathlib import Path

import pytest

from research.analyst_revisions_v2_qc import formal_streaming_bridge
from research.analyst_revisions_v2_qc import formal_streaming_input
from research.analyst_revisions_v2_qc import physical_production_evidence_bridge
from research.analyst_revisions_v2_qc import physical_streaming_scoring
from research.analyst_revisions_v2_qc import production_evidence_composer


@pytest.mark.parametrize(
    "module",
    (
        formal_streaming_bridge,
        formal_streaming_input,
        physical_production_evidence_bridge,
        physical_streaming_scoring,
        production_evidence_composer,
    ),
)
def test_qc_and_physical_spools_do_not_require_the_macos_private_tmp(module):
    source = Path(module.__file__).read_text(encoding="utf-8")
    assert 'dir="/private/tmp"' not in source
    assert "dir='/private/tmp'" not in source
