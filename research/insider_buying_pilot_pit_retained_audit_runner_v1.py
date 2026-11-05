"""Read-only, fixed-input PIT evidence audit. No acquisition or output epoch.

The existing reference projections are metadata, not contemporaneous snapshots.
Only sanitized counts/digests leave the native worker. No retained filing body,
fundamental value, provider credential, account or QC interface is accessed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

from research import insider_buying_pilot_stable_custody_v2 as stable
from research import insider_buying_sharadar_reference_cohort as reference
from research import insider_buying_pilot_pit_retained_audit_v1 as audit

ROOT, BRANCH = stable.LANE_ROOT, stable.LANE_BRANCH
SELF = "research/insider_buying_pilot_pit_retained_audit_runner_v1.py"
OWN = (SELF, "research/insider_buying_pilot_pit_retained_audit_v1.py",
       "tests/test_insider_buying_pilot_pit_retained_audit_runner_v1.py",
       "tests/test_insider_buying_pilot_pit_retained_audit_v1.py")
PROVIDER = stable.PRIVATE_CUSTODY_ROOT / "ib-fmp-eod-stable-qualification-v2-20261103-once"
PROOF = stable.PRIVATE_CUSTODY_ROOT / "ib-local-custody-v2-20261103-once"
SHARADAR = ROOT / "artifacts/insider_buying/sharadar_reference_cohort/ib-sharadar-cohort-2006q1-compact-v2-20261014-once"
MANIFEST = "94251ffdf0529b118ff331b98c4a144d97bc734380d7e7333f94045e4aa6f09b"
PINS = {
    "provider_complete": {"bytes": 70190, "sha256": "f52646ad80a2a7497f9eb56d471987d8041ac744600b194e5e9ea99c6684a552"},
    "proof_complete": {"bytes": 23187, "sha256": "e801524572f54c9c7415798386b5c579f66b35fcc46eb7a9b9e57aa977ad81b3"},
    "reference_complete": {"bytes": 7985, "sha256": "07dd203d82c3d90f90e1af239b8ef2255ecba47400595d6f415a65989ee29f97"},
    "tickers_projection": {"bytes": 29841795, "sha256": "da2bf31da6436127dd405154b339d1a31ad6c14a788d0017ce620ad5217aea60"},
    "actions_projection": {"bytes": 116139300, "sha256": "27387a32fffe710e7733b8f8b225250fc92ad3d829d720efc77df77a015c5246"},
}
FILES = {PROVIDER: ("complete.json", "controls.json", "storage-qualification.json"),
         PROOF: ("complete.json",),
         SHARADAR: ("complete.json", "tickers_projection.json", "actions_projection.json")}
MAX_INPUT = 256 * 1024 * 1024
MAX_OUTPUT = 64 * 1024
SCHEMA = "insider-pilot-pit-retained-audit-runner-v1"
PHASES = frozenset({"native", "sources", "open_provider", "open_proof", "open_reference",
    "provider_complete", "proof_complete", "provider_controls", "provider_storage", "storage_binding",
    "reference_complete", "derive", "final_inputs", "final_sources", "serialization"})
SAFE_FAILURE_CODES = frozenset({"retained_identity_audit_refused", "input_pin_refused", "input_json_refused",
    "input_root_refused", "input_name_refused", "input_leaf_refused", "input_changed", "input_cleanup_refused",
    "projection_refused", "storage_identity_refused", "source_refused", "reference_completion_refused",
    "controls_refused", "output_refused", "worker_result_refused", "input_refused", "authority_refused",
    "count_refused", "pin_refused", "provider_refused", "control_evidence_missing", "row_schema_refused",
    "row_limit_refused", "arguments_refused", "control_refused", "accounting_refused", "genuine_result_required", "unknown"})


class AuditRunnerError(ValueError):
    """Finite own refusal only; never serialize source or exception text."""


class ReportedAuditRefusal(AuditRunnerError):
    def __init__(self, diagnostic):
        need(type(diagnostic) is dict and set(diagnostic) == {"completed", "read_only", "phase", "failure_class", "os_errno", "refusal_code"}
             and diagnostic["completed"] is False and diagnostic["read_only"] is True
             and diagnostic["phase"] in PHASES | {"unknown"}
             and diagnostic["failure_class"] in {"audit_control", "audit_metadata", "custody", "os_error", "other"}
             and diagnostic["refusal_code"] in SAFE_FAILURE_CODES
             and (diagnostic["os_errno"] is None or type(diagnostic["os_errno"]) is int
                  and 0 <= diagnostic["os_errno"] <= 255), "failure_diagnostic_refused")
        self.diagnostic = dict(diagnostic)
        super().__init__("retained_identity_audit_refused")


def failure_info(phase, error):
    category = ("audit_control" if isinstance(error, AuditRunnerError) else
                "audit_metadata" if isinstance(error, audit.PitRetainedAuditError) else
                "custody" if isinstance(error, stable.CustodyError) else
                "os_error" if isinstance(error, OSError) else "other")
    number = error.errno if isinstance(error, OSError) else None
    if type(number) is not int or not 0 <= number <= 255:
        number = None
    code = str(error) if type(error) in {AuditRunnerError, audit.PitRetainedAuditError} else "unknown"
    return {"completed": False, "read_only": True, "phase": phase if phase in PHASES else "unknown",
            "failure_class": category, "os_errno": number,
            "refusal_code": code if code in SAFE_FAILURE_CODES else "unknown"}


def need(value, code="retained_identity_audit_refused"):
    if not value:
        raise AuditRunnerError(code)


def raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def decode(data, pin):
    need(type(data) is bytes and type(pin) is dict and set(pin) == {"bytes", "sha256"}
         and type(pin["bytes"]) is int and 0 < pin["bytes"] <= MAX_INPUT
         and len(data) == pin["bytes"] and type(pin["sha256"]) is str
         and re.fullmatch(r"[0-9a-f]{64}", pin["sha256"])
         and hashlib.sha256(data).hexdigest() == pin["sha256"], "input_pin_refused")
    def pairs(items):
        value = {}
        for key, child in items:
            need(key not in value, "input_json_refused")
            value[key] = child
        return value
    try:
        value = json.loads(data, object_pairs_hook=pairs,
                           parse_constant=lambda _: need(False, "input_json_refused"))
        need(type(value) is dict and raw(value) == data, "input_json_refused")
        return value
    except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, OverflowError):
        raise AuditRunnerError("input_json_refused") from None


def version(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_uid,
            info.st_gid, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_flags)


class Held:
    def __init__(self, root, *, fixture=False):
        root = Path(root)
        need(root.is_absolute() and root.resolve() == root, "input_root_refused")
        if fixture:
            need(root.is_relative_to(Path(tempfile.gettempdir()).resolve()), "input_root_refused")
            forbidden = (ROOT, stable.PRIVATE_CUSTODY_ROOT, *FILES)
            identities = {(p.stat().st_dev, p.stat().st_ino) for p in forbidden if p.exists()}
            need(all((p.stat().st_dev, p.stat().st_ino) not in identities
                     for p in (root, *root.parents)), "input_root_refused")
        else:
            need(root in FILES, "input_root_refused")
        self.chain = stable._HeldChain(root, ())
        self.leaves = {}
        try:
            stable._private_directory(self.chain)
        except BaseException:
            self.close()
            raise

    def read(self, name, pin, *, check):
        need(type(name) is str and re.fullmatch(r"[a-z][a-z0-9_.-]{0,99}", name), "input_name_refused")
        need(type(pin) is dict and set(pin) == {"bytes", "sha256"}
             and type(pin["bytes"]) is int and 0 < pin["bytes"] <= MAX_INPUT
             and type(pin["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", pin["sha256"]), "input_pin_refused")
        if name not in self.leaves:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.chain.fd)
            try:
                info = os.fstat(fd)
                need(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
                     and info.st_uid == os.geteuid() and info.st_nlink == 1
                     and info.st_size == pin["bytes"], "input_leaf_refused")
                self.leaves[name] = (fd, version(info), dict(pin))
            except BaseException:
                os.close(fd)
                raise
        fd, initial, previous = self.leaves[name]
        need(previous == pin, "input_pin_refused")
        parts, offset = [], 0
        while offset < pin["bytes"]:
            check()
            data = os.pread(fd, min(1024 * 1024, pin["bytes"] - offset), offset)
            need(bool(data), "input_leaf_refused")
            parts.append(data)
            offset += len(data)
        data = b"".join(parts)
        need(hashlib.sha256(data).hexdigest() == pin["sha256"], "input_pin_refused")
        self.check(check=check)
        return data

    def check(self, *, check):
        self.chain.recheck()
        for name, (fd, initial, pin) in self.leaves.items():
            check()
            need(version(os.fstat(fd)) == initial == version(os.stat(
                name, dir_fd=self.chain.fd, follow_symlinks=False)), "input_changed")
            digest, offset = hashlib.sha256(), 0
            while offset < pin["bytes"]:
                check()
                data = os.pread(fd, min(1024 * 1024, pin["bytes"] - offset), offset)
                need(bool(data), "input_changed")
                digest.update(data)
                offset += len(data)
            need(digest.hexdigest() == pin["sha256"] and version(os.fstat(fd)) == initial
                 == version(os.stat(name, dir_fd=self.chain.fd, follow_symlinks=False)),
                 "input_changed")
        self.chain.recheck()

    def close(self):
        primary, failed = sys.exc_info()[0] is not None, False
        for fd, _info, _pin in self.leaves.values():
            try:
                os.close(fd)
            except OSError:
                failed = True
        self.leaves = {}
        try:
            self.chain.close()
        except OSError:
            failed = True
        need(primary or not failed, "input_cleanup_refused")


def projection(held, name, pin, *, columns, schema, count, check):
    body = decode(held.read(name, pin, check=check), pin)
    need(set(body) == {"schema", "capture_manifest_sha256", "archive_sha256", "member_sha256", "columns", "rows"}
         and body["schema"] == schema and body["columns"] == list(columns)
         and body["capture_manifest_sha256"] == MANIFEST
         and all(type(body[k]) is str and re.fullmatch(r"[0-9a-f]{64}", body[k])
                 for k in ("archive_sha256", "member_sha256"))
         and type(body["rows"]) is list and len(body["rows"]) == count, "projection_refused")
    for ordinal, row in enumerate(body["rows"], 1):
        if ordinal % 512 == 0:
            check()
        need(type(row) is dict and set(row) == {"source_row_ordinal", *columns}
             and type(row["source_row_ordinal"]) is int and row["source_row_ordinal"] == ordinal
             and all(reference._safe_text(row[k], allow_name_controls=k in {"name", "contraname"})
                     for k in columns), "projection_refused")
        yield row
    held.check(check=check)


def fixed_input_paths():
    return tuple(root / name for root, names in FILES.items() for name in names)


def storage_binding(physical, proof, qualification):
    keys = {"schema", "root_kind", "device", "inode", "mode", "owner", "group"}
    need(type(physical) is dict and set(physical) == keys
         and physical["schema"] == stable.SCHEMA + "/storage-identity"
         and physical["root_kind"] == "fixed_user_application_support"
         and all(type(physical[k]) is int and physical[k] >= 0
                 for k in ("device", "inode", "mode", "owner", "group"))
         and physical["inode"] > 0 and physical["mode"] == 0o700
         and physical["owner"] == os.geteuid(), "storage_identity_refused")
    need(type(proof) is dict and type(qualification) is dict
         and proof.get("passed") is qualification.get("passed") is True
         and proof.get("fixture_only") is qualification.get("fixture_only") is False
         and raw(physical) == raw(proof.get("storage_identity"))
         == raw(qualification.get("storage_identity"))
         and qualification.get("receipt_sha256") == PINS["proof_complete"]["sha256"],
         "storage_identity_refused")


def _identity(head):
    need(type(head) is str and re.fullmatch(r"[0-9a-f]{40}", head), "source_refused")
    def git(*args):
        return subprocess.check_output(["git", "--no-optional-locks", *args], cwd=ROOT,
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}, stderr=subprocess.DEVNULL).decode().strip()
    need(Path.cwd().resolve() == ROOT and git("rev-parse", "--show-toplevel") == str(ROOT)
         and git("branch", "--show-current") == BRANCH and git("rev-parse", "HEAD") == head
         and not git("status", "--porcelain"), "source_refused")
    paths = set(OWN)
    for module in tuple(sys.modules.values()):
        location = getattr(module, "__file__", None)
        if type(location) is str and Path(location).is_relative_to(ROOT):
            p = Path(location)
            if p.suffix == ".py":
                paths.add(p.relative_to(ROOT).as_posix())
    sources = {}
    for path in sorted(paths):
        data = (ROOT / path).read_bytes()
        blob = subprocess.check_output(["git", "--no-optional-locks", "show", head + ":" + path],
            cwd=ROOT, env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}, stderr=subprocess.DEVNULL)
        need(data == blob, "source_refused")
        sources[path] = hashlib.sha256(data).hexdigest()
    return {"head": head, "sources": sources, "source_inventory_sha256": hashlib.sha256(raw(sources)).hexdigest()}


def _source_current(identity):
    need(type(identity) is dict and set(identity) == {"head", "sources", "source_inventory_sha256"}
         and set(OWN) <= set(identity["sources"])
         and hashlib.sha256(raw(identity["sources"])).hexdigest() == identity["source_inventory_sha256"], "source_refused")
    for name, digest in identity["sources"].items():
        need(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, "source_refused")


def policy(python=None, *, sources=()):
    executable = Path(python or sys.executable).resolve()
    targets = [executable]
    relaunch = executable.parents[1] / "Resources/Python.app/Contents/MacOS/Python"
    if relaunch.is_file():
        targets.append(relaunch.resolve())
    q = lambda p: json.dumps(str(p))
    answer = "(version 1)(allow default)(deny network*)(deny process-fork)(deny process-exec)(deny file-write*)(deny file-read-data)"
    answer += "".join("(allow process-exec (literal " + q(p) + "))" for p in targets)
    need(all(type(name) is str and name.endswith(".py") and ".." not in Path(name).parts
             and not Path(name).is_absolute() and Path(name).as_posix() == name
             and Path(name).parts[0] != "artifacts"
             for name in sources), "source_refused")
    directories = (Path("/System/Library"), Path("/usr/lib"), Path("/usr/share"),
                   Path("/private/var/db/dyld"), Path(sys.base_prefix).resolve(),
                   Path(sys.executable).parent.parent.resolve(), Path("/usr/share/zoneinfo").resolve())
    leaves = (*fixed_input_paths(), *(ROOT / name for name in sources), *targets,
              Path("/dev/null"), Path("/dev/urandom"), Path("/dev/random"),
              Path("/etc/localtime"), Path("/private/etc/localtime"))
    # Dynamic standard-library extensions use these separately installed
    # runtime libraries. Permit exact existing images, not Homebrew as DATA.
    runtime = ("openssl@3/lib/libssl.3.dylib", "openssl@3/lib/libcrypto.3.dylib",
               "xz/lib/liblzma.5.dylib", "sqlite/lib/libsqlite3.0.dylib",
               "gettext/lib/libintl.8.dylib", "readline/lib/libreadline.8.dylib",
               "zstd/lib/libzstd.1.dylib", "mpdecimal/lib/libmpdec.4.dylib")
    runtime_leaves = []
    for relative in runtime:
        path = Path("/opt/homebrew/opt") / relative
        if path.is_file():
            runtime_leaves.extend((path, path.resolve()))
    leaves = (*leaves, *runtime_leaves)
    # Python startup and held no-follow directory traversal open directory FDs.
    # Exact ancestor literals permit that without allowing neighboring DATA.
    ancestors = {Path("/")}
    for path in (*leaves, *directories):
        ancestors.update(path.parents)
    answer += "(allow file-read-data " + " ".join("(subpath " + q(p) + ")" for p in directories)
    answer += " " + " ".join("(literal " + q(p) + ")" for p in (*leaves, *sorted(ancestors))) + ")"
    return answer


def worker(identity):
    guard, holders, phase = None, [], "native"
    try:
        stable.native._isolated()
        stable.native.batch.campaign.base._prove_isolation()
        guard = stable.native._WorkerMemoryGuard()
        phase = "sources"
        _source_current(identity)
        phase = "open_provider"
        provider = Held(PROVIDER); holders.append(provider)
        phase = "open_proof"
        proof = Held(PROOF); holders.append(proof)
        phase = "open_reference"
        refs = Held(SHARADAR); holders.append(refs)
        phase = "provider_complete"
        complete = decode(provider.read("complete.json", PINS["provider_complete"], check=guard.check), PINS["provider_complete"])
        phase = "proof_complete"
        old_proof = decode(proof.read("complete.json", PINS["proof_complete"], check=guard.check), PINS["proof_complete"])
        named = complete["published_leaf_pins"]
        controls_pin, storage_pin = named["controls.json"], named["storage-qualification.json"]
        phase = "provider_controls"
        controls = decode(provider.read("controls.json", controls_pin, check=guard.check), controls_pin)
        phase = "provider_storage"
        storage = decode(provider.read("storage-qualification.json", storage_pin, check=guard.check), storage_pin)
        phase = "storage_binding"
        root_hold = stable._HeldChain(stable.PRIVATE_CUSTODY_ROOT, ())
        try:
            stable._managed(root_hold)
            physical = stable._storage_identity(root_hold, fixture=False)
            storage_binding(physical, old_proof, storage)
        finally:
            root_hold.close()
        phase = "reference_complete"
        receipt = decode(refs.read("complete.json", PINS["reference_complete"], check=guard.check), PINS["reference_complete"])
        need(receipt["capture_manifest_sha256"] == MANIFEST
             and receipt["tickers_projection_sha256"] == PINS["tickers_projection"]["sha256"]
             and receipt["actions_projection_sha256"] == PINS["actions_projection"]["sha256"]
             and receipt["fixture_only"] is False and receipt["financial_values_interpreted"] is False,
             "reference_completion_refused")
        need(controls["fixture_only"] is False and len(controls["cases"]) == 12, "controls_refused")
        sources = {**PINS, "provider_controls": controls_pin, "provider_storage": storage_pin}
        phase = "derive"
        value = audit.build_audit(controls["cases"], complete,
            projection(refs, "tickers_projection.json", PINS["tickers_projection"],
                columns=reference.TICKER_COLUMNS, schema=reference.TICKERS_SCHEMA, count=74150, check=guard.check),
            projection(refs, "actions_projection.json", PINS["actions_projection"],
                columns=reference.ACTION_COLUMNS, schema=reference.ACTIONS_SCHEMA, count=698455, check=guard.check),
            sources, check=guard.check, fixture_only=False)
        answer = audit.public_summary(value)
        phase = "final_inputs"
        for held in holders:
            held.check(check=guard.check)
        phase = "final_sources"
        _source_current(identity)
        guard.check()
        answer.update(execution_head=identity["head"], source_inventory_sha256=identity["source_inventory_sha256"],
                      source_images=len(identity["sources"]), actual_input_leaves=sum(len(h.leaves) for h in holders),
                      read_only=True, completed=True, new_requests=0, credential_reads=0, qc_accesses=0)
        phase = "serialization"
        wire = raw({"ok": True, "value": answer}) + b"\n"
        need(len(wire) <= MAX_OUTPUT, "output_refused")
        sys.stdout.buffer.write(wire); sys.stdout.buffer.flush(); guard.check()
    except Exception as error:
        # A successful IPC transfer is distinct from a failed semantic audit.
        # Preserve finite phase/class metadata without any supplied exception text.
        sys.stdout.buffer.write(raw({"ok": True, "value": failure_info(phase, error)}) + b"\n")
        sys.stdout.buffer.flush()
    finally:
        primary = sys.exc_info()[0] is not None
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
        if failed and not primary:
            raise SystemExit(2)


def run_actual(head):
    identity = _identity(head)
    code = ("import sys;sys.path.insert(0," + repr(str(ROOT)) + ");"
            "from research import insider_buying_pilot_pit_retained_audit_runner_v1 as m;m.worker(" + repr(identity) + ")")
    command = ("/usr/bin/sandbox-exec", "-p", policy(sources=identity["sources"]), sys.executable, "-I", "-S", "-B", "-X",
               "pycache_prefix=" + stable.native.EMPTY_CACHE_PREFIX, "-c", code)
    try:
        value = stable.source._launch(command, timeout=180)
        need(_identity(head) == identity, "source_refused")
        if value.get("completed") is False:
            raise ReportedAuditRefusal(value)
        need(value.get("completed") is True, "worker_result_refused")
        return value
    except ReportedAuditRefusal:
        raise
    except Exception:
        raise AuditRunnerError("retained_identity_audit_refused") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    args = parser.parse_args()
    try:
        print(raw(run_actual(args.expected_head)).decode())
    except ReportedAuditRefusal as error:
        print(raw({"code": "retained_identity_audit_refused", **error.diagnostic}).decode())
        raise SystemExit(2) from None
    except Exception:
        print('{"code":"retained_identity_audit_refused","read_only":true}')
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
