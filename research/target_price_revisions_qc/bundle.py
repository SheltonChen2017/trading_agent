"""Pure readable source packaging for the six frozen private QC projects.

No filesystem/network, cloud launch, encoded source, or data-module generation.
The returned Object Store key names only the separately uploaded plaintext JSON.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re

from . import packet

MAX_SOURCE_BYTES = 30_000
PLACEHOLDERS = ("__CONFIG_SHA256__", "__PACKET_SHA256__", "__PACKET_KEY__")


class BundleError(ValueError):
    """Fixed refusal that never echoes private JSON."""


def _digest(payload):
    return hashlib.sha256(payload).hexdigest()


def _pairs(rows):
    result = {}
    for key, value in rows:
        if key in result:
            raise BundleError("duplicate JSON key")
        result[key] = value
    return result


def _load(payload, bound):
    if type(payload) is not bytes or not 0 < len(payload) <= bound:
        raise BundleError("bounded immutable bytes required")
    try:
        return json.loads(payload.decode("utf-8"), object_pairs_hook=_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(BundleError("nonfinite JSON")))
    except (UnicodeError, ValueError, RecursionError):
        raise BundleError("invalid JSON bytes") from None


def _source(text):
    if type(text) is not str or not 0 < len(text.encode("utf-8")) <= MAX_SOURCE_BYTES:
        raise BundleError("source exceeds fixed per-file bound")
    try:
        tree = ast.parse(text, filename="tpr-qc-six-source.py")
        compile(tree, "tpr-qc-six-source.py", "exec")
    except (SyntaxError, ValueError, TypeError):
        raise BundleError("source does not compile") from None
    return tree


def build_upload_bundle(template_payload, *, packet_payload, packet_sha256, freeze_payload):
    """Return all six source/config pairs and exact hashes, without side effects."""
    if type(freeze_payload) is not bytes or _digest(freeze_payload) != packet.FREEZE_SHA256:
        raise BundleError("freeze identity mismatch")
    freeze = _load(freeze_payload, 65_536)
    if (type(packet_sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", packet_sha256) is None
            or type(packet_payload) is not bytes or _digest(packet_payload) != packet_sha256):
        raise BundleError("packet identity mismatch")
    signals = _load(packet_payload, packet.MAX_PACKET_BYTES)
    packet.validate_packet(signals)
    if packet.canonical_json(signals) != packet_payload:
        raise BundleError("packet must use the reviewed canonical JSON encoding")
    if signals["source_hashes"]["structure.json"] != freeze["signal"]["source_structure_sha256"]:
        raise BundleError("packet source is not the frozen source")
    if type(template_payload) is not bytes:
        raise BundleError("immutable template bytes required")
    try:
        template = template_payload.decode("utf-8")
    except UnicodeError:
        raise BundleError("template must be readable UTF-8") from None
    tree = _source(template)
    assignments = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in {"EXPECTED_FREEZE_SHA256", "CASES", "DECISIONS", "CUTOFFS"}:
                if name in assignments:
                    raise BundleError("duplicate template policy assignment")
                try:
                    assignments[name] = ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    raise BundleError("literal template policy required") from None
    expected_cases = {row["case"]: (row["id"], row["membership_etf"]) for row in freeze["universes"]}
    if (len(expected_cases) != 6 or assignments.get("EXPECTED_FREEZE_SHA256") != packet.FREEZE_SHA256
            or assignments.get("CASES") != expected_cases
            or assignments.get("DECISIONS") != packet.SESSIONS
            or assignments.get("CUTOFFS") != packet.CUTOFFS):
        raise BundleError("template and six-case freeze diverge")
    for marker in PLACEHOLDERS:
        if template.count(marker) != 1:
            raise BundleError("absent or duplicate source placeholder")
    key = f"tpr-qc6/{packet.FAMILY_ID}/{packet_sha256}.json"
    cases = []
    for case in freeze["universes"]:
        config = {"schema": "tpr-qc-six-config-v1", "freeze_sha256": packet.FREEZE_SHA256,
                  "candidate_id": case["id"], "universe_id": case["case"]}
        config_text = packet.canonical_json(config).decode("ascii")
        config_sha = _digest(config_text.encode("ascii"))
        replacements = dict(zip(PLACEHOLDERS, (config_sha, packet_sha256, key)))
        main = template
        for marker, value in replacements.items():
            main = main.replace(marker, value)
        if re.search(r"__[A-Z][A-Z0-9_]*__", main):
            raise BundleError("unreplaced source placeholder")
        config_module = "# Frozen per-case configuration; no market rows.\nCONFIG_JSON = " + repr(config_text) + "\n"
        files = {"main.py": main, "signal_packet.py": config_module}
        for text in files.values():
            _source(text)
        cases.append({"candidate_id": case["id"], "universe_id": case["case"],
            "config_sha256": config_sha, "files": files,
            "source_hashes": {name: _digest(text.encode("utf-8")) for name, text in files.items()}})
    return {"schema": "tpr-qc-six-upload-bundle-v1", "family_id": packet.FAMILY_ID,
        "freeze_sha256": packet.FREEZE_SHA256, "template_sha256": _digest(template_payload),
        "packet_sha256": packet_sha256, "packet_key": key, "cases": cases}
