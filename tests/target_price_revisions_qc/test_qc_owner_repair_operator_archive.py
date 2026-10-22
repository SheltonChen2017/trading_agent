"""Static custody checks for nineteen spent public operator recipes.

The archive is retrospective, not an executor or a complete UI replay. These
tests parse Python ASTs only: they never import, compile or execute archived
source, retrieve private artifacts, use credentials, or operate QC/native UI.
They verify the retained text/labels, not historical execution completeness,
native accounting, or closure of the broader historical review finding.
"""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "research/target_price_revisions_qc/owner_repair_operation_scripts_20261021.json"
PROMPT_SHA256 = "270611202ba1a7287a3e7d71180676a918e8018c77945f7a464093d742890e1b"
OWNER_SHA256 = "4cbdbec4c54b5db78455516442f96c25d636af6e54a214209cef5419e301b9aa"
TOP_KEYS = {
    "canonical_admission", "effect_authority", "entries", "known_setup_limitations",
    "lane_branch", "mia_source_only_prompt", "mia_source_only_prompt_sha256",
    "owner_instruction_sha256", "replay_authority", "retrospective", "schema", "scope",
    "selected_cua_effect_statements", "study_id", "warning",
}
IDENTITIES = {
    "tprFreshDiscoveryScript": (1281, "8f290b6442f75da320adeb434660143caa32221dc5bb6baa1105786ef9926927"),
    "tprNewSourceScript": (1246, "509d8168d70c8f2599d3640edd9e112b70fdbf36218aa1c2111654df646f5cb6"),
    "tprSourceInspect001Script": (7667, "1f544f23cbd30cf06aef74cd5770b5062a2c2fddc57be79cd8b9e35528eab6ee"),
    "tprSourceInspect002Script": (4869, "c09df92575a1b10c5c16562dbe73cba462add32f5b9a37bb3c6ee752b511fb62"),
    "tprSourceInspect003Script": (5642, "177fb9009e65c5a523c9ea8ff89347a3504cab92f976174fc42234a26b546ecb"),
    "tprMiaVerify001Script": (1842, "cb8c903e3b095dc7bc9cf6cb595c0221c77af478e026648932ad89154a0107b3"),
    "tprRepairTerminal001Script": (1444, "aae5c704a438b9132707b5c8be55d2c4277802450ba389578b02efcb45418caa"),
    "tprMiaHistoryVerify001Script": (1956, "888f2e4732a14c31ebea5562a9bdf250d942bcc2dd14ab6a779bdf5bb0656202"),
    "tprMiaHistoryVerify002Script": (1956, "1552eaaae2dcf38d548610211ea96c97f34b61c51c8cbb2e77e8b0e2e2a69760"),
    "tprMiaControlVerify001Script": (2025, "ed18a4b3dee9260d8801e1f39a6df18ebf30dad398154953bfed5b4740fd0bbd"),
    "tprPreMiaSource002Script": (1246, "0b0718aa0fd0162293270ba00d9a5c36563f9c6ab68e1ce8ae012703037af393"),
    "tprMiaGuardSourceOnly001Script": (4225, "80869f1581b289d76a8b6c20f6c3834633e3f5f711c7463873ea9d39248a26a0"),
    "tprPostDraftSource003Script": (1246, "4871e8b47f50311be05ee13600bbfc9811fe3900d744571faeed3bc2f2b49ccc"),
    "tprPostDraftDiscovery002Script": (1281, "6b1be73f0abdcd4844a37612f5050ec363cbb344f131423245b628a89528a390"),
    "tprMiaGuardSubmit002Script": (2570, "d68a12c9130a06d7c5779077690630d6bd376d4332a03babf627bd4ca00a9a99"),
    "tprMiaGuardSubmit003Script": (2570, "e9ae96900ff387cea9c3dfaceec84093670b3407a09d699a1ba02df8ccf01e2f"),
    "tprPostMiaSource004Script": (1246, "53f7a99dd6ca6071cb53b44d14b84be769ae1c89c134e1f518c23597585a5298"),
    "tprPostMiaDiscovery003Script": (1281, "4e74637b2f41f6cc8066e06d1e9e72c93f8fbcc44a44c3658dbb35d83ab3d7f3"),
    "tprPostMiaSourceInspect004Script": (7667, "a65601c19e3e0d11e553ada6f7c5d403811a081ccdd8e095e0a17f42af06cd8a"),
}
CUA_STATEMENTS = [
    "await tprSafariHistory.click(107); // observed own New chat button in source-only scope001",
    "await tprSafariHistory.setValue(107,tprRestorePrompt); // registered public prompt",
    "await tprSafariHistory.click(107); await tprSafariHistory.pressKey('super+a'); await tprSafariHistory.paste(tprRestorePrompt); // identical draft, not deliberate Send",
    "await tprSafariHistory.pressKey('super+Down'); // focused own draft; no Return",
    "await tprSafariHistory.click(646); // previously-created own ninth tab, then verify exact own URL and nonce",
    "await tprSafariHistory.click(112); // ONE deliberate own send in successor003 after fresh route+nonce checks",
]
AUTHORITY_FIELDS = ("canonical_admission", "effect_authority", "replay_authority")
SECRET_NAME = re.compile(r"(?i)(?:credential|api[_-]?(?:key|token)|password|secret|bearer)")


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(_value):
    raise ValueError("non-finite JSON constant")


