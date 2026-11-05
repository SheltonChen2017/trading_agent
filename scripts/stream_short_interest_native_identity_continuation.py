"""Source-only stream of already replayed original and continued date reports.

No caller completion flag or general report-bytes constructor is accepted.
The parent and child reports were independently rebuilt in the sealed replay;
this bridge restores their exact qualification type from those pinned bytes.
It does not recreate retrieval or availability dates or admit economics.
"""
from contextlib import contextmanager
import json
import re
import subprocess
from types import MappingProxyType

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_dated_identity as identities
import scripts.continue_short_interest_native_identity as capture
from scripts.qualify_short_interest_action_supplement import _clock
import scripts.load_short_interest_native_identity_continuation as base


def require(value, reason):
    base.replay.require(value, reason)


def _qualification(replayed, entry, raw):
    require(type(replayed) is base.replay.CompletedIdentityReplay, "exact_completed_replay_required")
    state = replayed.payload()
    require(type(entry) is dict and any(base.replay.exact(entry, known)
            for known in state["old_reports"] + state["new_reports"]), "bound_original_or_child_report_required")
    require(type(raw) is bytes and len(raw) == entry["report_bytes"]
            and hash_bytes(raw) == entry["report_bytes_sha256"], "bound_report_original_bytes")
    value = capture.parsed(raw)
    source = state["parent_source"]
    require(type(value) is dict and canonical_json(value).encode() == raw
            and value.get("schema") == "si-native-dated-identity-qualified-date-v1"
            and value.get("query_date") == entry["query_date"]
            and value.get("retrieved_at") == entry["retrieved_at"]
            and value.get("started_at") == source["source_started_at"]
            and value.get("policy_sha256") == hash_payload(identities.identity_policy())
            and value.get("master_archive_sha256") == source["original_native_index"]["archive_sha256"]
            and value.get("master_CSV_sha256") == source["original_native_index"]["CSV_sha256"]
            and base.replay.exact(value.get("authority"), identities._authority())
            and value.get("row_fields") == list(identities.ROW_FIELDS), "replayed_qualification_contract")
    # Private factory is reachable only with the exact replay type and one of
    # its already-rebuilt original report pins; no arbitrary raw-file flag.
    result = object.__new__(identities.DatedIdentityQualification)
    anchor = (raw,)
    for name, item in (("_bytes", raw), ("_anchor", anchor), ("_identity", anchor)):
        object.__setattr__(result, name, item)
    result.to_bytes()
    return result


def iter_qualified_dates(replayed, *, read_original, guard):
    """Bounded-date stream; originals remain in the original source directory."""
    guard()
    require(type(replayed) is base.replay.CompletedIdentityReplay, "exact_completed_replay_required")
    state = replayed.payload()
    expected = state["parent_source"]["dates"]
    entries = state["old_reports"] + state["new_reports"]
    require([entry["query_date"] for entry in entries] == expected
            and expected == sorted(set(expected)), "all_original_and_child_dates_in_order")
    previous, position = _clock(state["parent_source"]["source_started_at"]), 0
    for entry in state["old_reports"]:
        guard()
        raw = read_original(entry["report_path"])
        guard()
        require(previous <= _clock(entry["retrieved_at"]) <= _clock(state["parent_source"]["source_refused_at"]),
                "original_report_clocks_unchanged")
        qualified = _qualification(replayed, entry, raw)
        require(qualified.to_payload()["query_date"] == expected[position], "original_date_position")
        previous, position = _clock(entry["retrieved_at"]), position + 1
        yield qualified
    for entry, raw in replayed.iter_new_reports():
        guard()
        require(previous <= _clock(entry["retrieved_at"])
                and _clock(state["child_started_at"]) <= _clock(entry["retrieved_at"])
                    <= _clock(state["child_completed_at"]), "child_report_clocks_unchanged")
        qualified = _qualification(replayed, entry, raw)
        require(position < len(expected) and qualified.to_payload()["query_date"] == expected[position],
                "child_date_position")
        previous, position = _clock(entry["retrieved_at"]), position + 1
        yield qualified
    guard()
    require(position == len(expected), "complete_exact_date_stream_required")


