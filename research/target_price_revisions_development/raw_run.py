"""Private one-look admission for the separately frozen raw-revision candidate.

No import opens inputs. A hash-bound rights manifest is a required input, not
independent proof of its underlying agreement. No production manifest, bundle,
claim or run is created by implementing this controller. Local owner-only files
are not signed external custody and cannot prevent rollback by their owner.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import uuid

CANDIDATE_ID = "TPR-DEV-RAWREV-v1"
LANE_ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__target_price_revisions")
LANE_BRANCH = "codex/strategy-target-price-revisions"
PRODUCTION_ROOT = LANE_ROOT / "artifacts" / "target_price_raw_revision" / CANDIDATE_ID
CODE_FILES = ("raw_candidate.py", "raw_revision.py", "raw_backtest.py", "raw_run.py")
MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_RIGHTS_BYTES = 65536
CONFIG = {"candidate_id": CANDIDATE_ID, "start_date": "2025-01-02", "end_date": "2025-03-31",
    "view": "censored", "development_looks": 1, "order_based": True,
    "personal_only": True, "quantconnect": False, "canonical_admission": False, "trading": False}
_STRUCTURE_KEYS = {"schema", "capture_utc", "calendar", "ratings", "identities", "actions", "action_inventory_complete"}
_RATING_KEYS = {"benzinga_id", "benzinga_firm_id", "ticker", "date", "last_updated", "currency",
    "price_target_action", "price_target", "previous_price_target"}
_IDENTITY_KEYS = {"ticker", "security_id", "permaticker", "figi", "category", "exchange", "isdelisted"}
_ACTION_KEYS = {"ticker", "date", "action"}
_CALENDAR_KEYS = {"session_date", "open_utc", "close_utc"}
_RIGHTS_DATASETS = ("Massive:Benzinga ratings", "Sharadar:TICKERS", "Sharadar:SEP", "Sharadar:ACTIONS")


class RawRunError(ValueError):
    """Fixed refusal strings contain no source rows, secrets or account values."""


class _ReservationFailure(RawRunError):
    def __init__(self, interrupted: bool):
        super().__init__("run reservation incomplete; candidate remains spent")
        self.interrupted = interrupted


def _canonical(body: dict) -> bytes:
    try:
        return (json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False) + "\n").encode("ascii")
    except (ValueError, TypeError, RecursionError):
        raise RawRunError("invalid run JSON") from None


def _unique(pairs):
    body = {}
    for key, value in pairs:
        if key in body:
            raise RawRunError("duplicate run JSON key")
        body[key] = value
    return body


def _no_number(_value):
    raise RawRunError("noninteger JSON number refused")


def _decode(payload: bytes, limit: int) -> dict:
    if type(payload) is not bytes or not 0 < len(payload) <= limit:
        raise RawRunError("invalid run JSON size")
    try:
        body = json.loads(payload.decode("ascii"), object_pairs_hook=_unique,
            parse_float=_no_number, parse_constant=_no_number)
        if type(body) is not dict or _canonical(body) != payload:
            raise RawRunError("noncanonical run JSON refused")
        return body
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise RawRunError("invalid canonical run JSON") from None


def _hash(value: object) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise RawRunError("invalid run content identity")
    return value


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _clock(value: object) -> datetime:
    if type(value) is not str or not 1 <= len(value) <= 64:
        raise RawRunError("invalid run UTC clock")
    try:
        clock = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if clock.tzinfo is None or clock.utcoffset() != timedelta(0):
            raise ValueError
        return clock.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise RawRunError("invalid run UTC clock") from None


def freeze_run_spec(*, structure_sha256: str, outcomes_sha256: str, rights_sha256: str,
                    code_hashes: dict, created_utc: str, expires_utc: str,
                    mode: str = "production") -> bytes:
    """Bind reviewed input identities before outcomes; no file is opened here."""
    for value in (structure_sha256, outcomes_sha256, rights_sha256):
        _hash(value)
    if type(code_hashes) is not dict or set(code_hashes) != set(CODE_FILES):
        raise RawRunError("invalid candidate code inventory")
    for value in code_hashes.values():
        _hash(value)
    if type(mode) is not str or mode not in ("production", "offline-fixture"):
        raise RawRunError("invalid run mode")
    created, expires = _clock(created_utc), _clock(expires_utc)
    if not created < expires <= created + timedelta(hours=48):
        raise RawRunError("invalid run expiry")
    return _canonical({"schema": "tpr-raw-run-spec-v1", "candidate_id": CANDIDATE_ID, "mode": mode,
        "structure_sha256": structure_sha256, "outcomes_sha256": outcomes_sha256, "rights_sha256": rights_sha256,
        "code_hashes": dict(code_hashes), "config": dict(CONFIG), "config_sha256": _digest(_canonical(CONFIG)),
        "created_utc": created.isoformat(), "expires_utc": expires.isoformat(),
        "lane_root": str(LANE_ROOT), "lane_branch": LANE_BRANCH,
        "input_files": ["rights.json", "structure.json", "outcomes.json"],
        "structure_max_bytes": MAX_INPUT_BYTES, "outcomes_max_bytes": MAX_INPUT_BYTES,
        "rights_max_bytes": MAX_RIGHTS_BYTES, "canonical_custody": False})


def _spec(payload: bytes) -> dict:
    body = _decode(payload, MAX_RIGHTS_BYTES)
    try:
        expected = freeze_run_spec(structure_sha256=body["structure_sha256"], outcomes_sha256=body["outcomes_sha256"],
            rights_sha256=body["rights_sha256"], code_hashes=body["code_hashes"], created_utc=body["created_utc"],
            expires_utc=body["expires_utc"], mode=body["mode"])
    except (KeyError, TypeError):
        raise RawRunError("invalid run spec policy") from None
    if payload != expected:
        raise RawRunError("run spec differs from fixed candidate policy")
    return body


def _verify_lane() -> None:
    try:
        if Path.cwd() != LANE_ROOT or Path.cwd().resolve() != LANE_ROOT:
            raise RawRunError("run requires the designated physical lane")
        values = [subprocess.run(command, cwd=LANE_ROOT, capture_output=True, check=True, timeout=5).stdout.decode("ascii").strip()
            for command in (["git", "rev-parse", "--show-toplevel"], ["git", "branch", "--show-current"])]
        if values != [str(LANE_ROOT), LANE_BRANCH]:
            raise RawRunError("run lane identity mismatch")
    except (OSError, UnicodeError, subprocess.SubprocessError):
        raise RawRunError("run lane identity unavailable") from None


def _open_root(root: Path, mode: str) -> int:
    if type(root) is not type(LANE_ROOT) or not root.is_absolute() or root.resolve() != root:
        raise RawRunError("invalid private run root")
    if (mode == "production" and root != PRODUCTION_ROOT) or (mode == "offline-fixture" and root == PRODUCTION_ROOT):
        raise RawRunError("run root and mode disagree")
    descriptor = None
    try:
        descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        for part in root.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        metadata = os.fstat(descriptor)
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
            raise RawRunError("private run root requires owner-only custody")
        result, descriptor = descriptor, None
        return result
    except OSError:
        raise RawRunError("private run root unavailable") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _read_file(directory_fd: int, name: str, limit: int, expected: str) -> bytes:
    descriptor = None
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                or stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1 or not 0 < before.st_size <= limit):
            raise RawRunError("invalid private input custody or size")
        parts, remaining = [], before.st_size
        while remaining:
            piece = os.read(descriptor, min(remaining, 65536))
            if not piece:
                raise RawRunError("private input changed while reading")
            parts.append(piece)
            remaining -= len(piece)
        after = os.fstat(descriptor)
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise RawRunError("private input changed while reading")
        payload = b"".join(parts)
        if _digest(payload) != expected:
            raise RawRunError("private input identity mismatch")
        return payload
    except OSError:
        raise RawRunError("private input unavailable") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _verify_code(hashes: dict) -> None:
    root = LANE_ROOT / "research" / "target_price_revisions_development"
    for name in CODE_FILES:
        path = root / name
        if path.resolve() != path:
            raise RawRunError("candidate code custody mismatch")
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                metadata = os.fstat(descriptor)
                if not stat.S_ISREG(metadata.st_mode) or not 0 < metadata.st_size <= 1024 * 1024:
                    raise RawRunError("candidate code identity mismatch")
                payload = os.read(descriptor, metadata.st_size)
                if len(payload) != metadata.st_size or _digest(payload) != hashes[name]:
                    raise RawRunError("candidate code identity mismatch")
            finally:
                os.close(descriptor)
        except OSError:
            raise RawRunError("candidate code unavailable") from None


def _rights(body: dict) -> None:
    required = {"schema", "candidate_id", "personal_only", "quantconnect", "grants"}
    if (set(body) != required or body["schema"] != "tpr-raw-rights-v1" or body["candidate_id"] != CANDIDATE_ID
            or body["personal_only"] is not True or body["quantconnect"] is not False):
        raise RawRunError("inapplicable exact source rights")
    grants = body["grants"]
    if type(grants) is not list or len(grants) != len(_RIGHTS_DATASETS):
        raise RawRunError("incomplete source-rights inventory")
    observed = []
    for grant in grants:
        if (type(grant) is not dict or set(grant) != {"provider_dataset", "local_retention", "derived_processing",
                "evidence_sha256", "evidence_classification"}
                or type(grant["provider_dataset"]) is not str
                or grant["local_retention"] is not True or grant["derived_processing"] is not True):
            raise RawRunError("inapplicable source-rights grant")
        _hash(grant["evidence_sha256"])
        classifications = ("account-specific-agreement", "written-vendor-clarification")
        if grant["provider_dataset"].startswith("Sharadar:"):
            classifications += ("vendor-published-terms",)
        if type(grant["evidence_classification"]) is not str or grant["evidence_classification"] not in classifications:
            raise RawRunError("insufficient agreement applicability evidence")
        observed.append(grant["provider_dataset"])
    if sorted(observed) != sorted(_RIGHTS_DATASETS):
        raise RawRunError("incomplete source-rights inventory")


def _date(value: object) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise RawRunError("invalid structural date")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise RawRunError("invalid structural date") from None
    if not "2024-08-01" <= value <= "2025-03-31":
        raise RawRunError("structure outside frozen warmup or evaluation dates")
    return value


def _structure(body: dict) -> None:
    if set(body) != _STRUCTURE_KEYS or body["schema"] != "tpr-raw-structure-v1" or type(body["action_inventory_complete"]) is not bool:
        raise RawRunError("invalid structure framing")
    _clock(body["capture_utc"])
    for name, keys, maximum in (("ratings", _RATING_KEYS, 100000), ("identities", _IDENTITY_KEYS, 4096),
            ("actions", _ACTION_KEYS, 4096), ("calendar", _CALENDAR_KEYS, 256)):
        rows = body[name]
        if type(rows) is not list or len(rows) > maximum:
            raise RawRunError("invalid bounded structural rows")
        for row in rows:
            if type(row) is not dict or set(row) != keys:
                raise RawRunError("invalid flat structural row schema")
            for value in row.values():
                if not (value is None or type(value) is bool or type(value) is int and value.bit_length() <= 128
                        or type(value) is str and len(value) <= 256):
                    raise RawRunError("invalid structural primitive")
            if name in ("ratings", "actions"):
                _date(row["date"])
            if name == "calendar":
                _date(row["session_date"])
                if _clock(row["open_utc"]) >= _clock(row["close_utc"]):
                    raise RawRunError("invalid calendar clock order")
    if not body["calendar"]:
        raise RawRunError("structural calendar unavailable")


def _write(descriptor: int, payload: bytes) -> None:
    remaining = memoryview(payload)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise RawRunError("incomplete immutable run write")
        remaining = remaining[written:]
    os.fsync(descriptor)


def _reserve(directory_fd: int, spec: dict, spec_sha256: str, started: str) -> None:
    payload = _canonical({"schema": "tpr-raw-run-reservation-v1", "candidate_id": CANDIDATE_ID,
        "spec_sha256": spec_sha256, "started_utc": started, "code_hashes": spec["code_hashes"],
        "structure_sha256": spec["structure_sha256"], "outcomes_sha256": spec["outcomes_sha256"],
        "rights_sha256": spec["rights_sha256"], "config_sha256": spec["config_sha256"],
        "config": spec["config"], "mode": spec["mode"],
        "development_look_reserved": 1 if spec["mode"] == "production" else 0,
        "fixture_runs": 1 if spec["mode"] == "offline-fixture" else 0})
    try:
        descriptor = os.open(CANDIDATE_ID + ".spent.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=directory_fd)
    except FileExistsError:
        raise RawRunError("candidate already spent") from None
    except OSError:
        raise RawRunError("run reservation unavailable") from None
    try:
        _write(descriptor, payload)
        os.fsync(directory_fd)
    except KeyboardInterrupt:
        raise _ReservationFailure(True) from None
    except (OSError, RawRunError):
        raise _ReservationFailure(False) from None
    finally:
        os.close(descriptor)


def _publish(directory_fd: int, name: str, payload: bytes) -> None:
    temporary = ".raw-pending-" + uuid.uuid4().hex
    descriptor = None
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
        _write(descriptor, payload)
        os.close(descriptor)
        descriptor = None
        os.link(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd, follow_symlinks=False)
        os.fsync(directory_fd)
    except OSError:
        raise RawRunError("run publication failed; candidate remains spent") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        except OSError:
            pass  # The owner-only orphan cannot confer another run permission.


def _load_candidate():
    from .raw_candidate import run_raw_candidate
    return run_raw_candidate


def _prepare_structure(structure: dict) -> None:
    """Pure source/target validation precedes the look; no outcome loader runs."""
    from .raw_candidate import build_target_frames
    try:
        targets = build_target_frames(structure)
        positive = any(Fraction(row["weight"]) > 0
            for frame in targets["frames"] for row in frame["weights"])
    except Exception:
        raise RawRunError("candidate source validation refused") from None
    if not positive:
        raise RawRunError("no positive proxy targets")


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class RawRunResult:
    status: str
    report_sha256: str | None
    report_path: Path | None
    terminal_path: Path


def execute_run(spec_bytes: bytes, root: Path) -> RawRunResult:
    """Public production-only entry: a mode flag cannot select fixture custody."""
    spec = _spec(spec_bytes)
    if spec["mode"] != "production":
        raise RawRunError("public executor is production-only")
    return _execute_run(spec_bytes, root)


def _execute_fixture_run(spec_bytes: bytes, root: Path) -> RawRunResult:
    """Private fixture seam, never an empirical look or production entry point."""
    spec = _spec(spec_bytes)
    if spec["mode"] != "offline-fixture":
        raise RawRunError("private fixture executor requires offline-fixture identity")
    return _execute_run(spec_bytes, root)


def _execute_run(spec_bytes: bytes, root: Path) -> RawRunResult:
    """Validate rights and pure targets, reserve, then open outcomes and run.

    Importing the pure candidate for source validation confers no authority;
    its outcome-consuming runner is obtained and called only after reservation.
    """
    spec = _spec(spec_bytes)
    if spec["mode"] == "production":
        _verify_lane()
    current = _now()
    if type(current) is not datetime or current.tzinfo is None or current.utcoffset() != timedelta(0):
        raise RawRunError("invalid current run clock")
    if not _clock(spec["created_utc"]) <= current < _clock(spec["expires_utc"]):
        raise RawRunError("run spec is not currently valid")
    directory_fd = _open_root(root, spec["mode"])
    try:
        _verify_code(spec["code_hashes"])
        _rights(_decode(_read_file(directory_fd, "rights.json", MAX_RIGHTS_BYTES, spec["rights_sha256"]), MAX_RIGHTS_BYTES))
        structure = _decode(_read_file(directory_fd, "structure.json", MAX_INPUT_BYTES, spec["structure_sha256"]), MAX_INPUT_BYTES)
        _structure(structure)
        if _clock(structure["capture_utc"]) > current:
            raise RawRunError("source capture is in the future")
        _prepare_structure(structure)
        try:
            _reserve(directory_fd, spec, _digest(spec_bytes), current.isoformat())
        except _ReservationFailure as failure:
            status = "INTERRUPTED" if failure.interrupted else "FAILED"
            terminal_name = CANDIDATE_ID + ".terminal.json"
            _publish(directory_fd, terminal_name, _canonical({"schema": "tpr-raw-run-terminal-v1",
                "candidate_id": CANDIDATE_ID, "spec_sha256": _digest(spec_bytes), "mode": spec["mode"],
                "status": status, "failure": "reservation_incomplete", "report_sha256": None,
                "development_look_spent": 1 if spec["mode"] == "production" else 0,
                "fixture_runs": 1 if spec["mode"] == "offline-fixture" else 0,
                "quantconnect_attempts": 0, "canonical_admission": False,
                "canonical_custody": False, "trading": False}))
            if failure.interrupted:
                raise KeyboardInterrupt("reservation interrupted; look remains spent") from None
            return RawRunResult(status, None, None, root / terminal_name)
        status, report_sha256, report_path, failure, interrupted = "FAILED", None, None, None, False
        try:
            outcomes = _decode(_read_file(directory_fd, "outcomes.json", MAX_INPUT_BYTES, spec["outcomes_sha256"]), MAX_INPUT_BYTES)
            if (set(outcomes) != {"schema", "sessions"} or outcomes["schema"] != "tpr-raw-outcomes-v1"
                    or type(outcomes["sessions"]) is not list or len(outcomes["sessions"]) > 256):
                raise RawRunError("invalid outcome framing")
            _verify_code(spec["code_hashes"])
            report = _load_candidate()(structure, outcomes)
            payload = _canonical(report)
            _decode(payload, MAX_INPUT_BYTES)
            identity = _digest(payload)
            report_name = CANDIDATE_ID + "." + identity + ".report.json"
            _publish(directory_fd, report_name, payload)
            report_sha256, report_path, status = identity, root / report_name, "COMPLETED"
        except KeyboardInterrupt:
            interrupted, status, failure = True, "INTERRUPTED", "candidate_interrupted"
        except Exception:
            failure = "candidate_failed"
        terminal_name = CANDIDATE_ID + ".terminal.json"
        _publish(directory_fd, terminal_name, _canonical({"schema": "tpr-raw-run-terminal-v1",
            "candidate_id": CANDIDATE_ID, "spec_sha256": _digest(spec_bytes), "mode": spec["mode"],
            "status": status, "failure": failure, "report_sha256": report_sha256,
            "development_look_spent": 1 if spec["mode"] == "production" else 0,
            "fixture_runs": 1 if spec["mode"] == "offline-fixture" else 0,
            "quantconnect_attempts": 0, "canonical_admission": False,
            "canonical_custody": False, "trading": False}))
        if interrupted:
            raise KeyboardInterrupt("candidate interrupted; look remains spent") from None
        return RawRunResult(status, report_sha256, report_path, root / terminal_name)
    finally:
        os.close(directory_fd)


def preflight(root: Path = PRODUCTION_ROOT, *, mode: str = "production") -> dict:
    """Report fixed-file presence/custody only; never open data or imply readiness."""
    result = {"candidate_id": CANDIDATE_ID, "mode": mode, "ready": False,
        "inputs": {name: "unavailable" for name in ("rights.json", "structure.json", "outcomes.json")},
        "outcomes_read": False, "development_looks": 0, "reason": "verified_evidence_and_spec_required"}
    if type(mode) is not str or mode not in ("production", "offline-fixture"):
        raise RawRunError("invalid preflight mode")
    if type(root) is not type(LANE_ROOT):
        raise RawRunError("invalid private run root")
    try:
        if mode == "production":
            _verify_lane()
        directory_fd = _open_root(root, mode)
    except RawRunError:
        result["reason"] = "private_bundle_unavailable" if root.exists() else "rights_missing"
        return result
    try:
        for name in result["inputs"]:
            try:
                metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                result["inputs"][name] = ("present_unverified" if stat.S_ISREG(metadata.st_mode)
                    and metadata.st_uid == os.getuid() and stat.S_IMODE(metadata.st_mode) == 0o600
                    and metadata.st_nlink == 1 else "custody_refused")
            except FileNotFoundError:
                result["inputs"][name] = "missing"
        if result["inputs"]["rights.json"] == "missing":
            result["reason"] = "rights_missing"
        try:
            os.stat(CANDIDATE_ID + ".spent.json", dir_fd=directory_fd, follow_symlinks=False)
            result["reason"] = "candidate_spent"
        except FileNotFoundError:
            pass
    finally:
        os.close(directory_fd)
    return result


class _CommandError(RawRunError):
    pass


class _CommandParser(argparse.ArgumentParser):
    def error(self, _message):
        # argparse's default error includes caller argument values and paths.
        raise _CommandError("invalid command arguments")


def main(argv: list[str] | None = None) -> int:
    """Default to presence-only preflight; run only the exact fixed private spec."""
    try:
        parser = _CommandParser(prog="tpr-raw-run", allow_abbrev=False,
            description="Inspect or execute the admitted private raw-revision candidate.")
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--preflight", action="store_true", help="Report presence only; this is the default.")
        mode.add_argument("--run", action="store_true", help="Execute the fixed private candidate after admission.")
        parser.add_argument("--spec-sha256", help="Required exact lowercase SHA-256 of fixed run-spec.json for --run.")
        arguments = parser.parse_args(argv)
        if arguments.run:
            if arguments.spec_sha256 is None:
                raise _CommandError("invalid command arguments")
            identity = _hash(arguments.spec_sha256)
            _verify_lane()
            directory_fd = _open_root(PRODUCTION_ROOT, "production")
            try:
                payload = _read_file(directory_fd, "run-spec.json", MAX_RIGHTS_BYTES, identity)
            finally:
                os.close(directory_fd)
            result = execute_run(payload, PRODUCTION_ROOT)
            print(_canonical({"status": result.status, "report_sha256": result.report_sha256}).decode("ascii"), end="")
            return 0 if result.status == "COMPLETED" else 1
        if arguments.spec_sha256 is not None:
            raise _CommandError("invalid command arguments")
        print(_canonical(preflight()).decode("ascii"), end="")
        return 0
    except _CommandError:
        print(_canonical({"status": "REFUSED", "reason": "invalid_command_arguments"}).decode("ascii"), end="")
        return 2
    except RawRunError:
        print(_canonical({"status": "REFUSED", "reason": "run_refused"}).decode("ascii"), end="")
        return 2
    except KeyboardInterrupt:
        print(_canonical({"status": "INTERRUPTED", "reason": "operation_interrupted"}).decode("ascii"), end="")
        return 130
    except Exception:
        print(_canonical({"status": "FAILED", "reason": "operation_failed"}).decode("ascii"), end="")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
