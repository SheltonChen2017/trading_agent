"""Read-only custody/schema replay of the consumed three-profile Massive probe.

The historical producer's Git images and the current verifier are separate
identities. Current pure schema helpers revalidate opaque retained bytes; this
is neither executed historical code nor a replay of the unavailable API key's
privacy screen. No provider, credential, acquisition or QC operation exists.
Only the native worker opens actual retained inputs. Its private IPC identity
is discarded after trusted-parent Git verification; the public receipt has
only counts, digests and explicit false authority flags.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import pwd
import re
import selectors
import signal
import stat
import subprocess
import sys
import time

from research import insider_buying_pilot_massive_evidence_probe_v2 as producer
from research import insider_buying_sec_feed_archive_format_v3 as native

prior, custody, publication = producer.prior, producer.prior.custody, producer.prior.publication
LANE_ROOT, LANE_BRANCH = producer.LANE_ROOT, producer.LANE_BRANCH
SELF_PATH = "research/insider_buying_pilot_massive_evidence_readback_v1.py"
TEST_PATH = "tests/test_insider_buying_pilot_massive_evidence_readback_v1.py"
SCHEMA = "insider-pilot-massive-evidence-retained-readback-v1"
PRODUCER_HEAD = "78a048e3eaf3f93f1888f3d35c46b02e85c8eae2"
PRODUCER_INVENTORY = "150a108bb20abb9360146bae09144dcc5619d127a4c3440a7d216be438330299"
COMPLETE_SHA256 = "1a6d8e8ea61cd0cd2e9af752c0ba8ff405bf8c937a8f0554c3e8ce343e083b06"
EMPTY_CACHE_PREFIX = native.EMPTY_CACHE_PREFIX
MAX_CONTROL = producer.MAX_CONTROL_BYTES
WORKER_SECONDS = 90
CLEANUP_SECONDS = 2
OBSERVED_TOTAL_BYTES = 2355
_raw, _sha = producer._raw, producer._sha
_CODES = frozenset({"arguments_refused", "controls_refused", "retained_custody_refused",
                    "producer_identity_refused", "projection_refused", "current_source_refused", "native_refused",
                    "native_sandbox_launch_refused", "native_child_process_refused", "native_child_ipc_refused",
                    "native_child_deadline"})
_NAMES = frozenset({"reservation.json", "credential-read-started.json", "credential-read-completed.json", "complete.json"}
    | {f"{i:02d}-{part}.json" for i in range(1, 4) for part in ("started", "response", "metadata", "completed")})


class MassiveReadbackError(ValueError):
    """Finite refusals; supplied values and OS exceptions never cross IPC."""


def _need(ok, code):
    if not ok:
        raise MassiveReadbackError(code)


def _safe(error):
    return str(error) if type(error) is MassiveReadbackError and str(error) in _CODES else "native_refused"


def _same(left, right):
    _need(_raw(left) == _raw(right), "controls_refused")


def _decode(raw):
    _need(type(raw) is bytes and 0 < len(raw) <= MAX_CONTROL, "controls_refused")
    try:
        return publication._json(raw)
    except Exception:
        raise MassiveReadbackError("controls_refused") from None


def _project(raw, ordinal):
    """Current strict schema revalidation, deliberately WITHOUT key screening."""
    _need(type(raw) is bytes and 0 < len(raw) <= producer.MAX_BODY_BYTES
          and type(ordinal) is int and 1 <= ordinal <= 3, "projection_refused")
    try:
        body = prior._json(raw)
        producer._structure(body)
        _need(type(body) is dict and {"results", "status", "request_id"} <= set(body)
              and set(body) <= {"results", "status", "request_id", "count", "next_url"}
              and type(body["status"]) is str and body["status"] == "OK"
              and producer._text(body["request_id"]) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", body["request_id"])
              and type(body["results"]) is list and len(body["results"]) == 1, "projection_refused")
        if "count" in body:
            _need(type(body["count"]) is prior._IntegerLexeme and body["count"] == "1", "projection_refused")
        cursor = body.get("next_url")
        if cursor is not None:
            _need(producer._text(cursor), "projection_refused")
            parsed = producer._split(cursor, "cursor_origin_refused")
            expected = producer.parse.urlsplit(producer.REQUESTS[ordinal - 1][1])
            _need(parsed.scheme == "https" and parsed.netloc == "api.massive.com" and parsed.path == expected.path
                  and not parsed.fragment and bool(parsed.query), "projection_refused")
        kind = producer.REQUESTS[ordinal - 1][0]
        row = body["results"][0]
        identity = producer._reference(row) if kind == "reference" else producer._filing(row, kind)
        return {"schema": producer.SCHEMA + "/metadata", "ordinal": ordinal, "kind": kind,
            "result_count": 1, "has_unfollowed_next_page": cursor is not None,
            "response_field_names": sorted(body), "row_field_names": sorted(row), "source_identity": identity,
            "response_body_sha256": _sha(raw), "response_body_bytes": len(raw),
            "numeric_financial_fields_interpreted": False, **dict.fromkeys(producer.FALSE_FLAGS, False)}
    except Exception:
        raise MassiveReadbackError("projection_refused") from None


class _Held:
    """No-follow ancestry and immutable private leaf versions, without writes."""
    def __init__(self, root):
        self.chains, self.pins, self.names = [], [], []
        try:
            for parts, names in ((producer.OUTPUT_PARTS, {"scope-reservation.json", producer.AUDIT_ID}),
                                 ((*producer.OUTPUT_PARTS, producer.AUDIT_ID), set(_NAMES))):
                chain = custody._Chain(root, parts)
                self.chains.append(chain)
                info = os.fstat(chain.fd)
                _need(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700,
                      "retained_custody_refused")
                _need(set(os.listdir(chain.fd)) == names, "retained_custody_refused")
                self.names.append(set(names))
        except BaseException:
            self.close()
            raise

    def read(self, index, name):
        chain = self.chains[index]
        chain.recheck()
        raw, version = publication._leaf(chain.fd, name, MAX_CONTROL)
        self.pins.append((chain, name, version, _sha(raw)))
        chain.recheck()
        return raw

    def recheck(self):
        for chain, names in zip(self.chains, self.names):
            chain.recheck()
            _need(set(os.listdir(chain.fd)) == names, "retained_custody_refused")
        for chain, name, version, digest in self.pins:
            raw, latest = publication._leaf(chain.fd, name, MAX_CONTROL)
            _need(latest == version and _sha(raw) == digest, "retained_custody_refused")
        for chain, names in zip(self.chains, self.names):
            chain.recheck()
            _need(set(os.listdir(chain.fd)) == names, "retained_custody_refused")

    def close(self):
        primary, failed = sys.exc_info()[0] is not None, False
        for chain in reversed(self.chains):
            try:
                chain.close()
            except BaseException:
                failed = True
        self.chains = []
        if failed and not primary:
            raise MassiveReadbackError("retained_custody_refused") from None


def _receipt(identity, complete_sha256, fixture, total):
    return {"schema": SCHEMA, "fixture_only": fixture, "complete_sha256": complete_sha256,
            "producer_head": identity["head"], "producer_source_inventory_sha256": identity["source_inventory_sha256"],
            "private_leaves_revalidated": 17, "producer_journal_transport_invocations": 3,
            "producer_journal_credential_reads": 1, "retained_success_bodies": 3,
            "retained_success_body_bytes": total, "current_key_privacy_rescreened": False,
            "original_key_privacy_screen_reexecuted": False, "historical_code_executed": False, "source_financial_values_interpreted": False,
            "new_requests": 0, "credential_reads": 0, "research_looks": 0, "qc_jobs": 0, "outcome_looks": 0, "backtests": 0,
            **dict.fromkeys(producer.FALSE_FLAGS, False)}


def _readback(root, complete_sha256, *, fixture):
    """Internal private result: producer identity must NEVER be printed."""
    held = None
    try:
        _need(type(complete_sha256) is str and re.fullmatch(r"[0-9a-f]{64}", complete_sha256), "arguments_refused")
        if fixture:
            _need(prior._outside_lane(root) and root.is_absolute() and root.resolve() == root, "arguments_refused")
            prior.date_probe._fixture_denial()
        else:
            _need(root == LANE_ROOT and complete_sha256 == COMPLETE_SHA256, "arguments_refused")
        held = _Held(root)
        raw = held.read(1, "complete.json")
        _need(_sha(raw) == complete_sha256, "controls_refused")
        final = _decode(raw)
        _need(final.get("fixture_only") is fixture, "controls_refused")
        identity = final.get("identity")
        _need(type(identity) is dict and type(identity.get("head")) is str, "producer_identity_refused")
        prior._validate_identity(identity, identity["head"] if fixture else PRODUCER_HEAD, root)
        if not fixture:
            _need(len(identity["source_sha256"]) == 50 and identity["source_inventory_sha256"] == PRODUCER_INVENTORY
                  and {producer.SELF_PATH, prior.SELF_PATH} <= set(identity["source_sha256"]), "producer_identity_refused")
        scope_raw = held.read(0, "scope-reservation.json")
        _same(_decode(scope_raw), {"schema": producer.SCHEMA, "audit_id": producer.AUDIT_ID, "profile": producer.PROFILE,
            "requests": producer._profiles(), "maximum_attempts": 3})
        raws = {name: held.read(1, name) for name in sorted(_NAMES - {"complete.json"})}
        pins = {name: _sha(value) for name, value in raws.items()}
        _same(_decode(raws["reservation.json"]), producer._reservation(identity, fixture))
        _same(_decode(raws["credential-read-started.json"]), {"schema": producer.SCHEMA, "maximum_credential_reads": 1,
            "reservation_sha256": pins["reservation.json"]})
        _same(_decode(raws["credential-read-completed.json"]), {"schema": producer.SCHEMA, "fixture_only": fixture,
            "started_sha256": pins["credential-read-started.json"], "credential_read_observed": True,
            "disposition": "configured-keychain-credential-read"})
        rows, total = [], 0
        for ordinal in range(1, 4):
            prefix = f"{ordinal:02d}"
            _same(_decode(raws[prefix + "-started.json"]), producer._started(ordinal, pins["reservation.json"]))
            body = raws[prefix + "-response.json"]
            metadata = _project(body, ordinal)
            _same(_decode(raws[prefix + "-metadata.json"]), metadata)
            row = {"schema": producer.SCHEMA, "ordinal": ordinal, "http_status": 200,
                "started_sha256": pins[prefix + "-started.json"], "disposition": "capability_metadata_observed",
                "metadata": metadata, "body_sha256": _sha(body), "body_size_bytes": len(body),
                "untrusted_error_body_hashed_or_retained": False}
            _same(_decode(raws[prefix + "-completed.json"]), row)
            rows.append(row)
            total += len(body)
        stamp = final.get("completed_at_utc")
        _need(type(stamp) is str and stamp.endswith("Z") and prior.datetime.fromisoformat(stamp.replace("Z", "+00:00")).utcoffset().total_seconds() == 0,
              "controls_refused")
        _same(final, {"schema": producer.SCHEMA, "audit_id": producer.AUDIT_ID, "profile": producer.PROFILE,
            "owner_direction": producer.OWNER_DIRECTION, "completed_at_utc": stamp, "fixture_only": fixture,
            "identity": identity, "planned_requests": 3, "credential_read_observed": True, "transport_invocation_count": 3,
            "unattempted_requests": 0, "status": "completed-capability-probe", "disposition": "capability_metadata_observed",
            "results": rows, "published_leaf_sha256": pins, "scope_reservation_sha256": _sha(scope_raw),
            "source_financial_values_interpreted": False, "research_looks": 0, "qc_jobs": 0, "backtests": 0,
            **dict.fromkeys(producer.FALSE_FLAGS, False)})
        held.recheck()
        receipt = _receipt(identity, complete_sha256, fixture, total)
        return {"producer_identity": identity, "receipt": receipt}
    except MassiveReadbackError:
        raise
    except Exception:
        raise MassiveReadbackError("retained_custody_refused") from None
    finally:
        if held is not None:
            held.close()


def read_invented(root, *, complete_sha256):
    """Invented outside-lane inputs only; requires native test denial."""
    return _readback(Path(root), complete_sha256, fixture=True)["receipt"]


def _current(identity):
    try:
        prior._validate_identity(identity, identity["head"], LANE_ROOT)
        _need({SELF_PATH, TEST_PATH} <= set(identity["source_sha256"]), "current_source_refused")
        _need(custody._source_bytes(LANE_ROOT, tuple(identity["source_sha256"])) == identity["source_sha256"]
              and set(custody._internal_source_paths(LANE_ROOT)) <= set(identity["source_sha256"]), "current_source_refused")
    except Exception:
        raise MassiveReadbackError("current_source_refused") from None


def _identity(expected_head):
    _need(type(expected_head) is str and re.fullmatch(r"[0-9a-f]{40}", expected_head)
          and Path(__file__).resolve() == LANE_ROOT / SELF_PATH, "arguments_refused")
    native._isolated()
    value = custody._identity(expected_head)
    own = custody._source_bytes(LANE_ROOT, (SELF_PATH, TEST_PATH))
    for name, digest in own.items():
        _need(_sha(custody._git(LANE_ROOT, "show", expected_head + ":" + name)) == digest, "current_source_refused")
    sources = {**value["source_sha256"], **own}
    value = {**value, "source_sha256": sources, "source_inventory_sha256": _sha(_raw(sources))}
    _current(value)
    return value


def _health(identity):
    return {"schema": SCHEMA + "/runtime-health", "readback_head": identity["head"],
        "readback_source_inventory_sha256": identity["source_inventory_sha256"],
        "readback_source_images": len(identity["source_sha256"]), "retained_inputs_opened": False,
        "native_network_fork_allwrite_securityexec_denial": True, "memory_guard_live_through_stdout": True,
        "new_requests": 0, "credential_reads": 0, "research_looks": 0, "qc_jobs": 0, "outcome_looks": 0, "backtests": 0,
        **dict.fromkeys(producer.FALSE_FLAGS, False)}


def _worker(identity, *, role="readback"):
    guard = None
    try:
        _need(type(role) is str and role in {"health", "readback"}, "arguments_refused")
        native._isolated()
        native.batch.campaign.base._prove_isolation()
        guard = native._WorkerMemoryGuard()
        _current(identity)
        value = _health(identity) if role == "health" else _readback(LANE_ROOT, COMPLETE_SHA256, fixture=False)
        result = {"ok": True, "value": value}
        _current(identity)
        guard.check()
    except Exception as error:
        result = {"ok": False, "code": _safe(error)}
    try:
        wire = _raw(result)
        _need(len(wire) <= MAX_CONTROL, "native_refused")
        _need(guard is not None, "native_refused")
        guard.check()
        sys.stdout.buffer.write(wire + b"\n")
        sys.stdout.buffer.flush()
        guard.check()
    finally:
        if guard is not None:
            guard.close()


def _command(identity, *, role="readback"):
    _need(type(role) is str and role in {"health", "readback"}, "arguments_refused")
    code = "import sys,json;sys.path.insert(0," + repr(str(LANE_ROOT)) + ");from research import insider_buying_pilot_massive_evidence_readback_v1 as m;identity=json.loads(" + repr(_raw(identity).decode()) + ");\ntry:m._worker(identity,role=" + repr(role) + ")\nexcept Exception as error:sys.stdout.buffer.write(m._raw({'ok':False,'code':m._safe(error)})+b'\\n');sys.stdout.buffer.flush();sys.exit(2)"
    policy = '(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    if role == "health":
        for private in (LANE_ROOT / "artifacts", Path(pwd.getpwuid(os.geteuid()).pw_dir) / "Library" / "Keychains"):
            policy += "(deny file-read* (subpath " + json.dumps(str(private)) + "))"
    return ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "/usr/bin/sandbox-exec", "-p", policy,
        sys.executable, "-I", "-S", "-B", "-X", "pycache_prefix=" + EMPTY_CACHE_PREFIX, "-c", code)


def _result_value(result):
    _need(type(result) is dict and type(result.get("ok")) is bool, "native_child_ipc_refused")
    if result["ok"] is False:
        _need(set(result) == {"ok", "code"} and type(result["code"]) is str and result["code"] in _CODES,
              "native_child_ipc_refused")
        raise MassiveReadbackError(result["code"])
    _need(set(result) == {"ok", "value"}, "native_child_ipc_refused")
    return result["value"]


def _child_result(stdout, stderr, exit_code):
    _need(type(stdout) is bytes and len(stdout) <= MAX_CONTROL + 1 and type(stderr) is bytes
          and len(stderr) <= 4096 and type(exit_code) is int, "native_child_ipc_refused")
    # Exact SOURCE-ONLY reproduction signature. Never relabel earlier generic
    # receipts as having measured this exit code or this stderr.
    if exit_code == 71 and stdout == b"" and stderr == b"sandbox-exec: sandbox_apply: Operation not permitted\n":
        raise MassiveReadbackError("native_sandbox_launch_refused")
    _need(exit_code in {0, 2} and not stderr, "native_child_process_refused")
    _need(stdout.endswith(b"\n"), "native_child_ipc_refused")
    try:
        result = _decode(stdout[:-1])
    except Exception:
        raise MassiveReadbackError("native_child_ipc_refused") from None
    _need(exit_code == 0 or result.get("ok") is False, "native_child_process_refused")
    _result_value(result)  # Validate even refused worker messages before return.
    return result


def _cleanup(process, poll, *, failed):
    """Bounded reap/close-all; even an exited leader may have pipe holders."""
    clean = True
    if process is not None:
        try:
            if failed or process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except Exception:
            clean = False
        try:
            process.wait(timeout=CLEANUP_SECONDS)
        except Exception:
            clean = False
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    clean = False
    if poll is not None:
        try:
            poll.close()
        except Exception:
            clean = False
    return clean


def _launch(command):
    """Bounded protected IPC, without a fallback launcher or weaker fence."""
    process = poll = None
    accepted = False
    try:
        process = subprocess.Popen(command, cwd=LANE_ROOT, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        poll = selectors.DefaultSelector()
        output, errors = bytearray(), bytearray()
        for stream, sink in ((process.stdout, output), (process.stderr, errors)):
            os.set_blocking(stream.fileno(), False)
            poll.register(stream, selectors.EVENT_READ, sink)
        deadline = time.monotonic() + WORKER_SECONDS
        while poll.get_map():
            remaining = deadline - time.monotonic()
            _need(remaining > 0, "native_child_deadline")
            for key, _ in poll.select(min(0.2, remaining)):
                cap = 4096 if key.data is errors else MAX_CONTROL + 1
                chunk = os.read(key.fileobj.fileno(), min(65536, cap + 1 - len(key.data)))
                if chunk:
                    key.data.extend(chunk)
                    _need(len(key.data) <= cap, "native_child_ipc_refused")
                else:
                    poll.unregister(key.fileobj)
        code = process.wait(timeout=max(0.001, deadline - time.monotonic()))
        result = _child_result(bytes(output), bytes(errors), code)
        accepted = True
        return result
    except MassiveReadbackError:
        raise
    except subprocess.TimeoutExpired:
        raise MassiveReadbackError("native_child_deadline") from None
    except Exception:
        raise MassiveReadbackError("native_child_process_refused") from None
    finally:
        primary = sys.exc_info()[0] is not None
        cleaned = _cleanup(process, poll, failed=not accepted)
        _need(cleaned or primary, "native_child_process_refused")


def preflight_actual(*, expected_head):
    """SOURCE ONLY: run BEFORE a caller claims any new diagnostic namespace.

    Health proves launch/isolation/current-code/IPC mechanics, not permission
    to repeat a consumed scope or to read any retained input. The trusted
    source-only orchestrator must let the fixed child install its full fence;
    a nested sandbox rejection is preserved, never bypassed.
    """
    try:
        identity = _identity(expected_head)
        value = _result_value(_launch(_command(identity, role="health")))
        _same(value, _health(identity))
        _same(_identity(expected_head), identity)
        return value
    except MassiveReadbackError:
        raise
    except Exception:
        raise MassiveReadbackError("native_refused") from None


def verify_actual(*, expected_head):
    """Trusted parent verifies old Git images; actual private identity stays IPC."""
    try:
        identity = _identity(expected_head)
        value = _result_value(_launch(_command(identity)))
        _need(type(value) is dict and set(value) == {"producer_identity", "receipt"}, "native_refused")
        old = value["producer_identity"]
        prior._validate_identity(old, PRODUCER_HEAD, LANE_ROOT)
        _need(len(old["source_sha256"]) == 50 and old["source_inventory_sha256"] == PRODUCER_INVENTORY,
              "producer_identity_refused")
        for name, digest in old["source_sha256"].items():
            _need(_sha(custody._git(LANE_ROOT, "show", PRODUCER_HEAD + ":" + name)) == digest,
                  "producer_identity_refused")
        receipt = value["receipt"]
        _same(receipt, _receipt(old, COMPLETE_SHA256, False, OBSERVED_TOTAL_BYTES))
        _same(_identity(expected_head), identity)
        return {**receipt, "readback_head": expected_head, "readback_source_inventory_sha256": identity["source_inventory_sha256"],
            "readback_source_images": len(identity["source_sha256"]), "native_network_fork_allwrite_securityexec_denial": True}
    except MassiveReadbackError:
        raise
    except Exception:
        raise MassiveReadbackError("native_refused") from None