def load_archive():
    return json.loads(ARCHIVE.read_text(encoding="utf-8"), object_pairs_hook=_unique_pairs,
                      parse_constant=_reject_constant)


def validate_archive(archive):
    """Check a public in-memory object without running any retained recipe."""
    assert type(archive) is dict and set(archive) == TOP_KEYS, "closed archive schema"
    assert archive["schema"] == "tpr-ext26-owner-repair-operator-source-archive-v1"
    assert archive["lane_branch"] == "codex/strategy-target-price-revisions"
    assert archive["study_id"] == "TPR-CAP-TILT-EXT26-20261010-v1"
    assert archive["owner_instruction_sha256"] == OWNER_SHA256
    assert archive["retrospective"] is True, "retrospective provenance is mandatory"
    assert all(archive[field] is False for field in AUTHORITY_FIELDS), "no replay/effect/admission authority"
    warning = archive["warning"]
    assert type(warning) is str and all(fragment in warning for fragment in (
        "Spent scopes", "MUST NOT be replayed", "no effect or access authority",
        "section93", "Retrospective hashes do not fabricate preregistration",
    )), "spent retrospective provenance and sole-record limits"
    scope = archive["scope"]
    assert type(scope) is str and all(fragment in scope for fragment in (
        "Exact retained Python", "selected effect-bearing CUA statements",
        "not a complete deterministic UI replay",
        "No source archive/private rows or credentials are embedded",
    )), "archive scope must not promise a complete UI replay or private custody"
    limitations = archive["known_setup_limitations"]
    assert type(limitations) is list and len(limitations) == 5
    assert all(type(item) is str and item for item in limitations)
    assert all(any(fragment in item for item in limitations) for fragment in (
        "History001", "input EOF", "Owner confirmed still draft", "Successor002",
        "not imported/executed", "not native completion", "AST", "exact byte/inverse",
    )), "retain setup failures and limits rather than replacing history"
    prompt = archive["mia_source_only_prompt"]
    assert type(prompt) is str and len(prompt) == 1789
    assert archive["mia_source_only_prompt_sha256"] == PROMPT_SHA256
    assert hashlib.sha256(prompt.encode("utf-8")).hexdigest() == PROMPT_SHA256, "exact public source-only prompt"
    assert archive["selected_cua_effect_statements"] == CUA_STATEMENTS, "selected observed UI statements, not replay authority"
    entries = archive["entries"]
    assert type(entries) is list and len(entries) == 19, "retain exactly nineteen public recipes"
    keys = [entry.get("session_store_key") for entry in entries if type(entry) is dict]
    assert len(keys) == 19 and len(set(keys)) == 19 and set(keys) == set(IDENTITIES), "unique exact recipe identities"
    for entry in entries:
        assert set(entry) == {"bytes", "language", "session_store_key", "sha256", "source"}, "closed entry schema"
        assert entry["language"] == "python"
        assert type(entry["source"]) is str and type(entry["bytes"]) is int
        raw = entry["source"].encode("utf-8")
        count, digest = IDENTITIES[entry["session_store_key"]]
        assert entry["bytes"] == count == len(raw), "exact retained UTF-8 byte count"
        assert entry["sha256"] == digest == hashlib.sha256(raw).hexdigest(), "exact retained recipe bytes"
        ast.parse(entry["source"], filename="<retrospective-public-operator-recipe>")


def _target_names(target):
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, ast.Attribute):
        return [target.attr]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [name for child in target.elts for name in _target_names(child)]
    return []


