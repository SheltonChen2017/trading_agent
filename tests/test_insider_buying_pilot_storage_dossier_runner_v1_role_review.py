"""Claude section 383 review: role-narrowed dossier worker read policies.

The health, readback and discovery profiles are cut down from the full worker
profile by string replacement, and nothing checked that the replacement found
its target. These tests pin what each role may and may not read. Each absence
check is preceded by a control that the full profile contains the same literal,
so a changed literal format cannot make the absence pass vacuously.
Invented values only; no retained input, git, sandbox launch or provider access.
"""
import json

import pytest

pytest.importorskip("fcntl", reason="supported macOS/POSIX retained custody")
from research import insider_buying_pilot_storage_dossier_runner_v1 as m


def _bound():
    sources = {m.SELF: "a" * 64}
    return {"root": str(m.ROOT), "branch": m.BRANCH, "head": "b" * 40, "clean": True,
            "source_sha256": sources, "source_inventory_sha256": m.sha(m.raw(sources))}


def _literal(path):
    return "(literal " + json.dumps(str(path)) + ")"


FIXED = m.prior.fixed_input_paths()
DISCOVERY_ALLOWED = m.prior.PROVIDER / "complete.json"


def test_full_worker_profile_contains_every_fixed_input_literal():
    # Control for the absence checks below: same literal format, present here.
    profile = m.policy(_bound())
    assert FIXED and all(_literal(path) in profile for path in FIXED)
    assert _literal(m.METADATA_PATH) in profile


@pytest.mark.parametrize("kwargs", ({"role": "health"}, {"readback": True, "role": "readback"}))
def test_health_and_readback_profiles_cannot_read_any_retained_input(kwargs):
    profile = m.policy(_bound(), **kwargs)
    assert not [path for path in FIXED if _literal(path) in profile]
    assert _literal(m.METADATA_PATH) not in profile
    for token in ("(deny network*)", "(deny process-fork)", "(deny file-write*)"):
        assert token in profile


def test_discovery_profile_reads_only_the_provider_receipt_and_the_controls_metadata():
    profile = m.policy(_bound(), role="discovery")
    assert [path for path in FIXED if _literal(path) in profile] == [DISCOVERY_ALLOWED]
    assert _literal(m.METADATA_PATH) in profile
