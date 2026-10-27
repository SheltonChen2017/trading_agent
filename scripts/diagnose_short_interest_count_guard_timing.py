"""One finite, read-only original-archive guard timing diagnostic.

No tickets are reserved and no source lease, claim, volume or wire is opened.
The original four-epoch loader must close before the pure accounting sample.
Its result measures guard cost; it grants no custody or dispatch exception.
"""
import math
import os
from pathlib import Path
import re
import sys
import time

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf import native_count_recovery_budget as plan_model
from scripts import load_short_interest_count_epoch_ledger as loader
from scripts import short_interest_count_durable_budget as accounting

ROOT = loader.lane.ROOT
DRIVER = "scripts/diagnose_short_interest_count_guard_timing.py"
PROTOCOL_SHA256 = "9fdb15e412f2caa161ddef2078dc601a0984c365992084a018a6331eb724deb4"
MAXIMUM_SECONDS, SAMPLES, MAXIMUM_GIT_COMMANDS = 1800, 3, 20000
HISTORICAL_HEADS = (
    "ab169b34f8763af7bd529ba98dbe151b5aa46e6c", "f67bbf2fc5ab4c7ce822c7e52b57b560cd670682",
    "91f4158b6c9a9b4bf0099e60e5a50d2d9727587b", "3784f4f8779b4a8a14aed109b6a9cb8354126dd7",
    "f61a40bf497747cffdda367d2a20c393383c8232", "a5ac4c22499e13f04776a8fa145fd3dba72bc383",
    "11d6b300b6737ead079a3a0532b5bfdd693600c5", "64f372ea8bfbcc542e87356a5e3e58fe07da1c27",
    "71f0a62de1ecfa07e1c1f91bd34ec94361eb207a", "99417837467f98b0ed02a3272b0980f4efa2d243",
    "e9771c52824edc3fb123d586230ffca36bcfdd8f", "2d11d1f5b73a04e0701c65bdeb81152766535f89")
_INVOKED = False
_SEAMS, _COUNTERS = {}, {}
_CODES = frozenset("""timing_registration_pending timing_arguments_refused timing_already_invoked
timing_clock_refused timing_window_exhausted timing_code_changed timing_baseline_changed
timing_external_seam_denied timing_counter_changed timing_not_closed""".split())


class CountGuardTimingRefusal(ValueError): pass


def require(value, code):
    if not value: raise CountGuardTimingRefusal("REFUSED: " + code)


def code_paths():
    return tuple(sorted(set((*loader.code_paths(), DRIVER,
        "research/short_interest_etf/native_count_recovery_budget.py",
        "scripts/short_interest_count_durable_budget.py",
        "scripts/short_interest_closed_count_chunk.py",
        "scripts/short_interest_count_durable_transport.py"))))


def protocol():
    return {"schema": "si-count-guard-readonly-timing-v1", "root": str(ROOT),
        "baseline_ledger_sha256": plan_model.BASELINE_LEDGER_SHA256,
        "loader_protocol_sha256": loader.PROTOCOL_SHA256,
        "budget_policy_sha256": hash_payload(accounting.policy()),
        "maximum_seconds": MAXIMUM_SECONDS, "samples": SAMPLES,
        "maximum_Git_commands": MAXIMUM_GIT_COMMANDS,
        "Git_show": "exact_current_or_fixed_historical_HEAD_colon_exact_held_code_path_no_options",
        "Git_ancestry": "fixed_historical_HEAD_to_exact_runtime_HEAD_only",
        "historical_heads": list(HISTORICAL_HEADS),
        "source_context": "original_all_exits_then_closed_summary_before_accounting",
        "sample": "original_model_guard_original_plan_guard_original_empty_budget_summary",
        "ticket_reservations": 0, "new_claims": 0, "new_HTTP": 0,
        "new_STARTs": 0, "new_charged_bytes": 0, "new_files": 0,
        "runtime_code_paths": list(code_paths()), "authority": loader.authority()}


def registered():
    require((MAXIMUM_SECONDS, SAMPLES, MAXIMUM_GIT_COMMANDS) == (1800, 3, 20000)
        and hash_payload(protocol()) == PROTOCOL_SHA256, "timing_registration_pending")


def failure_summary(error):
    if type(error) is CountGuardTimingRefusal:
        args = BaseException.args.__get__(error, BaseException)
        code = None
        if type(args) is tuple and len(args) == 1 and type(args[0]) is str:
            code = next((item for item in _CODES if args[0] == "REFUSED: " + item), None)
        return {"stage": "readonly_timing", "category": "local_contract_refusal", "contract_code": code}
    return loader.failure_summary(error)