@contextmanager
def load_for_current_runtime(root, *, runtime_head, actual_remote):
    """Runtime guard is current; source head/remote anchors stay historical.

    This new adapter leaves the released in-flight 64f adapter byte-unchanged.
    Future integration must freeze this file and its exact preflight code first.
    It performs no source/key HTTP and publishes no artifacts.
    """
    capture._require_capture_platform()
    require(root == base.ROOT and type(runtime_head) is str and re.fullmatch(r"[0-9a-f]{40}", runtime_head)
            and type(actual_remote) is str and re.fullmatch(r"[0-9a-f]{40}", actual_remote), "designated_runtime_lane")
    local = lambda: capture._local(root, runtime_head)
    local()
    require(all(base.replay.digest(pin) for pin in base.ANCHORS.values()), "registered_historical_child_pins")
    registered = dict(base.ANCHORS)
    capture._guard_remote(root, actual_remote)
    require(capture._git(root, "merge-base", "--is-ancestor", base.HEAD, runtime_head) == "",
            "historical_child_is_lane_ancestor")
    source = capture.load_parent(root, head=runtime_head)
    local()
    with capture._OwnedOutput(root / base.CHILD, local) as child, \
            capture._OwnedOutput(root / capture.SOURCE, local) as original:
        names = tuple(sorted(base.os.listdir(child._anchor[2])))
        require(len(names) == base.FILE_COUNT, "exact_closed_child_file_count")
        entries = {}
        anchor_names = {"protocol.private.json": "protocol_bytes_sha256", "started.json": "started_bytes_sha256",
                "completed.json": "completed_bytes_sha256", "inventory.private.json": "inventory_bytes_sha256"}
        for name in names:
            raw = base.read_owned_source(child, name, base.maximum(name))
            sha = hash_bytes(raw)
            require(name not in anchor_names or sha == registered[anchor_names[name]], "registered_child_anchor_bytes")
            entries[name] = sha, len(raw)
        files = object.__new__(capture._ParentFiles)
        reader = lambda name: base.read_owned_source(child, name, base.maximum(name))
        anchor = (MappingProxyType(entries), reader)
        for name, value in (("_entries", anchor[0]), ("_reader", reader), ("_anchor", anchor), ("_anchor_identity", anchor)):
            object.__setattr__(files, name, value)
        require(files.inventory_sha256() == registered["aggregate_inventory_sha256"], "registered_child_all_file_inventory")
        state = source.payload()
        claim_id = hash_payload({"source_inventory_sha256": state["source_inventory_sha256"],
                "failed_request_sha256": state["failed_request_sha256"],
                "failed_start_bytes_sha256": state["failed_start_bytes_sha256"],
                "purpose": "single_explicit_native_identity_manual_continuation"})
        budget = base.read_owned_source(child, "budget-" + claim_id + ".json", 65536, parent=True)

        def historical(commit, name):
            child.check()
            require(commit == base.HEAD and name in capture.CODE_FILES, "exact_historical_child_code_not_runtime_code")
            response = subprocess.run(["git", "show", commit + ":" + name], cwd=root,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            child.check()
            require(response.returncode == 0 and type(response.stdout) is bytes, "historical_child_code_unavailable")
            return response.stdout

        replayed = base.replay.verify_completed_continuation(source, files, byte_pins=files.pins(),
                inventory_sha256=registered["aggregate_inventory_sha256"], budget_raw=budget,
                budget_sha256=registered["budget_bytes_sha256"], expected_head=base.HEAD,
                expected_protocol_sha256=registered["protocol_bytes_sha256"],
                expected_code_identity_sha256=registered["code_identity_sha256"], historical_code=historical,
                local_guard=child.check, expected_run_id=base.RUN_ID, expected_remote_head=base.REMOTE)
        original_refs = {entry["report_path"]: entry for entry in state["completed_reports"]}

        def read_original(name):
            original.check()
            require(name in original_refs, "original_44_registered_report_path_only")
            raw = base.read_owned_source(original, name, identities.MAXIMUM_DATE_REPORT_BYTES)
            pin = original_refs[name]
            require(len(raw) == pin["report_bytes"] and hash_bytes(raw) == pin["report_bytes_sha256"],
                    "original_report_custody_unchanged")
            return raw

        def guard():
            child.check()
            original.check()
            require(base.ANCHORS == registered and tuple(sorted(base.os.listdir(child._anchor[2]))) == names,
                    "completed_stream_source_inventory_changed")

        guard()
        capture._guard_remote(root, actual_remote)
        yield replayed, iter_qualified_dates(replayed, read_original=read_original, guard=guard)
        guard()
