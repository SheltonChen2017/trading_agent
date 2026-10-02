"""The reviewed strategy blueprint digest must be one value, and the real PDF must hash to it."""
from __future__ import annotations

import hashlib
from pathlib import Path

from research.analyst_revisions_v2 import (
    fold_manifest,
    four_family_multiplicity,
    global_benchmark_contract,
    post_pandemic_evaluation_plan,
    power_calibration_input_schema,
    stock_evaluation_contract,
)

BLUEPRINT = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "Strategy Description"
    / "ANALYST_REVISIONS_ETF_STRATEGY_BLUEPRINT_V2_EN.pdf"
)
PINNING_MODULES = (
    fold_manifest,
    four_family_multiplicity,
    global_benchmark_contract,
    post_pandemic_evaluation_plan,
    power_calibration_input_schema,
    stock_evaluation_contract,
)


def test_every_lane_module_pins_the_same_blueprint_digest_and_the_pdf_matches():
    digests = {module.__name__: module.STRATEGY_PDF_SHA256 for module in PINNING_MODULES}
    assert len(set(digests.values())) == 1, digests
    assert hashlib.sha256(BLUEPRINT.read_bytes()).hexdigest() == next(iter(digests.values()))