def refuse_literal_credentials(source):
    """Narrow static literal guard, not proof that arbitrary text is secret-free."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, (str, bytes)) and value.value:
                assert not any(SECRET_NAME.search(name) for target in targets for name in _target_names(target)), "literal credential assignment"
        if isinstance(node, ast.keyword) and node.arg and SECRET_NAME.search(node.arg):
            assert not (isinstance(node.value, ast.Constant) and isinstance(node.value.value, (str, bytes)) and node.value.value), "literal credential argument"
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and isinstance(key.value, str) and SECRET_NAME.search(key.value):
                    assert not (isinstance(value, ast.Constant) and isinstance(value.value, (str, bytes)) and value.value), "literal credential mapping"


def test_retrospective_archive_has_exact_closed_contract_and_all_recipe_bytes():
    validate_archive(load_archive())


@pytest.mark.parametrize("key", IDENTITIES)
def test_each_public_recipe_is_parseable_without_import_compile_or_execution(key):
    entry = next(item for item in load_archive()["entries"] if item["session_store_key"] == key)
    assert isinstance(ast.parse(entry["source"]), ast.Module)
    refuse_literal_credentials(entry["source"])


@pytest.mark.parametrize("field", AUTHORITY_FIELDS)
@pytest.mark.parametrize("value", [True, 0, None, "false"])
def test_in_memory_authority_widening_or_loosely_false_labels_are_rejected(field, value):
    clean = load_archive()
    validate_archive(clean)
    mutated = deepcopy(clean)
    mutated[field] = value
    with pytest.raises(AssertionError, match="authority"):
        validate_archive(mutated)
    validate_archive(clean)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unknown", "byte_count", "hash", "body", "entry_key"])
def test_in_memory_recipe_custody_mutations_are_rejected_without_changing_disk(mutation):
    clean = load_archive()
    validate_archive(clean)
    mutated = deepcopy(clean)
    if mutation == "missing": mutated["entries"].pop()
    elif mutation == "duplicate": mutated["entries"][-1] = deepcopy(mutated["entries"][0])
    elif mutation == "unknown": mutated["entries"][0]["session_store_key"] = "unknown_public_recipe"
    elif mutation == "byte_count": mutated["entries"][0]["bytes"] += 1
    elif mutation == "hash": mutated["entries"][0]["sha256"] = "0" * 64
    elif mutation == "body": mutated["entries"][0]["source"] += "\npass\n"
    else: mutated["entries"][0]["replay_authority"] = False
    with pytest.raises(AssertionError): validate_archive(mutated)
    validate_archive(clean)


@pytest.mark.parametrize("mutation", ["schema", "retrospective", "warning", "scope", "limitations", "prompt", "prompt_hash", "cua", "unknown_key"])
def test_in_memory_scope_provenance_prompt_and_selected_ui_mutations_are_rejected(mutation):
    clean = load_archive()
    validate_archive(clean)
    mutated = deepcopy(clean)
    if mutation == "schema": mutated["schema"] = "invented-replay-executor"
    elif mutation == "retrospective": mutated["retrospective"] = False
    elif mutation == "warning": mutated["warning"] = "May replay all scopes."
    elif mutation == "scope": mutated["scope"] = "Complete native UI replay and current permission."
    elif mutation == "limitations": mutated["known_setup_limitations"].pop()
    elif mutation == "prompt": mutated["mia_source_only_prompt"] = mutated["mia_source_only_prompt"].replace("Do not launch anything.", "You may launch jobs.")
    elif mutation == "prompt_hash": mutated["mia_source_only_prompt_sha256"] = "0" * 64
    elif mutation == "cua": mutated["selected_cua_effect_statements"][-1] = "await unrelated.pressKey('Return');"
    else: mutated["new_access_authority"] = False
    with pytest.raises(AssertionError): validate_archive(mutated)
    validate_archive(clean)


@pytest.mark.parametrize("source", [
    "API_TOKEN = 'SYNTHETIC_NOT_A_REAL_TOKEN'\n",
    "credential: str = 'SYNTHETIC_NOT_A_REAL_TOKEN'\n",
    "request(credential='SYNTHETIC_NOT_A_REAL_TOKEN')\n",
    "value = {'password': 'SYNTHETIC_NOT_A_REAL_PASSWORD'}\n",
])
def test_literal_credential_guard_rejects_synthetic_danger_without_effects(source):
    with pytest.raises(AssertionError, match="literal credential"):
        refuse_literal_credentials(source)


def test_json_contract_rejects_duplicate_keys_and_nonfinite_values():
    with pytest.raises(ValueError, match="duplicate"):
        json.loads('{"effect_authority": false, "effect_authority": true}', object_pairs_hook=_unique_pairs)
    for value in ("NaN", "Infinity", "-Infinity"):
        with pytest.raises(ValueError, match="non-finite"):
            json.loads(value, parse_constant=_reject_constant)