class OfflineSeams:
    """Deny Python writes/native/source seams; allow exact lane Git metadata."""
    def __init__(self, runtime_head):
        require(type(runtime_head) is str and re.fullmatch(r"[0-9a-f]{40}", runtime_head),
            "timing_arguments_refused")
        self.head = runtime_head
        self.paths = frozenset(code_paths())
        self.denied = {name: 0 for name in ("network", "source", "credentials", "write", "mutation", "native", "subprocess")}
        self.git = 0
        _SEAMS[self] = (self.head, self.paths, self.denied, tuple(self.denied),
            HISTORICAL_HEADS, ROOT, loader.lane.REF, MAXIMUM_GIT_COMMANDS)
        _COUNTERS[self] = tuple(self.denied.values()), self.git

    def check(self):
        original = _SEAMS.get(self) if type(self) is OfflineSeams else None
        require(type(original) is tuple and len(original) == 8 and self.head is original[0]
            and self.paths is original[1] and self.denied is original[2]
            and tuple(self.denied) == original[3]
            and HISTORICAL_HEADS is original[4] and ROOT is original[5]
            and loader.lane.REF is original[6] and type(MAXIMUM_GIT_COMMANDS) is int
            and MAXIMUM_GIT_COMMANDS == original[7]
            and all(type(value) is int and value >= 0 for value in self.denied.values())
            and type(self.git) is int and self.git >= 0
            and (tuple(self.denied.values()), self.git) == _COUNTERS.get(self), "timing_counter_changed")

    def _record(self): _COUNTERS[self] = tuple(self.denied.values()), self.git

    def deny(self, kind):
        self.check()
        self.denied[kind] += 1
        self._record()
        raise CountGuardTimingRefusal("REFUSED: timing_external_seam_denied")

    def audit(self, event, args):
        self.check()
        if event.startswith("socket."): self.deny("network")
        if event.startswith("ctypes."): self.deny("native")
        if event == "open":
            flags = args[2]
            if type(flags) is not int or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                self.deny("write")
        if event in {"os.remove", "os.rmdir", "os.mkdir", "os.rename", "os.chmod", "os.chown",
                "os.truncate", "os.link", "os.symlink", "os.utime", "os.setxattr", "os.removexattr",
                "os.system", "os.posix_spawn", "os.exec", "os.fork", "pty.spawn"}:
            self.deny("mutation")
        if event == "subprocess.Popen":
            executable, argv, cwd, unused_env = args
            safe = type(executable) is str and executable == "git" and type(argv) in (list, tuple)
            safe = safe and len(argv) >= 2 and all(type(value) is str for value in argv)
            safe = safe and argv[0] == "git"
            safe = safe and type(cwd) in (str, type(ROOT)) and str(cwd) == str(ROOT)
            command = tuple(argv) if safe else ()
            if safe and argv[1] == "show":
                revision, separator, name = argv[2].partition(":") if len(argv) == 3 else (None, None, None)
                safe = separator == ":" and revision in (*HISTORICAL_HEADS, self.head) and name in self.paths
            elif safe and argv[1] == "merge-base":
                safe = len(argv) == 5 and argv[2] == "--is-ancestor" and argv[3] in HISTORICAL_HEADS and argv[4] == self.head
            elif safe:
                safe = command in {
                    ("git", "ls-remote", "--exit-code", "origin", loader.lane.REF),
                    ("git", "rev-parse", "--show-toplevel"), ("git", "rev-parse", "HEAD"),
                    ("git", "branch", "--show-current"), ("git", "status", "--porcelain"),
                    ("git", "status", "--porcelain=v2", "--branch", "--no-ahead-behind", "--untracked-files=all")}
            if not safe or self.git >= MAXIMUM_GIT_COMMANDS: self.deny("subprocess")
            self.git += 1
            self._record()

    def install(self):
        for module, name in ((loader.prior, "run_registered"), (loader.count, "run_registered"),
                (loader.count, "capture_chunk"), (loader.count.old, "run_registered"),
                (loader.count.old, "capture_child"), (loader.count.transport, "http"),
                (loader.count.old.original.transport, "_http"), (loader.prior._OwnedOutput, "publish")):
            setattr(module, name, lambda *args, **kwargs: self.deny("source"))
        for module in (loader.count, loader.count.old):
            setattr(module, "read_named_keychain", lambda *args, **kwargs: self.deny("credentials"))
        sys.addaudithook(self.audit)


