"""Read-only APFS stamp evidence that exec13448 never created a per-ticket START.

SI-CR24-001. Only lstat is called: nothing is opened, listed, mounted,
detached or written, and no key, claim body or provider is touched. Creating
or removing a directory entry sets that directory's mtime and ctime to the
current time; utimes() can restore mtime but always sets ctime to now. At
e756763 Main creates capture/starts/NNNNNN only after the claim file exists,
and the only key read and GET follow a START control in such a directory.
A container whose mtime equals its birth time and whose ctime predates the
claim file's birth therefore never held a per-ticket directory. A changed
system clock or an edit below the filesystem is outside what stat can show.
This is evidence for a frozen resolution policy only: it grants no dispatch,
refund, reset or release of SI-BUILD-20261028-052.
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
# (inode, mtime_ns, ctime_ns) by lstat on 2026-10-28; a later change shows here.
PINNED = {"mount/capture/starts": (19, 1793115452569302191, 1793115452569366316),
    "mount/capture/received": (20, 1793115452905836532, 1793115452905944324),
    "mount/capture/responses": (21, 1793115453257575693, 1793115453257656443),
    CLAIM: (23, 1793115455606139543, 1793115456838350715)}


class StampEvidenceRefusal(ValueError): pass


def require(value, code):
    if not value: raise StampEvidenceRefusal("REFUSED: " + code)


def observe(namespace):
    facts = {}
    for name in ("", "mount", *CONTAINERS, CLAIM):
        info = os.lstat(namespace / name if name else namespace)
        facts[name] = {"device": info.st_dev, "inode": info.st_ino, "mode": info.st_mode, "uid": info.st_uid,
            "links": info.st_nlink, "birth_ns": round(info.st_birthtime * 1e9),
            "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns}
    return facts


def classify(facts, uid):
    namespace, mount, claim = facts[""], facts["mount"], facts[CLAIM]
    require(stat.S_ISDIR(namespace["mode"]) and stat.S_ISDIR(mount["mode"])
        and mount["device"] != namespace["device"], "run13448_mount_not_separate_volume")
    require(stat.S_ISREG(claim["mode"]) and claim["links"] == 1 and claim["uid"] == uid
        and claim["device"] == mount["device"], "run13448_claim_changed")
    for name in CONTAINERS:
        item = facts[name]
        require(stat.S_ISDIR(item["mode"]) and stat.S_IMODE(item["mode"]) == 0o700 and item["uid"] == uid
            and item["device"] == mount["device"], "run13448_container_changed")
        require(item["links"] == 2, "run13448_container_not_empty")  # APFS: 2 + one per entry.
        require(abs(item["mtime_ns"] - item["birth_ns"]) <= BIRTH_TOLERANCE_NS, "run13448_container_entry_changed")
        require(item["mtime_ns"] <= item["ctime_ns"] < claim["birth_ns"], "run13448_container_changed_after_claim")
    return {"schema": "si-count-run13448-stamp-evidence-v1", "containers_never_held_an_entry": True,
        "containers_last_changed_before_claim": True, "per_ticket_START_directories_created": 0,
        "provider_key_read_or_GET_possible": False,
        "observable_residual": "changed_system_clock_or_below_filesystem_edit",
        "release_refund_or_dispatch_authority": False}


def pins_match(facts):
    return all((facts[name]["inode"], facts[name]["mtime_ns"], facts[name]["ctime_ns"]) == pinned
        for name, pinned in PINNED.items())


def main():
    try:
        facts = observe(ROOT / NAMESPACE)
        result = {**classify(facts, os.getuid()), "pins_match_2026_10_28_observation": pins_match(facts)}
    except StampEvidenceRefusal as error:
        print(canonical_json({"status": "refused", "code": str(error)})); return 2
    except OSError:
        print(canonical_json({"status": "refused", "code": "REFUSED: run13448_lstat_failed"})); return 2
    print(canonical_json(result))
    return 0 if result["pins_match_2026_10_28_observation"] else 2


if __name__ == "__main__":
    sys.exit(main())
