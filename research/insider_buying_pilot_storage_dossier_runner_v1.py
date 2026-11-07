"""One offline current-storage qualification and retained-original dossier.

The old storage guard and failed audit remain unchanged. The new receipt
qualifies present byte equivalence only. No provider, credential or QC call.
"""
from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from research import insider_buying_pilot_pit_retained_audit_runner_v1 as prior
from research import insider_buying_pilot_fmp_eod_qualification_v2 as producer
from research import insider_buying_pilot_provider_controls_v1 as controls
from research import insider_buying_pilot_storage_transition_v1 as transition
from research import insider_buying_pilot_historical_dossier_v1 as dossier

stable, ROOT, BRANCH = prior.stable, prior.ROOT, prior.BRANCH
SELF = "research/insider_buying_pilot_storage_dossier_runner_v1.py"
OWN = (SELF, "tests/test_insider_buying_pilot_storage_dossier_runner_v1.py",
       "research/insider_buying_pilot_storage_transition_v1.py",
       "tests/test_insider_buying_pilot_storage_transition_v1.py",
       "research/insider_buying_pilot_historical_dossier_v1.py",
       "tests/test_insider_buying_pilot_historical_dossier_v1.py", *prior.OWN)
SCHEMA = "insider-pilot-storage-dossier-runner-v1"
AUDIT_ID = "ib-storage-transition-dossier-v1-20261107-once"
OUTPUT = stable.PRIVATE_CUSTODY_ROOT / AUDIT_ID
METADATA_PATH = prior.PROVIDER / "controls-metadata.json"
OUTPUT_NAMES = ("reservation.json", "observation-started.json", "transition.json", "dossier.json", "complete.json")
MAX_IPC = 1024 * 1024
GIT_IMAGE = Path("/Library/Developer/CommandLineTools/usr/bin/git")
GIT_LIBRARIES = Path("/Library/Developer/CommandLineTools/usr/lib")


class StorageDossierError(ValueError):
    """Only fixed refusal codes; no original source or exception text."""


def need(ok, code="storage_dossier_refused"):
    if not ok:
        raise StorageDossierError(code)


def raw(value):
    return prior.raw(value)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def compact(identity):
    return {"head": identity["head"], "sources": dict(identity["source_sha256"]),
            "source_inventory_sha256": identity["source_inventory_sha256"]}


def identity(head):
    value = producer._identity(head)
    sources = dict(value["source_sha256"])
    for name in OWN:
        data = (ROOT / name).read_bytes()
        blob = subprocess.check_output(["git", "--no-optional-locks", "show", head + ":" + name], cwd=ROOT,
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}, stderr=subprocess.DEVNULL)
        need(data == blob, "source_refused")
        sources[name] = sha(data)
    value = {**value, "source_sha256": sources, "source_inventory_sha256": sha(raw(sources))}
    producer._current(value)
    return value


def registration():
    return {"schema": SCHEMA + "/registration", "audit_id": AUDIT_ID,
            "purpose": "present_storage_and_twelve_original_identity_dossier",
            "fixed_metadata_leaves": 7, "additional_control_metadata_leaves": 1,
            "selected_original_parents": 12, "historical_changed_fields_required": ["device"],
            "historical_physical_continuity_claimed": False, "historical_binding_repaired": False,
            "old_namespace_resumed": False, "provider_requests": 0, "credential_reads": 0,
            "qc_accesses": 0, "outcome_looks": 0, "authority": transition.authority()}


def selected_paths(metadata):
    controls._validate_metadata(metadata)
    need(metadata["fixture_only"] is False, "metadata_refused")
    result = tuple(Path(row["body_path"]) for row in metadata["selected"])
    need(len(result) == len(set(result)) == 12 and all(path.resolve() == path for path in result), "metadata_refused")
    return result


