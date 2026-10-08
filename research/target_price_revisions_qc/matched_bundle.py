"""Pure readable-source packaging for the prospectively frozen matched study.

No file, credential, provider, outcome or cloud access occurs in this module.
The original packet remains an input artifact, not a newly tuned signal.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re

from . import packet

STUDY = "TPR-MATCHED-20261008-v1"
FREEZE_SHA256 = "a0645dce96d1153de4a6709b4d39c1d8cc0c583950a76421220e00539a9521d0"
CORE_SHA256 = "00f4f3a55ddca276a954e78bb550eaeaafc4b1b95051b3a7f64554edbae464e3"
PACKET_SHA256 = "4dd3a9d800b7c1cb8114272c829ee18239972cc0a15c71e47a3e86ed6491a316"
MAX_FILE_BYTES = 60000
CANDIDATES = (
    ("TPR-MATCHED-ON-BASE-v1", "tpr_on", "baseline", "0.001"),
    ("TPR-MATCHED-OFF-BASE-v1", "tpr_off", "baseline", "0.001"),
    ("TPR-MATCHED-ETF-BASE-v1", "etf_basket", "baseline", "0.001"),
    ("TPR-MATCHED-ON-ADVERSE-v1", "tpr_on", "adverse", "0.0015"),
    ("TPR-MATCHED-OFF-ADVERSE-v1", "tpr_off", "adverse", "0.0015"),
    ("TPR-MATCHED-ETF-ADVERSE-v1", "etf_basket", "adverse", "0.0015"),
)


class Refusal(ValueError):
    """Fixed messages; private bytes never echoed."""


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return packet.canonical_json(value)


def _source(text):
    if type(text) is not str or not 0 < len(text.encode()) <= MAX_FILE_BYTES:
        raise Refusal("readable source size refused")
    try:
        compile(ast.parse(text), "matched-source.py", "exec")
    except (SyntaxError, ValueError, TypeError):
        raise Refusal("source compilation refused") from None


def _replace_once(text, marker, value):
    if text.count(marker) != 1:
        raise Refusal("exact source placeholder required")
    return text.replace(marker, value)


def validate_packet_bytes(raw):
    if type(raw) is not bytes or digest(raw) != PACKET_SHA256:
        raise Refusal("original frozen packet identity refused")
    body = packet._load(raw, packet.MAX_PACKET_BYTES)
    packet.validate_packet(body)
    if canonical(body) != raw:
        raise Refusal("canonical packet encoding refused")


def build_bundle(template, core, freeze_payload, *, max_file_size):
    """Render without private input reads; input verified separately before upload.

    Quota must be obtained from the fresh project. Rendering at the fixed60000
    cap is safe before project creation, but upload refuses a lower actual quota.
    """
    if type(max_file_size) is not int or max_file_size < MAX_FILE_BYTES:
        raise Refusal("verified project quota at least60000 required")
    if type(freeze_payload) is not bytes or digest(freeze_payload) != FREEZE_SHA256:
        raise Refusal("matched freeze identity refused")
    freeze = packet._load(freeze_payload, 65536)
    actual = tuple((row["candidate_id"], row["arm"], row["cost"], row["slippage"])
                   for row in freeze["candidates"])
    if freeze["study_id"] != STUDY or actual != CANDIDATES:
        raise Refusal("six candidate policies diverge")
    if type(core) is not bytes or digest(core) != CORE_SHA256:
        raise Refusal("immutable executed core identity refused")
    if type(template) is not bytes:
        raise Refusal("template bytes required")
    try:
        main_template, core_template = template.decode(), core.decode()
    except UnicodeError:
        raise Refusal("readable UTF8 sources required") from None
    _source(main_template)
    _source(core_template)
    key = f"tpr-matched/{STUDY}/{PACKET_SHA256}.json"
    proxy_config = {"schema": "tpr-qc-six-config-v1", "freeze_sha256": packet.FREEZE_SHA256,
                    "candidate_id": "TPR-QC6-SPY-v1", "universe_id": "sp500"}
    proxy_text = canonical(proxy_config).decode()
    proxy_hash = digest(proxy_text.encode())
    proxy_core = core_template
    for marker, value in (("__CONFIG_SHA256__", proxy_hash),
                          ("__PACKET_SHA256__", PACKET_SHA256),
                          ("__PACKET_KEY__", key)):
        proxy_core = _replace_once(proxy_core, marker, value)
    proxy_module = "# Original packet validation configuration, not portfolio identity.\nCONFIG_JSON = " + repr(proxy_text) + "\n"
    cases = []
    for candidate_id, arm, cost, slippage in CANDIDATES:
        config = {"schema": "tpr-qc-matched-config-v1", "study_id": STUDY,
                  "freeze_sha256": FREEZE_SHA256, "candidate_id": candidate_id,
                  "arm": arm, "cost": cost, "slippage": slippage}
        config_text = canonical(config).decode()
        config_hash = digest(config_text.encode())
        main = _replace_once(main_template, "__MATCHED_FREEZE_SHA256__", FREEZE_SHA256)
        main = _replace_once(main, "__MATCHED_CONFIG_SHA256__", config_hash)
        files = {"main.py": main, "proxy_core.py": proxy_core,
                 "signal_packet.py": proxy_module,
                 "matched_config.py": "# Frozen matched candidate.\nCONFIG_JSON = " + repr(config_text) + "\n"}
        for value in files.values():
            _source(value)
            if re.search(r"__[A-Z][A-Z0-9_]*__", value):
                raise Refusal("unreplaced source marker")
        cases.append({"candidate_id": candidate_id, "arm": arm, "cost": cost,
                      "config_sha256": config_hash, "files": files,
                      "source_hashes": {name: digest(text.encode()) for name, text in files.items()}})
    return {"schema": "tpr-qc-matched-bundle-v1", "study_id": STUDY,
            "freeze_sha256": FREEZE_SHA256, "template_sha256": digest(template),
            "original_core_sha256": CORE_SHA256, "packet_sha256": PACKET_SHA256,
            "packet_key": key, "cases": cases}
