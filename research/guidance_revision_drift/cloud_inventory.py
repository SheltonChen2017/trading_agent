"""Passive complete new-project byte custody; opaque extras stay quarantined.

The caller separately verifies the exact current local carrier and obtains
the entire returned project within its authorized scope. This module neither
fetches files nor executes/renders/notebook-parses anything. A matching Python
map is not economic acceptance, authenticated provenance or QC permission.
"""
from __future__ import annotations

import difflib
import re

from data.hashing import hash_bytes, hash_payload


MAX_FILES, MAX_FILE_BYTES, MAX_TOTAL_BYTES = 64, 1_048_576, 4_194_304
MAX_EXPECTED_PYTHON_BYTES = 32_000
MAX_TEXT_DIFF_BYTES = 64_000
MAX_DIFF_LINES, MAX_DIFF_CHARS, MAX_ALL_DIFF_CHARS = 2048, 32_768, 131_072
_PATH = re.compile(r"[A-Za-z0-9_./-]{1,256}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")


class CloudInventoryError(ValueError):
    """Unsafe, incomplete, mutated, oversized or unanchored project custody."""


def _digest(value):
    if type(value) is not str or not _HASH.fullmatch(value):
        raise CloudInventoryError("exact caller-retained lowercase SHA-256 required")
    return value


def _snapshot(files):
    if type(files) is not dict or len(files) > MAX_FILES:
        raise CloudInventoryError("bounded complete immutable file map required")
    try:
        result = dict(files)
    except RuntimeError as exc:
        raise CloudInventoryError("file map changed during snapshot") from exc
    folded, size = set(), 0
    for name, raw in result.items():
        if (type(name) is not str or not _PATH.fullmatch(name) or name.startswith("/")
                or any(part in ("", ".", "..") for part in name.split("/"))
                or name.casefold() in folded or type(raw) is not bytes or len(raw) > MAX_FILE_BYTES):
            raise CloudInventoryError("safe unique bounded immutable project file bytes required")
        folded.add(name.casefold())
        size += len(raw)
    if len(result) > MAX_FILES or size > MAX_TOTAL_BYTES:
        raise CloudInventoryError("complete project inventory exceeds bound")
    return result


def _inventory(files):
    return {name: {"bytes": len(raw), "sha256": hash_bytes(raw),
        "classification": ("python_source" if name.lower().endswith(".py") else
                           "quarantined_notebook" if name.lower().endswith(".ipynb") else "quarantined_opaque")}
        for name, raw in sorted(files.items())}


def cloud_file_inventory(files):
    return _inventory(_snapshot(files))


def cloud_inventory_anchor(files):
    """Bind all returned names/bytes/classes, not a silently filtered Python map."""
    return hash_payload(cloud_file_inventory(files))


def compare_cloud_inventory(expected_python, returned_files, *, expected_project_sha256,
                            expected_returned_sha256):
    expected, returned = _snapshot(expected_python), _snapshot(returned_files)
    if (not expected or "main.py" not in expected or not expected["main.py"] or len(expected) > 25
            or any(not name.endswith(".py") or len(raw) >= MAX_EXPECTED_PYTHON_BYTES
                   for name, raw in expected.items())):
        raise CloudInventoryError("complete retained bounded Python carrier required")
    before, after = _inventory(expected), _inventory(returned)
    # Compatibility with the retained carrier's existing name->{bytes,sha} anchor.
    expected_identity = {name: {key: row[key] for key in ("bytes", "sha256")} for name, row in before.items()}
    if (hash_payload(expected_identity) != _digest(expected_project_sha256)
            or hash_payload(after) != _digest(expected_returned_sha256)):
        raise CloudInventoryError("complete project differs from retained local/returned anchor")
    changes, opaque, diff_budget = [], [], MAX_ALL_DIFF_CHARS
    for name in sorted(set(before) | set(after)):
        status = "extra" if name not in expected else "missing" if name not in returned else "unchanged" if expected[name] == returned[name] else "changed"
        row = {"name": name, "status": status, "expected": before.get(name), "returned": after.get(name)}
        if name in after and after[name]["classification"] != "python_source":
            opaque.append(name)
            row["diff_status"] = "opaque_bytes_retained_not_decoded_or_executed"
        elif status != "unchanged":
            if len(expected.get(name, b"")) + len(returned.get(name, b"")) > MAX_TEXT_DIFF_BYTES:
                row["diff_status"] = "oversized_python_quarantined_raw_review_required"
                changes.append(row)
                continue
            try:
                old = expected.get(name, b"").decode("utf-8").splitlines(keepends=True)
                new = returned.get(name, b"").decode("utf-8").splitlines(keepends=True)
            except UnicodeError:
                row["diff_status"] = "invalid_utf8_python_quarantined_raw_review_required"
            else:
                if len(old) + len(new) > MAX_DIFF_LINES:
                    row["diff_status"] = "too_many_python_lines_quarantined_raw_review_required"
                else:
                    parts, used, complete = [], 0, True
                    allowance = min(MAX_DIFF_CHARS, diff_budget)
                    for part in difflib.unified_diff(old, new, fromfile="retained/" + name,
                                                    tofile="returned/" + name):
                        if len(part) > allowance - used:
                            parts.append(part[:allowance - used])
                            used, complete = allowance, False
                            break
                        parts.append(part)
                        used += len(part)
                    diff_budget -= used
                    row["diff_status"] = "text_diff_observation_only" if complete else "bounded_diff_prefix_quarantined_raw_review_required"
                    row["diff_complete"] = complete
                    row["unified_diff"] = "".join(parts)
        changes.append(row)
    python_changes = [row["name"] for row in changes if row["status"] != "unchanged" and (
        row["name"] in before or (row["name"] in after and after[row["name"]]["classification"] == "python_source"))]
    quarantined = bool(python_changes or opaque)
    return {"schema": "gdr.synthetic.complete-cloud-inventory.v1",
        "status": "quarantined_pending_manual_review" if quarantined else "byte_identical_observation_only",
        "expected_project_sha256": expected_project_sha256, "returned_inventory_sha256": expected_returned_sha256,
        "expected_files": before, "returned_files": after, "changes": changes,
        "change_manifest_sha256": hash_payload(changes), "python_changes": python_changes,
        "opaque_quarantine": opaque, "python_byte_identical": not python_changes, "quarantined": quarantined,
        "current_local_content_checked": False, "external_provenance_verified": False,
        "automatic_port_allowed": False, "economic_acceptance": False, "qc_launch_allowed": False,
        "market_evidence": False}