def policy(identity_value, *, metadata=None, parent=False, readback=False):
    paths = () if metadata is None else selected_paths(metadata)
    prior._disjoint_runtime_directories((Path(sys.base_prefix).resolve(), Path(sys.executable).parent.parent.resolve()),
                                       (controls.WARM_ROOT, controls.RECENT_ROOT))
    result = prior.policy(sources=identity_value["source_sha256"])
    leaves = [METADATA_PATH, *paths]
    if parent:
        result = result.replace("(deny process-fork)", "")
        result += '(allow process-exec (literal "/usr/bin/git") (literal "/usr/bin/sandbox-exec") (literal ' + json.dumps(str(GIT_IMAGE)) + '))'
        result += '(allow file-write* (subpath ' + json.dumps(str(OUTPUT)) + ') (literal "/dev/null"))'
        common = subprocess.check_output(["git", "rev-parse", "--git-common-dir"], cwd=ROOT,
            env={"PATH": "/usr/bin:/bin"}, stderr=subprocess.DEVNULL).decode().strip()
        common = (ROOT / common).resolve()
        # Administrative Git objects/config only, never sibling checkout source.
        result += '(allow file-read-data (subpath ' + json.dumps(str(common)) + '))'
        prior._disjoint_runtime_directories((GIT_LIBRARIES,), (ROOT, stable.PRIVATE_CUSTODY_ROOT, controls.RECENT_ROOT))
        result += '(allow file-read-data (subpath ' + json.dumps(str(GIT_LIBRARIES)) + '))'
        leaves.extend((ROOT / ".git", ROOT / ".gitignore", GIT_IMAGE))
    if parent or readback:
        leaves.extend(OUTPUT / name for name in (*OUTPUT_NAMES, "failure.json"))
    ancestors = {ancestor for leaf in leaves for ancestor in leaf.parents}
    result += '(allow file-read-data ' + ' '.join('(literal ' + json.dumps(str(path)) + ')'
        for path in (*leaves, *sorted(ancestors))) + ')'
    return result


def install_parent_policy(profile):
    library = ctypes.CDLL("/usr/lib/libsandbox.dylib", use_errno=True)
    call = library.sandbox_init
    call.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.POINTER(ctypes.c_char_p)]
    call.restype = ctypes.c_int
    error = ctypes.c_char_p()
    need(call(profile.encode(), 0, ctypes.byref(error)) == 0, "parent_isolation_refused")


def baseline_policy():
    targets = [Path(sys.executable).resolve(), Path("/usr/bin/git"), GIT_IMAGE, Path("/usr/bin/sandbox-exec")]
    relaunch = targets[0].parents[1] / "Resources/Python.app/Contents/MacOS/Python"
    if relaunch.is_file(): targets.append(relaunch.resolve())
    return ('(version 1)(allow default)(deny network*)(deny process-exec)(deny file-write*)'
            '(allow file-write* (subpath ' + json.dumps(str(OUTPUT)) + ') (literal "/dev/null"))'
            '(allow process-exec ' + ' '.join('(literal ' + json.dumps(str(path)) + ')' for path in targets) + ')')


