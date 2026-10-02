"""Exact policy bytes must survive a Windows-style Git checkout."""

import hashlib
from pathlib import Path
import subprocess

import pytest

from research.analyst_revisions_v2_qc import (
    six_universe_forward_construction_policy as construction,
    six_universe_forward_stock_selection_policy as selection,
    six_universe_qcom_exclusion_ar_range_policy as ar_range,
    six_universe_qcom_exclusion_dual_forward_policy as dual,
)


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "research/analyst_revisions_v2_qc/"


@pytest.mark.parametrize("module", (ar_range, dual, construction, selection))
def test_frozen_parent_bytes_survive_windows_checkout_conversion(module):
    """Use Git's real checkout filter, without changing files or config."""
    path = module.POLICY_PATH.relative_to(ROOT).as_posix()
    raw = subprocess.run(
        ["git", "-c", "core.autocrlf=true", "-c", "core.eol=crlf",
         "cat-file", "--filters", "HEAD:" + path],
        cwd=ROOT, check=True, capture_output=True,
    ).stdout
    assert b"\r" not in raw
    assert hashlib.sha256(raw).hexdigest() == module.FROZEN_POLICY_SHA256


def test_new_execution_child_inherits_exact_byte_checkout_rule():
    """Protect new policy files before they are committed, too."""
    path = PACKAGE + "six_universe_forward_execution.json"
    output = subprocess.run(
        ["git", "check-attr", "text", "--", path],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout.strip()
    assert output == path + ": text: unset"


def test_every_tracked_lane_json_is_exempt_from_newline_conversion():
    """The attribute protects every hash-pinned lane manifest, not only the
    five forward policies above; nearly all of them contain a newline, so a
    narrowed pattern would break their pins on a Windows-style checkout."""
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--", PACKAGE + "*.json"],
        cwd=ROOT, check=True, capture_output=True,
    ).stdout.decode("utf-8").split("\0")
    paths = sorted(path for path in listed if path)
    assert PACKAGE + "six_universe_forward_execution.json" in paths
    assert len(paths) > 5
    fields = subprocess.run(
        ["git", "check-attr", "-z", "text", "--", *paths],
        cwd=ROOT, check=True, capture_output=True,
    ).stdout.decode("utf-8").split("\0")
    rows = [fields[index:index + 3] for index in range(0, len(fields) - 1, 3)]
    assert sorted(row[0] for row in rows) == paths
    assert {row[0]: row[2] for row in rows} == {path: "unset" for path in paths}
