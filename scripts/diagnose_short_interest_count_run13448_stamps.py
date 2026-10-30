"""Present-path stamp observations; historical exec13448 dispatch stays unknown.

Only lstat is called: no file is opened/listed, no mount is changed, and no
key, claim body or provider is touched. V2 replaces V1's asserted zero/never
history with observed relationships and an explicitly conditional code-order
implication. Sequential present stats cannot authenticate original namespace,
mount/backing, capture, claim or execution lineage, APFS semantics, an unchanged
clock, or unobserved changes. Even matching the partial later leaf pins does
not establish original custody. No refund/reset/dispatch or 052 release follows.
"""
import os
from pathlib import Path
import stat
import sys

from data.hashing import canonical_json

ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest")
NAMESPACE = Path("artifacts/short_interest/native_reported_counts/count-response-20261027-v1-"
    "2aa15b2fae72b6421a75702ea961af530a3b0901de342f670c21e1caaa328cd0-chunk001")
CONTAINERS = ("mount/capture/starts", "mount/capture/received", "mount/capture/responses")
CLAIM = "mount/claim/claim.spent.json"
BIRTH_TOLERANCE_NS = 1000  # st_birthtime is a float, about 0.24 us resolution in 2026.
# PARTIAL later observation: only (inode, mtime_ns, ctime_ns) on four leaves.
# These are not original capture/mount/claim custody pins and do not cover
# device, birth time, protection, ownership or intermediate ancestor identity.
PINNED = {"mount/capture/starts": (19, 1793115452569302191, 1793115452569366316),
    "mount/capture/received": (20, 1793115452905836532, 1793115452905944324),
    "mount/capture/responses": (21, 1793115453257575693, 1793115453257656443),
    CLAIM: (23, 1793115455606139543, 1793115456838350715)}


class StampEvidenceRefusal(ValueError): pass


def require(value, code):
    if not value: raise StampEvidenceRefusal("REFUSED: " + code)


def observe(namespace):
    facts = {}
    for name in ("", "mount", "mount/capture", "mount/claim", *CONTAINERS, CLAIM):
        info = os.lstat(namespace / name if name else namespace)
        facts[name] = {"device": info.st_dev, "inode": info.st_ino, "mode": info.st_mode, "uid": info.st_uid,
            "links": info.st_nlink, "birth_ns": round(info.st_birthtime * 1e9),
            "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns,
            "flags": getattr(info, "st_flags", None)}
    return facts


def classify(facts, uid):
    namespace, mount, claim = facts[""], facts["mount"], facts[CLAIM]
    require(stat.S_ISDIR(namespace["mode"]) and stat.S_ISDIR(mount["mode"])
        and mount["device"] != namespace["device"], "run13448_mount_not_separate_volume")
    for name in ("", "mount", "mount/capture", "mount/claim"):
        item = facts[name]
        require(stat.S_ISDIR(item["mode"]) and stat.S_IMODE(item["mode"]) == 0o700 and item["uid"] == uid
            and (not name or item["device"] == mount["device"]), "run13448_ancestor_changed")
    require(stat.S_ISREG(claim["mode"]) and claim["links"] == 1 and claim["uid"] == uid
        and stat.S_IMODE(claim["mode"]) == 0o600 and claim["device"] == mount["device"], "run13448_claim_changed")
    for name in CONTAINERS:
        item = facts[name]
        require(stat.S_ISDIR(item["mode"]) and stat.S_IMODE(item["mode"]) == 0o700 and item["uid"] == uid
            and item["device"] == mount["device"], "run13448_container_changed")
        # Only the present link count is observed; APFS identity/semantics are
        # an unauthenticated assumption, never a proven historical emptiness.
        require(item["links"] == 2, "run13448_container_not_empty")
        require(abs(item["mtime_ns"] - item["birth_ns"]) <= BIRTH_TOLERANCE_NS, "run13448_container_entry_changed")
        require(item["mtime_ns"] <= item["ctime_ns"] < claim["birth_ns"], "run13448_container_changed_after_claim")
    return {"schema": "si-count-run13448-stamp-observation-v2", "status": "present_stamp_relationships_observed",
        "observation_scope": "sequential_present_path_lstat_only_not_atomic_or_original_custody",
        "present_container_link_counts_equal_two": True,
        "present_container_mtimes_match_birth_times_within_tolerance": True,
        "present_container_ctimes_precede_present_claim_birth_time": True,
        "present_claim_immutable_flag_set": type(claim["flags"]) is int and bool(claim["flags"] & 2),
        "partial_leaf_pin_scope": "four_leaves_inode_mtime_ctime_later_2026_10_28_observation_only",
        "original_lineage_authenticated": False, "historical_zero_dispatch_verified": False,
        "historical_counts": {"per_ticket_START_directories_created": None, "provider_key_reads": None,
            "provider_GET_requests": None, "internal_START_reservations": None, "charged_or_reserved_bytes": None},
        "conditional_code_order_implication": "Only if all listed assumptions hold do these stamp relationships support no per-ticket START; original e756763 code then implies no key read or GET.",
        "required_unauthenticated_assumptions": ["original_namespace_mount_backing_capture_claim_and_container_lineage",
            "original_e756763_code_and_execution_path", "APFS_directory_entry_and_timestamp_semantics",
            "unchanged_system_clock", "no_unobserved_namespace_volume_metadata_or_below_filesystem_changes"],
        "release_refund_or_dispatch_authority": False}


def pins_match(facts):
    return all((facts[name]["inode"], facts[name]["mtime_ns"], facts[name]["ctime_ns"]) == pinned
        for name, pinned in PINNED.items())


def main():
    try:
        facts = observe(ROOT / NAMESPACE)
        matched = pins_match(facts)
        result = {**classify(facts, os.getuid()), "partial_leaf_pins_match_2026_10_28_observation": matched}
        if not matched: result["status"] = "partial_leaf_pin_mismatch"
    except StampEvidenceRefusal as error:
        print(canonical_json({"status": "refused", "code": str(error)})); return 2
    except OSError:
        print(canonical_json({"status": "refused", "code": "REFUSED: run13448_lstat_failed"})); return 2
    print(canonical_json(result))
    return 0 if matched else 2


if __name__ == "__main__":
    sys.exit(main())
