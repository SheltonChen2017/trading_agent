"""Fail-closed registry for rejected pre-V2 analyst outcome runners."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import NoReturn, Sequence


REGISTRY_PATH = Path(__file__).resolve().parent / "specs" / "legacy_reproduction_registry.json"
_REGISTRY_KEYS = {"schema", "entries"}
_ENTRY_KEYS = {
    "reproduction_id",
    "script_name",
    "frozen_dataset_sha256",
    "producing_commit",
    "classification",
    "network_access",
    "may_update_active_findings",
    "owner_authorized",
}


class LegacyReproductionBlocked(RuntimeError):
    """A rejected-family runner attempted outcome or network access."""


def _load_registry() -> tuple[dict[str, object], ...]:
    try:
        value = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LegacyReproductionBlocked("legacy reproduction registry is unreadable") from exc
    if not isinstance(value, dict) or set(value) != _REGISTRY_KEYS:
        raise LegacyReproductionBlocked("legacy reproduction registry has an unknown schema")
    if value["schema"] != "arv2-legacy-reproduction-registry-v1":
        raise LegacyReproductionBlocked("legacy reproduction registry version is unsupported")
    entries = value["entries"]
    if not isinstance(entries, list):
        raise LegacyReproductionBlocked("legacy reproduction entries must be a list")
    parsed: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw in entries:
        if not isinstance(raw, dict) or set(raw) != _ENTRY_KEYS:
            raise LegacyReproductionBlocked("legacy reproduction entry has unknown fields")
        reproduction_id = raw["reproduction_id"]
        if (
            not isinstance(reproduction_id, str)
            or not reproduction_id.startswith("legacy-reproduction-")
            or reproduction_id in seen
        ):
            raise LegacyReproductionBlocked("legacy reproduction ID is invalid or duplicated")
        seen.add(reproduction_id)
        if raw["classification"] != "historical_non_new_non_v2":
            raise LegacyReproductionBlocked("legacy reproduction classification is unsafe")
        if raw["network_access"] is not False or raw["may_update_active_findings"] is not False:
            raise LegacyReproductionBlocked("legacy reproduction cannot access network or active findings")
        if raw["owner_authorized"] is not True:
            raise LegacyReproductionBlocked("legacy reproduction lacks exact owner authorization")
        for hash_name in ("frozen_dataset_sha256", "producing_commit"):
            expected_length = 64 if hash_name.endswith("sha256") else 40
            digest = raw[hash_name]
            if (
                not isinstance(digest, str)
                or len(digest) != expected_length
                or any(character not in "0123456789abcdef" for character in digest)
            ):
                raise LegacyReproductionBlocked(f"legacy {hash_name} is not canonical")
        parsed.append(raw)
    return tuple(parsed)


def quarantine_legacy_runner(
    *, script_name: str, argv: Sequence[str] | None = None
) -> NoReturn:
    """Refuse a legacy runner before any network or outcome is loaded.

    A future historical reproduction must first acquire a permanent owner
    registry entry and an exact frozen local input. Even then this active
    entrypoint remains non-runnable until a reviewed offline-only adapter is
    added; it can never fall back to the old mutable fetch functions.
    """
    parser = argparse.ArgumentParser(
        description="Quarantined historical runner; not Analyst Revisions V2 evidence"
    )
    parser.add_argument("--reproduction-id")
    parser.add_argument("--frozen-dataset", type=Path)
    arguments = parser.parse_args(argv)
    if not arguments.reproduction_id or arguments.frozen_dataset is None:
        raise LegacyReproductionBlocked(
            "rejected legacy outcome path is quarantined: a permanent registered "
            "reproduction ID and frozen local dataset are required"
        )
    matching = [
        entry
        for entry in _load_registry()
        if entry["reproduction_id"] == arguments.reproduction_id
        and entry["script_name"] == script_name
    ]
    if len(matching) != 1:
        raise LegacyReproductionBlocked("reproduction ID is absent or belongs to another script")
    try:
        dataset_path = arguments.frozen_dataset.resolve(strict=True)
        if not dataset_path.is_file():
            raise LegacyReproductionBlocked(
                "frozen dataset must be one immutable local file"
            )
        actual_hash = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise LegacyReproductionBlocked(
            "frozen dataset is missing or unreadable"
        ) from exc
    if actual_hash != matching[0]["frozen_dataset_sha256"]:
        raise LegacyReproductionBlocked("frozen dataset hash does not match the owner registry")
    raise LegacyReproductionBlocked(
        "registered historical reproduction is classified non-new/non-V2, but this "
        "active checkout has no reviewed offline adapter; use an owner-approved "
        "isolated reproduction checkout and never update active findings"
    )