def _window(began, previous):
    now = time.monotonic()
    require(type(now) in (int, float) and math.isfinite(now)
        and 0 <= began <= previous[0] <= now <= 2 ** 53, "timing_clock_refused")
    require(now - began < MAXIMUM_SECONDS, "timing_window_exhausted")
    previous[0] = now
    return now


def run_registered(runtime_head, actual_remote):
    global _INVOKED
    registered()
    require(not _INVOKED, "timing_already_invoked"); _INVOKED = True
    require(Path.cwd().resolve() == ROOT and ROOT.resolve() == ROOT
        and all(type(value) is str and re.fullmatch(r"[0-9a-f]{40}", value)
            for value in (runtime_head, actual_remote)), "timing_arguments_refused")
    began = time.monotonic(); previous = [began]
    guard = loader.lane.LaneGuard(ROOT, expected_head=runtime_head, expected_remote=actual_remote)
    def boundary(): guard.check(); registered(); _window(began, previous)
    seams = OfflineSeams(runtime_head); seams.install(); guard.refresh()
    paths = code_paths(); manifest = {}
    with loader.count.old.cache.HeldFiles(tuple(ROOT / name for name in paths),
            protected=False, boundary=boundary) as code:
        for name in paths:
            raw = code.read(ROOT / name, 8 * 1024 ** 2)
            committed = loader.count.old.cache._git(ROOT, ["show", runtime_head + ":" + name], guard)
            require(raw == committed, "timing_code_changed"); manifest[name] = hash_bytes(raw)
        print(canonical_json({"status": "started_readonly_guard_timing", "protocol_sha256": PROTOCOL_SHA256}), flush=True)
        with loader.load_registered_count_epoch_ledger(ROOT, runtime_head=runtime_head,
                actual_remote=actual_remote,
                complete_code_manifest={name: manifest[name] for name in loader.code_paths()}) as original:
            require(type(original) is loader.RegisteredCountEpochLedger, "timing_baseline_changed")
        closed = original.closed_summary(); model = original._anchor[0]
        require(closed["status"] == "closed_offline_source_only_slice"
            and closed["model_ledger_sha256"] == model.sha256 == plan_model.BASELINE_LEDGER_SHA256,
            "timing_baseline_changed")
        plan = plan_model.freeze_count_recovery_plan(model)
        budget = accounting.open_durable_count_budget(plan)
        samples = []
        for unused in range(SAMPLES):
            row = {}
            for name, function in (("model_guard", model._guard), ("plan_guard", plan._guard),
                    ("empty_budget_summary", budget.public_summary)):
                boundary(); before = _window(began, previous); function()
                row[name] = _window(began, previous) - before
            samples.append(row)
        summary = budget.public_summary()
        require(summary["new_START_reservations"] == 0 and not budget.current_tickets(), "timing_baseline_changed")
        code.check(); guard.refresh(); boundary()
        for name in paths:
            require(hash_bytes(code.read(ROOT / name, 8 * 1024 ** 2)) == manifest[name], "timing_code_changed")
    # All ORIGINAL held code/source contexts have closed successfully.
    guard.refresh(); registered(); _window(began, previous)
    seams.check(); require(not any(seams.denied.values()), "timing_counter_changed")
    return {"schema": "si-count-guard-readonly-timing-closed-v1", "status": "closed_readonly_guard_timing_only",
        "HEAD": runtime_head, "actual_remote": actual_remote, "protocol_sha256": PROTOCOL_SHA256,
        "code_manifest_sha256": hash_payload(manifest), "code_file_count": len(paths),
        "original_archive_closed_summary_sha256": hash_payload(closed), "samples_seconds": samples,
        "new_ticket_reservations": 0, "denied_seams": dict(seams.denied), "permitted_Git": seams.git,
        "authority": loader.authority()}


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    try:
        require(type(arguments) is list and len(arguments) == 2, "timing_arguments_refused")
        print(canonical_json(run_registered(*arguments)), flush=True); return 0
    except BaseException as error:
        print(canonical_json({"status": "refused", "fixed_diagnostic": failure_summary(error),
            "authority": loader.authority()}), flush=True); return 2


if __name__ == "__main__": raise SystemExit(main())
