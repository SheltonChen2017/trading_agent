"""Lane-local durable supervisor for an explicitly invoked metadata-only SDK cell.

No browser, account, credential, dataset, SDK instance, History, resolver,
financial/price field, property getter, export, order, outcome or backtest call.
Production APIs require the exact clean committed installation at the fixed
research path. Scope is not consumed until an authenticated Safari observation.

The fixed namespace is one scope for project 37465795, not one scope per run ID.
Claiming consumes it permanently. Failure/unknown execution/kernel reset never
authorizes restarting. Exclusive append-only leaves and held ancestry detect
ordinary concurrent replacement; they cannot defeat deliberate owner deletion
or an administrator rolling back the whole filesystem. Preserve the namespace.

Cell source, invocation source and later control input are distinct lineage:
registration-bindings binds the first two committed images; start-bindings
binds that registration and the inner start; controls then embed receipt bytes;
lineage pins all leaves before any bytes are returned for paste. No self-hash.
Only a later independently observed authenticated, controlled Safari execution
may supply completion. A supplied observation digest is NOT authenticated here.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

LANE_ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying")
LANE_BRANCH = "codex/strategy-insider-buying"
NAMESPACE_PARTS = ("artifacts", "insider_buying", "qc_sdk_metadata_once_v1")
PROFILE = "insider-lean-sdk-type-metadata-only-v1-inactive"
SCOPE = "owned-project-37465795-five-types-four-property-definitions-v1"
PROJECT_ID = 37465795
SOURCE_FILES = (
    "research/insider_buying_qc_sdk_metadata_cell.py",
    "research/insider_buying_qc_sdk_metadata_invocation.py",
    "research/insider_buying_qc_sdk_metadata_supervisor.py",
)
TARGETS = (
    "QuantConnect.Data.Fundamental.Fundamentals",
    "QuantConnect.Data.Fundamental.FundamentalUniverse",
    "QuantConnect.Data.UniverseSelection.BaseDataCollection",
    "QuantConnect.Data.Fundamental.Fundamental",
    "QuantConnect.Data.BaseData",
)
MEMBERS = ("Data", "Time", "EndTime", "Symbol")
PREPARED_FILES = (
    "scope-claim.json", "cell-source.py", "invocation.py", "supervisor-source.py",
    "registration.json", "registration-bindings.json", "start.json",
    "start-bindings.json", "control-input.py", "lineage.json",
)
MAX_SOURCE_BYTES = 256 * 1024
MAX_METADATA_BYTES = 32 * 1024


class SupervisorRefusal(ValueError):
    pass


def _need(condition, code):
    if not condition:
        raise SupervisorRefusal("REFUSED: " + code)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _digest(value):
    _need(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value), "digest-invalid")
    return value


def _utc(value):
    _need(type(value) is str and len(value) <= 40, "timestamp-invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise SupervisorRefusal("REFUSED: timestamp-invalid") from None
    _need(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0,
          "timestamp-not-utc")
    return parsed


def _parse(raw, limit=MAX_METADATA_BYTES):
    _need(type(raw) is bytes and 0 < len(raw) <= limit, "receipt-byte-bound")
    def pairs(items):
        result = {}
        for key, value in items:
            _need(key not in result, "duplicate-receipt-key")
            result[key] = value
        return result
    try:
        result = json.loads(raw, object_pairs_hook=pairs,
                            parse_constant=lambda _: _need(False, "nonfinite-receipt"))
        _need(_raw(result) == raw, "noncanonical-receipt")
    except (UnicodeError, ValueError, RecursionError):
        raise SupervisorRefusal("REFUSED: invalid-canonical-receipt") from None
    return result


def _version(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _directory_identity(info):
    # Own file creation changes directory timestamps, not held inode identity.
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid)


class _HeldDirectories:
    """Hold/recheck every absolute path component, including namespace ancestry."""
    def __init__(self, root):
        _need(root.is_absolute() and root == Path(os.path.normpath(root)), "root-not-normalized")
        self.chain = []
        self.root = root
        self.fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.chain.append((self.fd, None, None, _directory_identity(os.fstat(self.fd))))
        try:
            for name in root.parts[1:]:
                self._descend(name, create=False, private=False)
        except BaseException:
            self.close()
            raise

    def _descend(self, name, *, create, private):
        self.verify()
        parent = self.fd
        if create:
            try:
                os.mkdir(name, mode=0o700, dir_fd=parent)
                os.fsync(parent)
            except FileExistsError:
                pass
        child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        info = os.fstat(child)
        try:
            _need(stat.S_ISDIR(info.st_mode), "non-directory-ancestry")
            if private:
                _need(stat.S_IMODE(info.st_mode) == 0o700 and info.st_uid == os.getuid(),
                      "namespace-not-private-owned-700")
            self.chain.append((child, parent, name, _directory_identity(info)))
            self.fd = child
            self.verify()
        except BaseException:
            if self.fd != child:
                os.close(child)
            raise

    def namespace(self, *, create):
        for index, name in enumerate(NAMESPACE_PARTS):
            self._descend(name, create=create, private=index == len(NAMESPACE_PARTS) - 1)
        return self

    def verify(self):
        for fd, parent, name, expected in self.chain:
            _need(_directory_identity(os.fstat(fd)) == expected, "held-ancestry-changed")
            if parent is not None:
                named = os.stat(name, dir_fd=parent, follow_symlinks=False)
                _need(_directory_identity(named) == expected, "named-ancestry-changed")

    def read(self, name, *, limit=MAX_SOURCE_BYTES, private=True):
        self.verify()
        before = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
        _need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
              and 0 < before.st_size <= limit, "leaf-type-link-or-byte-bound")
        if private:
            _need(stat.S_IMODE(before.st_mode) == 0o600 and before.st_uid == os.getuid(),
                  "leaf-not-private-owned-600")
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        try:
            opened = os.fstat(fd)
            _need(_version(opened) == _version(before), "leaf-replaced-before-open")
            chunks, count = [], 0
            while True:
                chunk = os.read(fd, min(65536, limit + 1 - count))
                if not chunk:
                    break
                chunks.append(chunk)
                count += len(chunk)
                _need(count <= limit, "leaf-read-byte-bound")
            after = os.fstat(fd)
            named = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            _need(_version(before) == _version(after) == _version(named)
                  and count == before.st_size, "leaf-mutated-during-read")
            self.verify()
            return b"".join(chunks)
        finally:
            os.close(fd)

    def write_new(self, name, raw):
        _need(type(raw) is bytes and 0 < len(raw) <= MAX_SOURCE_BYTES, "new-leaf-byte-bound")
        self.verify()
        try:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=self.fd)
        except FileExistsError:
            raise SupervisorRefusal("REFUSED: immutable-leaf-already-exists") from None
        try:
            offset = 0
            while offset < len(raw):
                amount = os.write(fd, raw[offset:])
                _need(amount > 0, "new-leaf-short-write")
                offset += amount
            os.fsync(fd)
            info = os.fstat(fd)
            _need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                  and stat.S_IMODE(info.st_mode) == 0o600 and info.st_uid == os.getuid()
                  and info.st_size == len(raw), "new-leaf-not-private-single-link")
            self.verify()
            named = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            _need(_version(info) == _version(named), "new-leaf-name-replaced")
            os.fsync(self.fd)
        finally:
            os.close(fd)
        _need(self.read(name) == raw, "new-leaf-readback-mismatch")

    def close(self):
        for fd, *_ in reversed(self.chain):
            os.close(fd)
        self.chain = []


@contextmanager
def _held(root, *, create):
    held = None
    try:
        held = _HeldDirectories(root)
        yield held.namespace(create=create)
    except OSError:
        raise SupervisorRefusal("REFUSED: custody-filesystem-operation-failed") from None
    finally:
        if held is not None:
            held.close()


def _git(root, *args):
    try:
        result = subprocess.run(["/usr/bin/git", "--no-optional-locks", "-c", "core.fsmonitor=false", *args], cwd=root,
                                env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"}, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        raise SupervisorRefusal("REFUSED: local-git-operation-failed") from None
    _need(result.returncode == 0 and type(result.stdout) is bytes and len(result.stdout) <= MAX_SOURCE_BYTES,
          "local-git-operation-refused")
    return result.stdout


def _production_gate():
    _need(Path(__file__).absolute() == LANE_ROOT / SOURCE_FILES[2],
          "private-draft-not-activated-at-fixed-production-path")


def _production_identity(expected_head):
    _need(type(expected_head) is str and re.fullmatch(r"[0-9a-f]{40}", expected_head),
          "expected-head-invalid")
    _need(_git(LANE_ROOT, "rev-parse", "--show-toplevel").decode().strip() == str(LANE_ROOT),
          "wrong-worktree-root")
    _need(_git(LANE_ROOT, "branch", "--show-current").decode().strip() == LANE_BRANCH,
          "wrong-lane-branch")
    _need(_git(LANE_ROOT, "rev-parse", "HEAD").decode().strip() == expected_head,
          "unexpected-lane-head")
    _need(_git(LANE_ROOT, "status", "--porcelain=v1", "--untracked-files=normal") == b"",
          "production-source-tree-not-clean")
    sources = []
    for path in SOURCE_FILES:
        with _held_source(LANE_ROOT / path) as source:
            raw = source.read(Path(path).name, private=False)
        _need(_git(LANE_ROOT, "show", expected_head + ":" + path) == raw,
              "current-source-not-exact-committed-bytes")
        sources.append((path, raw))
    return {"git_head": expected_head, "source_inventory": [
        {"path": path, "sha256": _sha(raw), "bytes": len(raw)} for path, raw in sources],
        "fixture_only": False}, [raw for _, raw in sources]


@contextmanager
def _held_source(path):
    held = None
    try:
        held = _HeldDirectories(path.parent)
        yield held
    except OSError:
        raise SupervisorRefusal("REFUSED: source-filesystem-operation-failed") from None
    finally:
        if held is not None:
            held.close()


def _fixture_root(root):
    _need(type(root) is Path or isinstance(root, Path), "fixture-root-type")
    root = root.absolute()
    _need(root == Path(os.path.normpath(root)) and root.exists(), "fixture-root-missing")
    actual, requested = str(LANE_ROOT.resolve()).casefold(), str(root.resolve()).casefold()
    _need(actual != requested and not requested.startswith(actual + "/")
          and not actual.startswith(requested + "/"), "fixture-aliases-real-lane")
    _need(not os.path.samefile(root, LANE_ROOT), "fixture-aliases-real-lane")
    resolved = root.resolve()
    temporary_roots = tuple(Path(name).resolve() for name in ("/private/tmp", "/tmp"))
    _need(any(resolved != temporary and resolved.is_relative_to(temporary)
              for temporary in temporary_roots), "fixture-not-private-temporary-root")
    info = root.lstat()
    _need(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700
          and info.st_uid == os.getuid(), "fixture-not-private-temporary-root")
    # Opening every component with NOFOLLOW also fences symlinked fixture roots.
    with _held_source(root / "unused"):
        pass
    return root


def _fixture_identity(cell_raw, invocation_raw, supervisor_raw):
    sources = (cell_raw, invocation_raw, supervisor_raw)
    _need(all(type(raw) is bytes and 0 < len(raw) <= MAX_SOURCE_BYTES for raw in sources),
          "fixture-source-byte-bound")
    return {"git_head": "0" * 40, "source_inventory": [
        {"path": path, "sha256": _sha(raw), "bytes": len(raw)}
        for path, raw in zip(SOURCE_FILES, sources)], "fixture_only": True}, sources


def _prepare(root, identity, sources, external_observation_sha256, recheck):
    observation = _digest(external_observation_sha256)
    _need(identity["fixture_only"] is True or identity["fixture_only"] is False,
          "identity-fixture-marker-invalid")
    cell_raw, invocation_raw, supervisor_raw = sources
    run_id = "owned-project-37465795-sdk-metadata-v1"
    claim = {"schema": "insider-sdk-metadata-scope-claim-v1", "scope": SCOPE,
        "profile": PROFILE, "project_id": PROJECT_ID, "run_id": run_id,
        "fixture_only": identity["fixture_only"], "claimed_at_utc": datetime.now(timezone.utc).isoformat(),
        "external_authenticated_safari_observation_sha256": observation,
        "external_observation_authenticated_here": False,
        "kernel_reset_or_failure_does_not_restore_scope": True,
        "data_access_permitted": False}
    with _held(root, create=True) as held:
        _need(os.listdir(held.fd) == [], "scope-namespace-already-populated-no-restart")
        # First exclusive leaf permanently consumes this fixed project/scope.
        # An incomplete later write must leave the claim and all custody intact.
        held.write_new("scope-claim.json", _raw(claim))
        held.write_new("cell-source.py", cell_raw)
        held.write_new("invocation.py", invocation_raw)
        held.write_new("supervisor-source.py", supervisor_raw)
        registration = {"schema": "insider-sdk-metadata-preregistration-v1", "profile": PROFILE,
            "run_id": run_id, "project_id": PROJECT_ID, "source_sha256": _sha(cell_raw),
            "registered_at_utc": datetime.now(timezone.utc).isoformat(),
            "allowed_type_names": list(TARGETS), "allowed_member_names": list(MEMBERS),
            "data_access_permitted": False}
        registration_raw = _raw(registration)
        held.write_new("registration.json", registration_raw)
        registration_binding = {"schema": "insider-sdk-metadata-registration-bindings-v1",
            "scope": SCOPE, "scope_claim_sha256": _sha(_raw(claim)),
            "registration_sha256": _sha(registration_raw), "committed_identity": identity,
            "cell_source_sha256": _sha(cell_raw), "invocation_source_sha256": _sha(invocation_raw),
            "source_capture_precedes_paste": True}
        held.write_new("registration-bindings.json", _raw(registration_binding))
        start = {"schema": "insider-sdk-metadata-start-v1", "profile": PROFILE,
            "run_id": run_id, "registration_sha256": _sha(registration_raw),
            "source_sha256": _sha(cell_raw), "started_at_utc": datetime.now(timezone.utc).isoformat()}
        start_raw = _raw(start)
        held.write_new("start.json", start_raw)
        start_binding = {"schema": "insider-sdk-metadata-start-bindings-v1", "scope": SCOPE,
            "start_sha256": _sha(start_raw),
            "registration_bindings_sha256": _sha(_raw(registration_binding)),
            "cell_source_sha256": _sha(cell_raw), "invocation_source_sha256": _sha(invocation_raw),
            "start_is_consumed_before_any_paste": True}
        held.write_new("start-bindings.json", _raw(start_binding))
        control = {"registration_raw": registration_raw,
            "registration_sha256": _sha(registration_raw), "start_raw": start_raw,
            "start_sha256": _sha(start_raw), "execution_source_sha256": _sha(cell_raw)}
        # Receipt bytes are canonical ASCII with no secrets. repr(bytes) is a
        # literal input cell, not serialization of arbitrary reflection errors.
        control_raw = ("# INACTIVE; external start already consumed. Do not repeat.\n"
                       "_SDK_METADATA_CONTROL = " + repr(control) + "\n").encode("ascii")
        held.write_new("control-input.py", control_raw)
        leaves = {name: _sha(held.read(name)) for name in PREPARED_FILES[:-1]}
        lineage = {"schema": "insider-sdk-metadata-prepaste-lineage-v1", "scope": SCOPE,
            "project_id": PROJECT_ID, "fixture_only": identity["fixture_only"],
            "leaves_sha256": leaves,
            "lineage_is_not_a_notebook_execution_or_account_authentication": True}
        held.write_new("lineage.json", _raw(lineage))
        recheck()
        _verify_prepared(held, identity["fixture_only"], _sha(_raw(lineage)))
        held.verify()
    return {"namespace": str(root.joinpath(*NAMESPACE_PARTS)), "scope": SCOPE,
        "fixture_only": identity["fixture_only"], "lineage_sha256": _sha(_raw(lineage)),
        "cell_source_sha256": _sha(cell_raw), "invocation_source_sha256": _sha(invocation_raw),
        "registration_sha256": _sha(registration_raw), "start_sha256": _sha(start_raw),
        "paste_order": ["cell-source.py", "control-input.py", "invocation.py"],
        "hosted_execution_performed": False, "backtest_ready": False}


def _verify_prepared(held, fixture_only, expected_lineage_sha256):
    _need(set(os.listdir(held.fd)) <= set(PREPARED_FILES) | {
          "metadata-observation.json", "completion.json"}, "unexpected-scope-namespace-leaf")
    lineage_raw = held.read("lineage.json")
    _need(_sha(lineage_raw) == _digest(expected_lineage_sha256), "expected-lineage-hash-mismatch")
    lineage = _parse(lineage_raw)
    _need(type(lineage) is dict and set(lineage) == {
        "schema", "scope", "project_id", "fixture_only", "leaves_sha256",
        "lineage_is_not_a_notebook_execution_or_account_authentication"}
        and lineage["schema"] == "insider-sdk-metadata-prepaste-lineage-v1"
        and lineage["scope"] == SCOPE and type(lineage["project_id"]) is int
        and lineage["project_id"] == PROJECT_ID and lineage["fixture_only"] is fixture_only
        and lineage["lineage_is_not_a_notebook_execution_or_account_authentication"] is True,
        "prepaste-lineage-schema")
    leaves = lineage["leaves_sha256"]
    _need(type(leaves) is dict and set(leaves) == set(PREPARED_FILES[:-1]), "prepaste-leaf-roster")
    captured = {name: held.read(name) for name in PREPARED_FILES[:-1]}
    _need(all(_sha(raw) == _digest(leaves[name]) for name, raw in captured.items()),
          "immutable-prepaste-leaf-mismatch")
    # Consistency checks are not authentication of an external notebook.
    claim = _parse(captured["scope-claim.json"])
    _need(type(claim) is dict and set(claim) == {"schema", "scope", "profile", "project_id", "run_id",
          "fixture_only", "claimed_at_utc", "external_authenticated_safari_observation_sha256",
          "external_observation_authenticated_here", "kernel_reset_or_failure_does_not_restore_scope",
          "data_access_permitted"} and claim["schema"] == "insider-sdk-metadata-scope-claim-v1"
          and claim["scope"] == SCOPE and claim["profile"] == PROFILE
          and type(claim["project_id"]) is int and claim["project_id"] == PROJECT_ID
          and claim["run_id"] == "owned-project-37465795-sdk-metadata-v1"
          and claim["fixture_only"] is fixture_only and claim["data_access_permitted"] is False
          and claim["external_observation_authenticated_here"] is False
          and claim["kernel_reset_or_failure_does_not_restore_scope"] is True, "scope-claim-binding")
    _digest(claim["external_authenticated_safari_observation_sha256"])
    registration = _parse(captured["registration.json"])
    start = _parse(captured["start.json"])
    rb = _parse(captured["registration-bindings.json"])
    sb = _parse(captured["start-bindings.json"])
    _need(type(registration) is dict and set(registration) == {"schema", "profile", "run_id", "project_id",
          "source_sha256", "registered_at_utc", "allowed_type_names", "allowed_member_names", "data_access_permitted"}
          and registration["schema"] == "insider-sdk-metadata-preregistration-v1"
          and registration["profile"] == PROFILE and registration["run_id"] == claim["run_id"]
          and type(registration["project_id"]) is int and registration["project_id"] == PROJECT_ID
          and registration["allowed_type_names"] == list(TARGETS)
          and registration["allowed_member_names"] == list(MEMBERS)
          and registration["data_access_permitted"] is False, "inner-registration-schema")
    _need(type(start) is dict and set(start) == {"schema", "profile", "run_id", "registration_sha256",
          "source_sha256", "started_at_utc"} and start["schema"] == "insider-sdk-metadata-start-v1"
          and start["profile"] == PROFILE and start["run_id"] == claim["run_id"], "inner-start-schema")
    _need(_utc(claim["claimed_at_utc"]) <= _utc(registration["registered_at_utc"])
          <= _utc(start["started_at_utc"]) <= datetime.now(timezone.utc), "durable-receipt-chronology")
    _need(type(rb) is dict and set(rb) == {"schema", "scope", "scope_claim_sha256", "registration_sha256",
          "committed_identity", "cell_source_sha256", "invocation_source_sha256", "source_capture_precedes_paste"}
          and rb["schema"] == "insider-sdk-metadata-registration-bindings-v1" and rb["scope"] == SCOPE
          and rb["source_capture_precedes_paste"] is True, "registration-bindings-schema")
    _need(type(sb) is dict and set(sb) == {"schema", "scope", "start_sha256", "registration_bindings_sha256",
          "cell_source_sha256", "invocation_source_sha256", "start_is_consumed_before_any_paste"}
          and sb["schema"] == "insider-sdk-metadata-start-bindings-v1" and sb["scope"] == SCOPE
          and sb["start_is_consumed_before_any_paste"] is True, "start-bindings-schema")
    identity = rb["committed_identity"]
    _need(type(identity) is dict and set(identity) == {"git_head", "source_inventory", "fixture_only"}
          and type(identity["git_head"]) is str and re.fullmatch(r"[0-9a-f]{40}", identity["git_head"])
          and identity["fixture_only"] is fixture_only, "committed-identity-schema")
    inventory = identity["source_inventory"]
    _need(type(inventory) is list and len(inventory) == len(SOURCE_FILES), "committed-source-roster")
    for path, leaf, row in zip(SOURCE_FILES, ("cell-source.py", "invocation.py", "supervisor-source.py"), inventory):
        _need(type(row) is dict and set(row) == {"path", "sha256", "bytes"} and row["path"] == path
              and row["sha256"] == _sha(captured[leaf]) and type(row["bytes"]) is int
              and row["bytes"] == len(captured[leaf]), "committed-source-capture-mismatch")
    _need(rb["scope_claim_sha256"] == _sha(captured["scope-claim.json"])
          and rb["registration_sha256"] == _sha(captured["registration.json"])
          and rb["cell_source_sha256"] == sb["cell_source_sha256"] == _sha(captured["cell-source.py"])
          and rb["invocation_source_sha256"] == sb["invocation_source_sha256"] == _sha(captured["invocation.py"])
          and sb["registration_bindings_sha256"] == _sha(captured["registration-bindings.json"])
          and sb["start_sha256"] == _sha(captured["start.json"])
          and start["registration_sha256"] == _sha(captured["registration.json"])
          and registration["source_sha256"] == start["source_sha256"] == _sha(captured["cell-source.py"]),
          "registration-start-source-invocation-lineage")
    return lineage_raw, captured, registration, start


def prepare_once(*, expected_head, authenticated_safari_observation_sha256):
    """Future fixed-path production API. Never automates or performs the paste."""
    _production_gate()
    identity, sources = _production_identity(expected_head)
    def recheck():
        _need(_production_identity(expected_head) == (identity, sources), "source-changed-after-start")
    return _prepare(LANE_ROOT, identity, sources, authenticated_safari_observation_sha256, recheck)


def prepare_invented(*, fixture_root, cell_raw, invocation_raw, supervisor_raw):
    """Temp-only proof. Explicitly fixture provenance, never authenticates host."""
    root = _fixture_root(fixture_root)
    identity, sources = _fixture_identity(cell_raw, invocation_raw, supervisor_raw)
    return _prepare(root, identity, sources, "f" * 64, lambda: None)


def _type_name(value):
    _need(type(value) is str and 0 < len(value) <= 256
          and re.fullmatch(r"(?:QuantConnect|System)\.[A-Za-z0-9_.+`]+", value),
          "output-type-name-not-public-metadata")


def _shape(value):
    _need(type(value) is dict and set(value) == {"type_name", "generic_argument_names"},
          "output-type-shape-schema")
    _type_name(value["type_name"])
    args = value["generic_argument_names"]
    _need(type(args) is list and len(args) <= 4, "output-generic-argument-bound")
    for arg in args:
        _type_name(arg)


def _validate_metadata(raw, *, fixture_only, captured, registration, start):
    output = _parse(raw)
    false_fields = {"source_identity_verified_here", "durable_registration_authenticated_here",
        "owner_account_verified_here", "history_return_shape_observed", "dataset_access_observed",
        "fundamental_instance_data_read", "financial_values_read", "market_prices_read",
        "platform_engine_build_observed", "backtest_ready"}
    keys = false_fields | {"schema", "profile", "run_id", "registration_sha256", "start_sha256",
        "declared_execution_source_sha256", "fixture_only", "observed_at_utc", "classes",
        "qc_backtests", "research_outcome_looks"}
    _need(type(output) is dict and set(output) == keys, "output-exact-schema")
    _need(output["schema"] == "insider-lean-sdk-type-metadata-observation-v1"
          and output["profile"] == PROFILE and output["run_id"] == registration["run_id"]
          and output["registration_sha256"] == _sha(captured["registration.json"])
          and output["start_sha256"] == _sha(captured["start.json"])
          and output["declared_execution_source_sha256"] == _sha(captured["cell-source.py"])
          and output["fixture_only"] is fixture_only, "output-source-run-binding")
    _need(all(output[key] is False for key in false_fields)
          and all(type(output[key]) is int and output[key] == 0
                  for key in ("qc_backtests", "research_outcome_looks")), "output-must-not-promote-authority")
    _need(_utc(start["started_at_utc"]) <= _utc(output["observed_at_utc"])
          <= datetime.now(timezone.utc), "output-observation-chronology")
    classes = output["classes"]
    _need(type(classes) is list and len(classes) == len(TARGETS), "output-type-roster-bound")
    for expected, item in zip(TARGETS, classes):
        _need(type(item) is dict and set(item) == {"requested_type", "available", "metadata"}
              and item["requested_type"] == expected and type(item["available"]) is bool,
              "output-class-schema-or-order")
        if not item["available"]:
            _need(item["metadata"] is None, "output-unavailable-type-has-metadata")
            continue
        metadata = item["metadata"]
        _need(type(metadata) is dict and set(metadata) == {"type_name", "base_type", "assembly_name",
              "assembly_version", "properties", "interfaces"} and metadata["type_name"] == expected
              and metadata["assembly_name"] == "QuantConnect.Common"
              and type(metadata["assembly_version"]) is str
              and re.fullmatch(r"[0-9]{1,5}(?:\.[0-9]{1,5}){1,3}", metadata["assembly_version"]),
              "output-class-metadata-schema")
        if metadata["base_type"] is not None:
            _shape(metadata["base_type"])
        interfaces = metadata["interfaces"]
        _need(type(interfaces) is list and len(interfaces) <= 32, "output-interface-bound")
        for interface in interfaces:
            _shape(interface)
        properties = metadata["properties"]
        _need(type(properties) is list and len(properties) == len(MEMBERS), "output-property-roster")
        for member, prop in zip(MEMBERS, properties):
            _need(type(prop) is dict and set(prop) == {"name", "available", "type", "declaring_type",
                  "can_read", "can_write"} and prop["name"] == member
                  and type(prop["available"]) is bool, "output-property-schema-or-order")
            if prop["available"]:
                _shape(prop["type"])
                _type_name(prop["declaring_type"])
                _need(type(prop["can_read"]) is bool and type(prop["can_write"]) is bool,
                      "output-property-boolean-types")
            else:
                _need(all(prop[key] is None for key in ("type", "declaring_type", "can_read", "can_write")),
                      "output-missing-property-values")
    return output


def _complete(root, output_raw, external_execution_observation_sha256, fixture_only,
              expected_lineage_sha256, recheck):
    observation = _digest(external_execution_observation_sha256)
    with _held(root, create=False) as held:
        # Existing claim is the lock; no lock creation/restart on completion.
        lock = os.open("scope-claim.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=held.fd)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            lock_version = _version(os.fstat(lock))
            prepared_versions = {name: _version(os.stat(name, dir_fd=held.fd, follow_symlinks=False))
                                 for name in PREPARED_FILES}
            lineage_raw, captured, registration, start = _verify_prepared(held, fixture_only, expected_lineage_sha256)
            _need(set(os.listdir(held.fd)) == set(PREPARED_FILES), "immutable-leaf-already-exists")
            prepared_raw = {**captured, "lineage.json": lineage_raw}
            terminal = {}
            def check_custody():
                held.verify()
                _need(_version(os.fstat(lock)) == lock_version
                      == _version(os.stat("scope-claim.json", dir_fd=held.fd, follow_symlinks=False)),
                      "scope-lock-name-or-version-replaced")
                _need(set(os.listdir(held.fd)) == set(PREPARED_FILES) | set(terminal),
                      "completion-namespace-not-exact")
                for name, version in prepared_versions.items():
                    _need(_version(os.stat(name, dir_fd=held.fd, follow_symlinks=False)) == version
                          and held.read(name) == prepared_raw[name], "prepared-leaf-changed-during-completion")
                for name, (version, expected_raw) in terminal.items():
                    _need(_version(os.stat(name, dir_fd=held.fd, follow_symlinks=False)) == version
                          and held.read(name, limit=MAX_METADATA_BYTES) == expected_raw,
                          "terminal-leaf-changed-during-completion")
                held.verify()
            def publish_terminal(name, expected_raw):
                check_custody()
                held.write_new(name, expected_raw)
                version = _version(os.stat(name, dir_fd=held.fd, follow_symlinks=False))
                _need(held.read(name, limit=MAX_METADATA_BYTES) == expected_raw
                      and _version(os.stat(name, dir_fd=held.fd, follow_symlinks=False)) == version,
                      "terminal-leaf-publication-changed")
                terminal[name] = (version, expected_raw)
                check_custody()
            check_custody()
            _validate_metadata(output_raw, fixture_only=fixture_only, captured=captured,
                               registration=registration, start=start)
            recheck()
            check_custody()
            # Invalid observation consumes no new completion leaves; scope was
            # already consumed before any paste. Unknown execution stays unknown.
            publish_terminal("metadata-observation.json", output_raw)
            completion = {"schema": "insider-sdk-metadata-completion-v1", "scope": SCOPE,
                "project_id": PROJECT_ID, "fixture_only": fixture_only,
                "prepaste_lineage_sha256": _sha(lineage_raw),
                "metadata_observation_sha256": _sha(output_raw),
                "external_controlled_safari_execution_observation_sha256": observation,
                "external_execution_authenticated_here": False,
                "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                "dataset_or_history_shape_verified": False, "actual_account_data_entitlement_verified": False,
                "platform_engine_build_verified": False, "backtest_ready": False}
            completion_raw = _raw(completion)
            publish_terminal("completion.json", completion_raw)
            _verify_prepared(held, fixture_only, expected_lineage_sha256)
            check_custody()
            recheck()
            check_custody()
            return {"completion_sha256": _sha(completion_raw), "metadata_sha256": _sha(output_raw),
                    "fixture_only": fixture_only, "scope_consumed": True, "backtest_ready": False}
        except BlockingIOError:
            raise SupervisorRefusal("REFUSED: scope-completion-already-locked") from None
        finally:
            os.close(lock)


def complete_once(*, expected_head, metadata_raw, controlled_safari_execution_observation_sha256,
                  expected_lineage_sha256):
    _production_gate()
    identity, _ = _production_identity(expected_head)
    with _held(LANE_ROOT, create=False) as held:
        _, captured, _, _ = _verify_prepared(held, False, expected_lineage_sha256)
        binding = _parse(captured["registration-bindings.json"])
        _need(binding["committed_identity"] == identity, "completion-current-committed-identity-differs")
    def recheck():
        _need(_production_identity(expected_head)[0] == identity, "source-changed-during-completion")
    return _complete(LANE_ROOT, metadata_raw, controlled_safari_execution_observation_sha256, False,
                     expected_lineage_sha256, recheck)


def complete_invented(*, fixture_root, metadata_raw, expected_lineage_sha256):
    root = _fixture_root(fixture_root)
    return _complete(root, metadata_raw, "e" * 64, True, expected_lineage_sha256, lambda: None)

