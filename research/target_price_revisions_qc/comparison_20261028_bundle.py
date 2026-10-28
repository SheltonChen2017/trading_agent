"""Pure pinned-public-source OFF bundle renderer, no read/upload/claim/job effect.

The caller supplies the exact twelve public source/metadata byte strings.
Pre-render template closure and final cloud source identities are separate:
embedding final source hashes in their own configuration would be circular.
Historical initialization is never selected; main exposes one subclass only.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re

PREFIX = "research/target_price_revisions_qc/"
STUDY = "TPR-SIX-UNIVERSE-FIVE-ARM-20261028-v1"
PROJECT = 37650980
MAX_SOURCE_BYTES = 131072
PINS = {
    "extended_core.py": "706ed5efdcb3999400c5349dc8b5200be1d48c4bb01cbfc7fb080608a679d5da",
    "cap_tilt.py": "262f568b7c0fe0b08af8a26896431465c17746bcd32e9addc568f58631e11a5c",
    "cap_observer.py": "cad8a3306f6b459bc8bf187c8fd8b8bb980c7b1dc0d85465fba11dd318b70c4d",
    "extended_construction.py": "4be72251040a0f133ee4a39245a3b0fe96285715a8510b4328b5d06c276596a6",
    "extended_loader.py": "24c752b0859a04d73306e3afddc10d45cc6d3c7b566e2ff17ef160fd90e6e10b",
    "extended_compressed_store.py": "d661b5752c35b9dd04f783f5d78850f453d5f5f299874e5cf19700599df2356e",
    "extended_runtime_successor.py": "2e6bb5c82f356ee7ece4811c9d634ce57d48533d408d4b57b8aee41de062517b",
    "extended_algorithm_successor.py": "e0077b7992dc64515384f56687b350725d694c746a8d4523336d18aa144dd9a8",
    "comparison_20261028.py": "cb507762dded3340acb7dd69b8086045ae819e0398eea1943444acb496e0e161",
    "comparison_20261028_algorithm.py": "c45a254b8999859796aec2c3fec904f292489838f32f87c0c76f11f7156cd3bc",
    "extended_calendar.json": "3eccdf3cf9a2542ffd249983241d5747c2ecd4e21bc4a71f7f826c77ec1fe53d",
    "comparison_20261028_policy.json": "df4c89601ba5a45a17c79d6386fff1ac202ef0689c4e592a8b1f9aba32ada80c"}
SOURCE_PATHS = tuple(PREFIX + name for name in PINS)
MAIN = b"import comparison_20261028_algorithm as candidate\n\nclass Main(candidate.ComparisonOffAlgorithm):\n    pass\n"


class BundleRefusal(ValueError):
    """Body-free source/config refusal; never a native authorization result."""


def _fail():
    raise BundleRefusal("pinned comparison OFF bundle refused") from None


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(body):
    try:
        return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                          allow_nan=False).encode("ascii")
    except (ValueError, TypeError, OverflowError, RecursionError):
        _fail()


def _hash(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None or set(value) == {"0"}:
        _fail()
    return value


def _span_replace(text, node, replacement):
    lines = text.splitlines(keepends=True)
    if node.end_lineno is None or node.end_col_offset is None:
        _fail()
    start = sum(len(row) for row in lines[:node.lineno-1]) + node.col_offset
    stop = sum(len(row) for row in lines[:node.end_lineno-1]) + node.end_col_offset
    # Source before these enumerated nodes is ASCII in the pinned templates.
    if not text[:stop].isascii():
        _fail()
    return text[:start] + replacement + text[stop:]


def _assignment(raw, name, placeholder, replacement, *, identifier=False):
    text = raw.decode("utf-8")
    matches = [node for node in ast.parse(text).body if isinstance(node, ast.Assign)
        and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name]
    if len(matches) != 1:
        _fail()
    value = matches[0].value
    if identifier:
        if not isinstance(value, ast.Name) or value.id != placeholder:
            _fail()
    elif not isinstance(value, ast.Constant) or type(value.value) is not str or value.value != placeholder:
        _fail()
    return _span_replace(text, value, replacement).encode("utf-8")


def _flat_import(raw, *, alias):
    text = raw.decode("utf-8")
    imports = [node for node in ast.walk(ast.parse(text)) if isinstance(node, ast.ImportFrom) and node.level]
    if len(imports) != 1:
        _fail()
    node = imports[0]
    if (node.level != 1 or node.module is not None or len(node.names) != 1
            or node.names[0].name != "cap_tilt" or node.names[0].asname != alias):
        _fail()
    return _span_replace(text, node, "import cap_tilt" + (" as " + alias if alias else "")).encode("utf-8")


def _calendar(raw, policy_sha256):
    try:
        source = json.loads(raw)
        if (source["study_id"] != "TPR-CAP-TILT-EXT26-20261010-v1" or source["decision_count"] != 301
                or source["valuation_count"] != 1449 or len(source["decisions"]) != 301
                or len(source["valuation_sessions"]) != 1449):
            _fail()
        return {"schema": "tpr-cmp28-calendar-candidate-v1", "study_id": STUDY,
            "policy_sha256": policy_sha256, "source_calendar_sha256": PINS["extended_calendar.json"],
            "timezone": "America/New_York", "start": "2021-01-04", "end": "2026-10-09",
            "warmup_start": "2020-09-01", "valuation_count": 1449, "decision_count": 301,
            "valuation_sessions": source["valuation_sessions"], "warmup_sessions": source["warmup_sessions"],
            "decisions": source["decisions"], "no_market_outcomes": True}
    except (KeyError, ValueError, TypeError, UnicodeError, RecursionError):
        _fail()


def build_off_candidate(*, public_sources, operation_id, attempt, prior_attempts_looks_sha256):
    """Return(flat filename->bytes, canonical report bytes), without any I/O.

    Template source closure is hash-bound in the config. Final rendered source
    hashes are returned separately and must be retained BEFORE native effects.
    Numeric attempt is provenance only: no reservation, look or claim is minted.
    """
    if (type(public_sources) is not dict or set(public_sources) != set(SOURCE_PATHS)
            or type(attempt) is not int or not 1 <= attempt <= 2**31-1
            or type(operation_id) is not str or not 0 < len(operation_id) <= 160
            or re.fullmatch(r"TPR-CMP28-OFF-[A-Za-z0-9][A-Za-z0-9_.-]*", operation_id) is None):
        _fail()
    prior = _hash(prior_attempts_looks_sha256)
    sources = {}
    for name, expected in PINS.items():
        raw = public_sources[PREFIX + name]
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_SOURCE_BYTES or _sha(raw) != expected:
            _fail()
        sources[name] = raw
    template_hashes = {PREFIX + name: _sha(raw) for name, raw in sources.items()}
    template_closure = _sha(_canonical({"schema": "tpr-cmp28-public-template-closure-v1", "source_hashes": template_hashes}))
    policy_hash = _sha(sources["comparison_20261028_policy.json"])
    calendar = _calendar(sources["extended_calendar.json"], policy_hash)
    calendar_hash = _sha(_canonical(calendar))
    config = {"schema": "tpr-cmp28-off-native-config-v1", "study_id": STUDY,
        "candidate_id": STUDY + "-OFF", "arm": "cap_off", "operation_id": operation_id,
        "attempt": attempt, "project_id": PROJECT, "policy_sha256": policy_hash,
        "calendar_sha256": calendar_hash, "source_template_closure_sha256": template_closure,
        "prior_attempts_looks_sha256": prior, "source_inputs_admitted": False, "canonical_admission": False}
    config_raw = _canonical(config)
    config_hash = _sha(config_raw)
    files = {name: raw for name, raw in sources.items() if name.endswith(".py")}
    files["extended_construction.py"] = _flat_import(files["extended_construction.py"], alias=None)
    files["comparison_20261028.py"] = _flat_import(files["comparison_20261028.py"], alias="legacy")
    files["extended_loader.py"] = _assignment(files["extended_loader.py"], "CALENDAR_JSON",
        "__CALENDAR_JSON_LITERAL__", repr(sources["extended_calendar.json"].decode("utf-8")), identifier=True)
    files["extended_algorithm_successor.py"] = _assignment(files["extended_algorithm_successor.py"],
        "EXPECTED_CONFIG_SHA256", "__EXTENDED_CONFIG_SHA256__", repr(_sha(b"IMPORT_ONLY_PREDECESSOR_INITIALIZE_NOT_SELECTED")))
    files["extended_algorithm_successor.py"] = _assignment(files["extended_algorithm_successor.py"],
        "EXPECTED_ATTEMPT", "__ATTEMPT_NUMBER__", repr(attempt), identifier=True)
    files["comparison_20261028_algorithm.py"] = _assignment(files["comparison_20261028_algorithm.py"],
        "EXPECTED_CONFIG_SHA256", "__CMP28_CONFIG_SHA256__", repr(config_hash))
    files["comparison_20261028_config.py"] = ("CONFIG_JSON = " + repr(config_raw.decode("ascii")) + "\n").encode("ascii")
    files["main.py"] = MAIN
    for name, raw in files.items():
        if not 0 < len(raw) <= 60000:
            _fail()
        try:
            tree = ast.parse(raw, filename=name)
            if any(isinstance(node, ast.ImportFrom) and node.level for node in ast.walk(tree)):
                _fail()
            compile(tree, name, "exec")
        except (SyntaxError, ValueError, TypeError, UnicodeError):
            _fail()
    final_hashes = {name: _sha(raw) for name, raw in sorted(files.items())}
    report = {"schema": "tpr-cmp28-off-bundle-candidate-v1", "study_id": STUDY,
        "candidate_id": config["candidate_id"], "arm": "cap_off", "project_id": PROJECT,
        "operation_id": operation_id, "attempt": attempt, "config_sha256": config_hash,
        "policy_sha256": policy_hash, "calendar_sha256": calendar_hash,
        "source_template_closure_sha256": template_closure, "template_source_hashes": template_hashes,
        "cloud_source_hashes": final_hashes, "cloud_source_bytes": {name: len(raw) for name, raw in sorted(files.items())},
        "rendered_source_closure_sha256": _sha(_canonical(final_hashes)), "file_count": len(files),
        "ast_changes": ["extended_construction.cap_tilt_import", "comparison_20261028.cap_tilt_import",
            "extended_loader.calendar_literal", "predecessor.import_only_config_literal",
            "predecessor.import_only_attempt_literal", "comparison_algorithm.config_literal"],
        "predecessor_initialize_selected": False, "main_class": "Main(candidate.ComparisonOffAlgorithm)",
        "source_inputs_admitted": False, "native_permission": False, "qc_setup_complete": False,
        "reservation_sha256": None, "new_attempts": 0, "new_observed_looks": 0,
        "strategy_accepted": False, "canonical_admission": False, "accepted_performance": None}
    return files, _canonical(report) + b"\n"