def prove_parent():
    stable.native._isolated()
    stable.custody._effective_denial(require_fork=False)
    try:
        os.execve("/usr/bin/security", ["security", "help"], {"PATH": "/usr/bin:/bin"})
    except OSError as error:
        need(error.errno in {errno.EACCES, errno.EPERM}, "parent_isolation_refused")
    else:
        raise StorageDossierError("parent_isolation_refused")
    try:
        descriptor = os.open("/private/tmp/ib-storage-dossier-forbidden-write", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError as error:
        need(error.errno in {errno.EACCES, errno.EPERM}, "parent_isolation_refused")
    else:
        os.close(descriptor)
        raise StorageDossierError("parent_isolation_refused")


def _send(value, guard):
    wire = raw({"ok": True, "value": value}) + b"\n"
    need(len(wire) <= MAX_IPC, "output_refused")
    sys.stdout.buffer.write(wire); sys.stdout.buffer.flush(); guard.check()


def _close(holders, guard):
    failed = False
    for held in reversed(holders):
        try:
            held.close()
        except Exception:
            failed = True
    if guard is not None:
        try:
            guard.close()
        except Exception:
            failed = True
    if failed:
        raise SystemExit(2)


def _metadata(provider, guard):
    complete = prior.decode(provider.read("complete.json", prior.PINS["provider_complete"], check=guard.check), prior.PINS["provider_complete"])
    pin = complete["published_leaf_pins"]["controls-metadata.json"]
    metadata = prior.decode(provider.read("controls-metadata.json", pin, check=guard.check), pin)
    selected_paths(metadata)
    return complete, metadata, pin


class BodyHold(controls._Hold):
    """Add full ctime/group/flags identity seals to the existing selected reader."""
    def __init__(self, root):
        self.full_versions = {}
        super().__init__(root)

    def read(self, relative, *, cap, pin=None):
        bits = relative.split("/")
        need(len(bits) == 2 and bits[0] == "objects" and re.fullmatch(r"[0-9a-f]{64}\.bin", bits[1]), "body_path_refused")
        directory = self.directory("objects")
        before = prior.version(os.stat(bits[1], dir_fd=directory.fd, follow_symlinks=False))
        need(relative not in self.full_versions or self.full_versions[relative] == before, "body_changed")
        value = super().read(relative, cap=cap, pin=pin)
        descriptor = self.leaves[relative][0]
        need(before == prior.version(os.fstat(descriptor)) == prior.version(os.stat(
            bits[1], dir_fd=directory.fd, follow_symlinks=False)), "body_changed")
        self.full_versions[relative] = before
        return value


def discovery_worker(identity_value):
    guard, holders = None, []
    try:
        stable.native._isolated(); stable.native.source_runner._prove_isolation()
        guard = stable.native._WorkerMemoryGuard(); prior._source_current(compact(identity_value))
        provider = prior.Held(prior.PROVIDER); holders.append(provider)
        _complete, metadata, pin = _metadata(provider, guard)
        provider.check(check=guard.check); prior._source_current(compact(identity_value))
        _send({"completed": True, "metadata": metadata, "metadata_pin": pin}, guard)
    except Exception:
        _send({"completed": False, "phase": "metadata_discovery", "code": "metadata_refused"}, guard) if guard is not None else None
    finally:
        _close(holders, guard)


def health_worker(identity_value):
    guard = None
    try:
        stable.native._isolated(); stable.native.source_runner._prove_isolation()
        guard = stable.native._WorkerMemoryGuard(); prior._source_current(compact(identity_value))
        _send({"completed": True, "health_passed": True, "actual_input_leaves": 0,
               "source_images": len(identity_value["source_sha256"])}, guard)
    finally:
        if guard is not None: guard.close()


def _originals(metadata, cases, guard, holders):
    need(type(cases) is list and len(cases) == 12 and len(metadata["selected"]) == 12, "original_control_refused")
    output = []
    by_root = {}
    for row, expected in zip(metadata["selected"], cases):
        guard.check()
        root = controls.WARM_ROOT if row["group"] == "warmup" else controls.RECENT_ROOT
        if root not in by_root:
            held = BodyHold(root); by_root[root] = held; holders.append(held)
        pin = row["body_pin"]
        body = by_root[root].read("objects/" + pin["sha256"] + ".bin", cap=controls.MAX_BODY,
                                 pin=(pin["bytes"], pin["sha256"]))
        projected = controls.project_sec_complete_submission(controls.SecCompleteSubmissionTarget(**row["target"]), body)
        recorded = controls.warm._project(body, {"period": projected.target.period,
            "accession_number": projected.target.accession_number, "form_type": projected.target.form_type,
            "filing_date": projected.target.filing_date, "issuer_cik": projected.target.issuer_cik,
            "master_decoded_sha256": projected.target.quarterly_index_sha256,
            "url": projected.target.complete_submission_url}) if row["group"] == "warmup" else projected.to_payload()
        need(raw(recorded) == raw(row["recorded_projection"])
             and raw(controls._case(row, projected)) == raw(expected), "original_control_refused")
        output.append(dossier.extract_identity(projected))
    for held in by_root.values():
        held.check()
    return output


def dossier_worker(identity_value, discovered):
    guard, holders, phase = None, [], "native"
    try:
        stable.native._isolated(); stable.native.source_runner._prove_isolation()
        guard = stable.native._WorkerMemoryGuard(); prior._source_current(compact(identity_value))
        phase = "metadata"
        provider, proof, refs = prior.Held(prior.PROVIDER), prior.Held(prior.PROOF), prior.Held(prior.SHARADAR)
        holders.extend((provider, proof, refs))
        complete, metadata, metadata_pin = _metadata(provider, guard)
        need(raw(metadata) == raw(discovered["metadata"]) and metadata_pin == discovered["metadata_pin"], "metadata_changed")
        named = complete["published_leaf_pins"]
        cases_value = prior.decode(provider.read("controls.json", named["controls.json"], check=guard.check), named["controls.json"])
        need(cases_value["metadata_sha256"] == metadata_pin["sha256"] and cases_value["fixture_only"] is False
             and len(cases_value["cases"]) == 12, "metadata_refused")
        qualification = prior.decode(provider.read("storage-qualification.json", named["storage-qualification.json"], check=guard.check), named["storage-qualification.json"])
        old_proof = prior.decode(proof.read("complete.json", prior.PINS["proof_complete"], check=guard.check), prior.PINS["proof_complete"])
        reference = prior.decode(refs.read("complete.json", prior.PINS["reference_complete"], check=guard.check), prior.PINS["reference_complete"])
        need(reference["capture_manifest_sha256"] == prior.MANIFEST and reference["fixture_only"] is False
             and reference["tickers_projection_sha256"] == prior.PINS["tickers_projection"]["sha256"]
             and reference["actions_projection_sha256"] == prior.PINS["actions_projection"]["sha256"], "metadata_refused")
        root_hold = stable._HeldChain(stable.PRIVATE_CUSTODY_ROOT, ()); holders.append(root_hold)
        stable._managed(root_hold); physical = stable._storage_identity(root_hold, fixture=False)
        pins = {**prior.PINS, "provider_controls": named["controls.json"], "provider_storage": named["storage-qualification.json"]}
        # Hash all seven leaves before constructing the separate current receipt.
        for name, key in (("tickers_projection.json", "tickers_projection"), ("actions_projection.json", "actions_projection")):
            refs.read(name, prior.PINS[key], check=guard.check)
        phase = "transition"
        receipt = transition.build_transition(physical, old_proof, qualification, pins, compact(identity_value), fixture_only=False)
        phase = "reference_audit"
        audit_value = prior.audit.build_audit(cases_value["cases"], complete,
            prior.projection(refs, "tickers_projection.json", prior.PINS["tickers_projection"],
                columns=prior.reference.TICKER_COLUMNS, schema=prior.reference.TICKERS_SCHEMA, count=74150, check=guard.check),
            prior.projection(refs, "actions_projection.json", prior.PINS["actions_projection"],
                columns=prior.reference.ACTION_COLUMNS, schema=prior.reference.ACTIONS_SCHEMA, count=698455, check=guard.check),
            pins, check=guard.check, fixture_only=False)
        phase = "original_identities"
        identities = _originals(metadata, cases_value["cases"], guard, holders)
        phase = "dossier"
        value = dossier.build_dossier(cases_value["cases"], identities, audit_value, receipt.sha256,
                                      compact(identity_value), fixture_only=False)
        phase = "final_inputs"
        for held in holders:
            if type(held) is prior.Held: held.check(check=guard.check)
            elif type(held) is BodyHold: held.check()
            else: held.recheck()
        need(stable._storage_identity(root_hold, fixture=False) == physical, "storage_changed")
        prior._source_current(compact(identity_value)); guard.check()
        leaf_count = sum(len(held.leaves) for held in holders if isinstance(held, (prior.Held, BodyHold)))
        need(leaf_count == 20, "input_accounting_refused")
        _send({"completed": True, "transition": receipt.to_payload(), "dossier": dossier.private_payload(value),
               "audit_summary": prior.audit.public_summary(audit_value), "dossier_summary": dossier.public_summary(value),
               "metadata_pin": metadata_pin, "current_storage_identity": physical,
               "input_leaves": leaf_count, "source_inventory_sha256": identity_value["source_inventory_sha256"]}, guard)
    except Exception:
        if guard is not None: _send({"completed": False, "phase": phase, "code": "storage_dossier_refused"}, guard)
    finally:
        _close(holders, guard)


def launch(function, identity_value, argument=None, *, readback=False):
    need(function in {"health_worker", "discovery_worker", "dossier_worker", "readback_worker"}, "worker_refused")
    code = "import sys;sys.path.insert(0," + repr(str(ROOT)) + ");from research import insider_buying_pilot_storage_dossier_runner_v1 as m;m." + function + "(" + repr(identity_value)
    if argument is not None: code += "," + repr(argument)
    code += ")"
    metadata = argument["metadata"] if function == "dossier_worker" else None
    command = ("/usr/bin/sandbox-exec", "-p", policy(identity_value, metadata=metadata, readback=readback), sys.executable,
               "-I", "-S", "-B", "-X", "pycache_prefix=" + stable.native.EMPTY_CACHE_PREFIX, "-c", code)
    value = stable.source._launch(command, timeout=240)
    need(type(value) is dict and value.get("completed") is True, "worker_refused")
    return value


def validate_result(value, bound, metadata_pin, physical):
    need(type(metadata_pin) is dict and set(metadata_pin) == {"bytes", "sha256"}
         and type(metadata_pin["bytes"]) is int and 0 < metadata_pin["bytes"] <= controls.MAX_METADATA
         and type(metadata_pin["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", metadata_pin["sha256"]), "worker_result_refused")
    need(type(value) is dict and set(value) == {"completed", "transition", "dossier", "audit_summary", "dossier_summary",
        "metadata_pin", "current_storage_identity", "input_leaves", "source_inventory_sha256"}
        and value["completed"] is True and type(value["input_leaves"]) is int and value["input_leaves"] == 20
        and value["source_inventory_sha256"] == bound["source_inventory_sha256"]
        and raw(value["current_storage_identity"]) == raw(physical)
        and raw(value["metadata_pin"]) == raw(metadata_pin), "worker_result_refused")
    private_transition = transition.validate_payload(value["transition"], execution_identity=compact(bound))
    need(raw(private_transition["current_storage_identity"]) == raw(physical)
         and private_transition["fixture_only"] is False, "worker_result_refused")
    transition_hash = sha(raw(private_transition))
    private_dossier = dossier.validate_payload(value["dossier"], transition_hash, compact(bound), fixture_only=False)
    need(raw(dossier.summary_from_payload(private_dossier, transition_hash, compact(bound))) == raw(value["dossier_summary"]), "worker_result_refused")
    summary = value["audit_summary"]
    need(type(summary) is dict and set(summary) == {"schema", "fixture_only", "counts", "authority", "source_pins", "result_sha256"}
         and summary["schema"] == prior.audit.SCHEMA and summary["fixture_only"] is False
         and raw(summary["authority"]) == raw(transition.authority())
         and raw(summary["source_pins"]) == raw(transition.expected_input_pins())
         and summary["counts"]["controls"] == 12
         and summary["counts"]["ticker_rows"] == 74150 and summary["counts"]["action_rows"] == 698455,
         "worker_result_refused")
    need(private_dossier["reference_audit_sha256"] == summary["result_sha256"]
         and raw(private_dossier["reference_counts"]) == raw(summary["counts"])
         and raw(private_dossier["reference_source_pins"]) == raw(summary["source_pins"]), "worker_result_refused")
    return value


def run(head):
    install_parent_policy(baseline_policy()); prove_parent()
    guard, epoch, phase = stable.native._WorkerMemoryGuard(), None, "identity"
    result = None
    try:
        bound = identity(head)
        phase = "metadata_discovery"
        discovered = launch("discovery_worker", bound)
        selected_paths(discovered["metadata"])
        profile = policy(bound, metadata=discovered["metadata"], parent=True)
        install_parent_policy(profile); prove_parent(); guard.check()
        phase = "reservation"
        epoch = stable.Epoch(bound, registration())
        epoch.publish("observation-started.json", {"schema": SCHEMA + "/started", "metadata_pin": discovered["metadata_pin"], "authority": transition.authority()})
        phase = "dossier_worker"
        value = launch("dossier_worker", bound, discovered)
        need(identity(head) == bound and value["source_inventory_sha256"] == bound["source_inventory_sha256"]
             and value["current_storage_identity"] == epoch.storage_identity, "identity_refused")
        validate_result(value, bound, discovered["metadata_pin"], epoch.storage_identity)
        phase = "publication"
        epoch.publish("transition.json", value["transition"])
        epoch.publish("dossier.json", value["dossier"])
        final = {"schema": SCHEMA + "/complete", "fixture_only": False, "audit_id": AUDIT_ID,
                 "storage_identity": epoch.storage_identity, "published_leaf_pins": {
                    name: {"bytes": pin["bytes"], "sha256": pin["sha256"]} for name, pin in epoch.pins.items()},
                 "audit_summary": value["audit_summary"], "dossier_summary": value["dossier_summary"],
                 "metadata_pin": value["metadata_pin"], "input_leaves": value["input_leaves"], "authority": transition.authority()}
        complete_hash = epoch.publish("complete.json", final)
        epoch.check(); guard.check()
        result = {"completed": True, "complete_sha256": complete_hash,
                  "transition_sha256": epoch.pins["transition.json"]["sha256"],
                  "dossier_sha256": epoch.pins["dossier.json"]["sha256"],
                  "dossier_summary": value["dossier_summary"], "audit_summary": value["audit_summary"],
                  "authority": transition.authority()}
    except Exception:
        if epoch is not None:
            try: epoch.publish("failure.json", {"schema": SCHEMA + "/failure", "phase": phase, "code": "storage_dossier_refused"})
            except Exception: pass
        raise StorageDossierError("storage_dossier_refused") from None
    finally:
        try:
            if epoch is not None: epoch.close()
        finally:
            guard.close()
    return result


def validate_readback(value, identity_value, complete_hash):
    need(type(value) is dict and set(value) == {"schema", "audit_id", "controls", "pins", "storage_identity"}
         and value["schema"] == stable.SCHEMA + "/readback" and value["audit_id"] == AUDIT_ID
         and type(value["controls"]) is dict and set(value["controls"]) == set(OUTPUT_NAMES)
         and type(value["pins"]) is dict and set(value["pins"]) == set(OUTPUT_NAMES), "readback_refused")
    for name, control in value["controls"].items():
        need(value["pins"][name] == {"bytes": len(raw(control)), "sha256": sha(raw(control))}, "readback_refused")
    need(value["pins"]["complete.json"]["sha256"] == complete_hash, "readback_refused")
    complete = value["controls"]["complete.json"]
    need(type(complete) is dict and set(complete) == {"schema", "fixture_only", "audit_id", "storage_identity",
         "published_leaf_pins", "audit_summary", "dossier_summary", "metadata_pin", "input_leaves", "authority"}
         and complete["schema"] == SCHEMA + "/complete" and complete["authority"] == transition.authority()
         and complete["fixture_only"] is False and complete["audit_id"] == AUDIT_ID
         and raw(complete["storage_identity"]) == raw(value["storage_identity"])
         and complete["published_leaf_pins"] == {name: pin for name, pin in value["pins"].items() if name != "complete.json"}, "readback_refused")
    expected_reservation = {"schema": stable.SCHEMA + "/reservation", "code_identity": identity_value,
        "registration": registration(), "fixture_only": False,
        "storage": {"root_kind": "fixed_user_application_support", "policy": stable.SCHEMA,
            "audit_id": AUDIT_ID, "identity": value["storage_identity"]}}
    need(raw(value["controls"]["reservation.json"]) == raw(expected_reservation)
         and raw(value["controls"]["observation-started.json"]) == raw({"schema": SCHEMA + "/started",
            "metadata_pin": complete["metadata_pin"], "authority": transition.authority()}), "readback_refused")
    validate_result({"completed": True, "transition": value["controls"]["transition.json"],
        "dossier": value["controls"]["dossier.json"], "audit_summary": complete["audit_summary"],
        "dossier_summary": complete["dossier_summary"], "metadata_pin": complete["metadata_pin"],
        "current_storage_identity": value["storage_identity"], "input_leaves": complete["input_leaves"],
        "source_inventory_sha256": identity_value["source_inventory_sha256"]}, identity_value,
        complete["metadata_pin"], value["storage_identity"])
    return complete


def readback_worker(identity_value, complete_hash):
    guard = None
    try:
        stable.native._isolated(); stable.native.source_runner._prove_isolation()
        guard = stable.native._WorkerMemoryGuard(); prior._source_current(compact(identity_value))
        value = stable.read_epoch_controls(AUDIT_ID, OUTPUT_NAMES, {"complete.json": {"bytes": None, "sha256": complete_hash}}, memory=guard)
        validate_readback(value, identity_value, complete_hash)
        _send({"completed": True, "readback_verified": True, "complete_sha256": complete_hash,
               "leaf_count": len(OUTPUT_NAMES), "authority": transition.authority()}, guard)
    finally:
        if guard is not None: guard.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--run", action="store_true")
    choice.add_argument("--health", action="store_true")
    choice.add_argument("--readback-hash")
    args = parser.parse_args()
    try:
        if args.health:
            install_parent_policy(baseline_policy()); prove_parent()
            bound = identity(args.expected_head)
            install_parent_policy(policy(bound, parent=True)); prove_parent()
            value = launch("health_worker", bound)
            need(identity(args.expected_head) == bound, "source_refused")
        elif args.run:
            value = run(args.expected_head)
        else:
            install_parent_policy(baseline_policy()); prove_parent()
            value = launch("readback_worker", identity(args.expected_head), args.readback_hash, readback=True)
        print(raw(value).decode())
    except Exception:
        print('{"completed":false,"code":"storage_dossier_refused"}')
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
