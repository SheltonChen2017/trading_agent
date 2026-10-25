"""One finite local custody stress probe, never a capture or source claim.

Old source evidence and spent claims stay immutable.  Success means only that
the registered local metadata observations did not reproduce the historical
failure; it is not a repair, source qualification, or backtest readiness.
"""
from __future__ import annotations

from contextlib import contextmanager, ExitStack
import dataclasses
import os
from pathlib import Path
import re
import stat
import time
from types import TracebackType

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import capture_short_interest_bounded_count_chunk as count
from scripts import short_interest_lane_batch_guard as lane
from scripts import short_interest_refused_count_snapshot as snapshot
from scripts.continue_short_interest_native_identity import _OwnedOutput
from scripts.qualify_finra_short_interest import _prepare_capture_directory, _require_capture_platform
from scripts.qualify_sharadar_companion import _utc_now

DRIVER = "scripts/diagnose_short_interest_count_custody.py"
NAMESPACE = "local-custody-probe-20261025-v3"
OUTPUT = count.old.OUTPUT.parent / NAMESPACE
PROBE_SPECS = tuple((size, index >= 8) for index, size in enumerate((186, 730, 746, 800) * 4))
MAXIMUM_PROBES, MAXIMUM_PROBE_BYTES, MAXIMUM_SECONDS = 16, 1024, 1800
PROTOCOL_SHA256 = "f610f9561576a6e1bb3e1f0fc1abb541a359871cbf9ee37c8e2b9f40543ab361"
V3_HEAD = "2d11d1f5b73a04e0701c65bdeb81152766535f89"
V3_REMOTE = "b648f60112af141efc2a12fbaef03b38846d219d"
V3_CLAIM_SHA256 = "b32d9e9757a29e0edae07b87159361a83185f84513826280bef4560aef96e353"
V3_REFUSAL_SHA256 = "594f53f5b275fabc5a2784e660533d98f0f0069d30dec85855ea9251bec213dc"
_ENTRY_CHECK_CODE = count.old.cache.HeldFiles._entry_check.__code__
MAXIMUM_TRACE_FRAMES = 128
_FIELD_NAMES = ("regular", "nlink", "dev", "ino", "size", "mtime_ns", "ctime_ns", "uid", "mode")
_COMPONENTS = frozenset(("base_code", "extra_code", "probe_code", "cache_source", "master_source",
    "matrix_source", "v2_zero", "v3_zero", "new_probe", "unidentified"))


class CustodyDiagnosticRefusal(ValueError):
    pass


_OWN_CONTRACT_CODES = frozenset("""
bounded_diagnostic_registration_required bounded_diagnostic_report_required bounded_nonclaim_metadata_required
designated_diagnostic_driver_required diagnostic_clock_backdated diagnostic_code_custody_changed
diagnostic_committed_code_manifest_changed diagnostic_output_membership_changed diagnostic_output_must_be_ignored
diagnostic_preflight_window_exhausted diagnostic_protocol_pending_or_changed diagnostic_report_changed
diagnostic_report_factory_required diagnostic_result_missing earlier_nonclaim_probe_changed
earlier_nonclaim_probe_changed_during_final_audit earlier_nonclaim_probe_stamp_changed
exact_complete_56_code_manifest_required exact_diagnostic_code_custody_required exact_diagnostic_original_member_required
exact_fixed_nonclaim_metadata_size_required exact_local_probe_bindings final_diagnostic_code_identity_changed
final_diagnostic_code_stamp_changed final_diagnostic_committed_code_bytes_changed final_earlier_diagnostic_code_changed
final_exact_diagnostic_registration_required finite_diagnostic_context_closure_window_exhausted
finite_diagnostic_window_exhausted fixed_nonclaim_metadata_already_exists fixed_nonclaim_metadata_size_too_small
fixed_probe_ordinal_required fixed_probe_parent_changed fixed_probe_parent_protection fixed_probe_parent_required
immutable_v3_zero_controls_changed nonclaim_probe_original_bytes_changed original_diagnostic_closure_material_required
post_context_clock_backdated post_context_earlier_original_member_changed post_context_final_clock_backdated
post_context_original_member_bytes_changed post_context_original_member_stamp_changed post_context_owned_report_required
registered_diagnostic_code_path_required v3_code_not_lane_ancestor v3_exact_historical_code_changed
v3_historical_registration_changed v3_spent_claim_semantics_changed v3_zero_exact_negative_membership_changed
v3_zero_namespace_changed v3_zero_negative_or_budget_changed v3_zero_original_clocks_changed
v3_zero_original_control_bytes_changed v3_zero_proof_changed
""".split())
_INITIALIZATION_STAGES = frozenset("""
protocol_registration platform_capability designated_driver lane_guard_initialization lane_remote_initialization
complete_code_manifest_shape saved_cache_loading current_extra_code_loading diagnostic_code_loading
current_code_manifest_verification refused_prefix_loading query_plan_binding v2_zero_loading v3_zero_loading
runtime_registration output_ignore_preflight metadata_absence_preflight finite_preflight output_directory_creation
output_custody_open local_probe_sequence source_code_context_exit terminal_context_finalization output_custody_close
""".split())
_FAILURE_SEAL = object()


class _DiagnosticStageFailure(ValueError):
    __slots__ = ("_anchor", "_identity")

    def __init__(self, stage, error, *, seal):
        if seal is not _FAILURE_SEAL or type(stage) is not str or stage not in _INITIALIZATION_STAGES:
            raise CustodyDiagnosticRefusal("REFUSED: diagnostic_result_missing")
        self._anchor = self._identity = (stage, error)
        super().__init__("diagnostic_initialization_refused")


def fixed_local_failure(error):
    """Exact own type/literal catalogue, otherwise the existing safe classifier."""
    if type(error) is CustodyDiagnosticRefusal:
        args = BaseException.args.__get__(error, BaseException)
        code = None
        if (type(args) is tuple and len(args) == 1 and type(args[0]) is str
            and len(args[0]) <= 256 and args[0].startswith("REFUSED: ")):
            candidate = args[0][len("REFUSED: "):]
            if candidate in _OWN_CONTRACT_CODES:
                code = candidate
        return {"category": "local_contract_refusal", "errno_name": None, "contract_code": code}
    return count.diagnostics.fixed_local_failure(error)


def failure_summary(error):
    """Wrapper-facing metadata only, including failures before output exists."""
    stage, original = "unclassified_diagnostic_failure", error
    if type(error) is _DiagnosticStageFailure:
        try:
            anchor = object.__getattribute__(error, "_anchor")
            identity = object.__getattribute__(error, "_identity")
        except AttributeError:
            return {"stage": stage, **fixed_local_failure(error), "held_field_observation": None}
        args = BaseException.args.__get__(error, BaseException)
        if (anchor is identity and type(anchor) is tuple and len(anchor) == 2
            and type(anchor[0]) is str and anchor[0] in _INITIALIZATION_STAGES
            and type(args) is tuple and len(args) == 1 and type(args[0]) is str
            and args[0] == "diagnostic_initialization_refused"):
            stage, original = anchor
    return {"stage": stage, **fixed_local_failure(original),
        "held_field_observation": project_held_file_mismatch(original)}


def require(value, code):
    if not value:
        raise CustodyDiagnosticRefusal("REFUSED: " + code)


def authority():
    return {"diagnostic_only": True, "is_capture_claim": False, "provider_HTTP": 0,
        "credential_reads": 0, "source_START_debits": 0, "source_charged_bytes": 0,
        "source_admitted": False, "ready_for_backtest": False, "historical_022_cause": "UNKNOWN",
        "root_cause_fix_established": False, "outcome_looks": 0, "qc_attempts": 0, "trading_authority": False}


def protocol():
    return {"schema": "si-count-local-custody-diagnostic-protocol-v3", "driver": DRIVER,
        "output": str(OUTPUT), "metadata_namespace": NAMESPACE,
        "maximum_probes": MAXIMUM_PROBES, "maximum_probe_bytes": MAXIMUM_PROBE_BYTES,
        "maximum_seconds": MAXIMUM_SECONDS, "maximum_trace_frames": MAXIMUM_TRACE_FRAMES,
        "probe_sizes": [row[0] for row in PROBE_SPECS],
        "additional_preopen_normal_checks": [row[1] for row in PROBE_SPECS],
        "metadata": "safe_fixed_JSON_padding_never_a_copy_of_private_claim_bytes",
        "publication": "parent_metadata_O_EXCL_0600_same_OwnedOutput_then_ExitStack_HeldFiles_normal_boundary",
        "handles": "close_each_probe_after_original_read;constant_extra_descriptors",
        "projection": "original_HeldFiles_entry_check_frame_only_failed_stat_field_NAMES_no_values_or_paths",
        "source_history": "authenticate_saved_cache_refused13944_prefix_and_both_zero_START_claims",
        "predecessor_manifest_sha256": count.PREDECESSOR_MANIFEST_SHA256,
        "v2_claim_sha256": snapshot.ZERO_CLAIM_SHA256, "v2_refusal_sha256": snapshot.ZERO_REFUSAL_SHA256,
        "v3_claim_sha256": V3_CLAIM_SHA256, "v3_refusal_sha256": V3_REFUSAL_SHA256,
        "predecessor_diagnostic": "local-custody-probe-20261025-v2_closed_preoutput_no_metadata;never_restart",
        "historical_54916_exception": "UNKNOWN_not_persisted",
        "adapter_correction": "strict_original_v3_fixed_diagnostic_field_not_failure_detail",
        "preoutput_diagnostics": "exact_own_type_literal_codes_and_sealed_fixed_stage_no_exception_formatting",
        "own_contract_codes": sorted(_OWN_CONTRACT_CODES), "initialization_stages": sorted(_INITIALIZATION_STAGES),
        "restart_or_retry_allowed": False, "new_source_claims": 0, "authority": authority()}


def registered():
    require(hash_payload(protocol()) == PROTOCOL_SHA256 and len(PROBE_SPECS) == MAXIMUM_PROBES == 16
        and all(type(size) is int and 0 < size <= MAXIMUM_PROBE_BYTES == 1024
            and type(extra) is bool for size, extra in PROBE_SPECS)
        and MAXIMUM_SECONDS == 1800 and MAXIMUM_TRACE_FRAMES == 128,
        "diagnostic_protocol_pending_or_changed")


def code_paths():
    return tuple(sorted((*count.code_paths(), DRIVER)))


def probe_name(ordinal):
    require(type(ordinal) is int and 1 <= ordinal <= MAXIMUM_PROBES, "fixed_probe_ordinal_required")
    return f"{NAMESPACE}-item-{ordinal:02d}.private.json"


def probe_bytes(ordinal, size):
    require(type(size) is int and 0 < size <= MAXIMUM_PROBE_BYTES
        and type(ordinal) is int and 1 <= ordinal <= MAXIMUM_PROBES, "bounded_nonclaim_metadata_required")
    value = {"schema": "si-custody-nonclaim-v3", "is_capture_claim": False, "provider_HTTP": 0,
        "credential_reads": 0, "source_START_debits": 0, "ordinal": ordinal, "padding": ""}
    empty = canonical_json(value).encode()
    require(len(empty) <= size, "fixed_nonclaim_metadata_size_too_small")
    value["padding"] = ("p" if ordinal % 2 else "0") * (size - len(empty))
    raw = canonical_json(value).encode()
    require(len(raw) == size, "exact_fixed_nonclaim_metadata_size_required")
    return raw


def project_held_file_mismatch(error, *, components=(), new_probe_binding=None):
    """Pure projection from the genuine failed frame; never inspect paths/I/O."""
    if type(error) is not count.old.cache.contract.AnchorCacheRefusal:
        return None
    args = BaseException.args.__get__(error, BaseException)
    if (type(args) is not tuple or len(args) != 1 or type(args[0]) is not str
        or args[0] != "held_custody_file_changed"):
        return None
    if type(components) is not tuple or any(type(row) is not tuple or len(row) != 2
        or type(row[1]) is not str or row[1] not in _COMPONENTS for row in components):
        return None
    trace = BaseException.__traceback__.__get__(error, BaseException)
    for unused in range(MAXIMUM_TRACE_FRAMES):
        if type(trace) is not TracebackType:
            return None
        frame = trace.tb_frame
        if frame.f_code is _ENTRY_CHECK_CODE:
            local = frame.f_locals
            entry, value = local.get("entry"), local.get("value")
            if (type(entry) is not tuple or len(entry) != 6 or type(value) is not os.stat_result
                or type(entry[3]) is not tuple or len(entry[3]) != 5
                or any(type(item) is not int for item in (*entry[3], entry[4], entry[5]))
                or local.get("original") is not entry[3]):
                return None
            original, uid, mode = entry[3], entry[4], entry[5]
            failed = {"regular": not stat.S_ISREG(value.st_mode), "nlink": value.st_nlink != 1,
                "dev": value.st_dev != original[0], "ino": value.st_ino != original[1],
                "size": value.st_size != original[2], "mtime_ns": value.st_mtime_ns != original[3],
                "ctime_ns": value.st_ctime_ns != original[4], "uid": value.st_uid != uid,
                "mode": stat.S_IMODE(value.st_mode) != mode}
            held = local.get("self")
            label = next((label for component, label in components if component is held), "unidentified")
            if label == "unidentified" and type(held) is count.old.cache.HeldFiles:
                anchor = object.__getattribute__(held, "_anchor")
                if (type(new_probe_binding) is tuple and len(new_probe_binding) == 2
                    and type(new_probe_binding[0]) is type(Path("."))
                    and type(anchor) is tuple and len(anchor) == 4 and type(anchor[1]) is tuple
                    and len(anchor[1]) == 1 and anchor[1][0] is entry and anchor[2] is True
                    and anchor[3] is new_probe_binding[1] and type(entry[0]) is type(Path("."))
                    and entry[0] == new_probe_binding[0]):
                    label = "new_probe"
            return {"component": label, "mismatch_fields": [name for name in _FIELD_NAMES if failed[name]],
                "observation": "original_failed_stat_result_only"}
        trace = trace.tb_next
    return None


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class CustodyDiagnosticReport:
    _raw: bytes = dataclasses.field(repr=False)
    _sha256: str
    _anchor: tuple = dataclasses.field(repr=False)
    _identity: tuple = dataclasses.field(repr=False)

    def __init__(self):
        raise CustodyDiagnosticRefusal("REFUSED: diagnostic_report_factory_required")

    def _guard(self):
        require(type(self) is CustodyDiagnosticReport and self._anchor is self._identity
            and type(self._anchor) is tuple and len(self._anchor) == 2
            and self._raw is self._anchor[0] and self._sha256 is self._anchor[1], "diagnostic_report_changed")

    def to_bytes(self):
        self._guard(); return self._raw

    def to_payload(self):
        return count.old._parse(self.to_bytes())

    @property
    def sha256(self):
        self._guard(); return self._sha256

    def public_summary(self):
        self._guard()
        value = self.to_payload()
        return {name: value[name] for name in ("schema", "status", "probes_published", "probes_opened",
            "probes_read", "failure", "authority")}


def _seal(payload):
    raw = canonical_json(payload).encode()
    require(len(raw) <= 64 * 1024, "bounded_diagnostic_report_required")
    value = object.__new__(CustodyDiagnosticReport)
    parts = raw, hash_bytes(raw)
    for name, item in (("_raw", parts[0]), ("_sha256", parts[1]), ("_anchor", parts), ("_identity", parts)):
        object.__setattr__(value, name, item)
    value._guard(); return value


class _CodeCustody:
    def __init__(self, root, composed, extra):
        require(type(composed) is count._ComposedCodeCustody and type(extra) is count.old.cache.HeldFiles,
            "exact_diagnostic_code_custody_required")
        self._anchor = self._identity = root, composed, extra

    def check(self):
        require(type(self) is _CodeCustody and self._anchor is self._identity,
            "diagnostic_code_custody_changed")
        unused_root, composed, extra = self._anchor
        composed.check(); extra.check()

    def read(self, path, maximum):
        self.check()
        root, composed, extra = self._anchor
        require(path in tuple(root / name for name in code_paths()), "registered_diagnostic_code_path_required")
        raw = (extra if path == root / DRIVER else composed).read(path, maximum)
        self.check(); return raw


class _V3ZeroProof:
    def __init__(self, directory, held, queries, paths, claim_raw, refused_raw):
        fd = next(fd for path, fd, unused in held._anchor[0] if path == directory)
        self._anchor = self._identity = (directory, held, queries, paths, claim_raw, refused_raw,
            fd, snapshot._directory_stamp(directory.lstat()))
        self.full_check()

    def check(self):
        require(type(self) is _V3ZeroProof and self._anchor is self._identity
            and type(self._anchor) is tuple and len(self._anchor) == 8, "v3_zero_proof_changed")
        directory, held, queries, unused_paths, unused_claim, unused_refusal, fd, stamp = self._anchor
        held.check(); queries._guard()
        require(snapshot._directory_stamp(directory.lstat()) == snapshot._directory_stamp(os.fstat(fd)) == stamp,
            "v3_zero_namespace_changed")

    def full_check(self):
        self.check()
        unused_dir, held, unused_queries, paths, claim_raw, refused_raw, fd, unused_stamp = self._anchor
        require(count.old.cache._inventory_names(fd, boundary=held.check) == ("run.refused.json",),
            "v3_zero_exact_negative_membership_changed")
        require(held.read(paths[0], 65536) == claim_raw and held.read(paths[1], 65536) == refused_raw,
            "v3_zero_original_control_bytes_changed")
        self.check()


@contextmanager
def _v3_zero(root, guard, queries):
    directory = root / count.OUTPUT
    paths = directory.parent / count.CLAIM, directory / "run.refused.json"
    with count.old.cache.HeldFiles(paths, protected=True, boundary=guard.check) as held:
        claim_raw, refused_raw = (held.read(path, 65536) for path in paths)
        require(hash_bytes(claim_raw) == V3_CLAIM_SHA256 and hash_bytes(refused_raw) == V3_REFUSAL_SHA256,
            "immutable_v3_zero_controls_changed")
        claim, refused = count.old._parse(claim_raw), count.old._parse(refused_raw)
        require(count.old._exact(claim, {"schema": "si-bounded-count-spent-claim-v3",
            "protocol_sha256": count.PROTOCOL_SHA256, "registration": claim.get("registration"),
            "started_at": claim.get("started_at"), "query_plan_sha256": queries.sha256,
            "predecessor_manifest_sha256": count.PREDECESSOR_MANIFEST_SHA256,
            "maximum_attempts": 528, "maximum_extra_attempts": 16, "prior_STARTs": 13992,
            "prior_charged_bytes": 23452681, "maximum_cumulative_bytes": 4 * 1024 ** 3,
            "restart_allowed": False}), "v3_spent_claim_semantics_changed")
        registration = claim["registration"]
        require(type(registration) is dict and set(registration) == {"head", "remote", "code_identity_sha256"}
            and registration["head"] == V3_HEAD and registration["remote"] == V3_REMOTE,
            "v3_historical_registration_changed")
        require(count.old._exact(refused, {"schema": "si-bounded-count-refused-v3",
            "code": "initialization_refused_after_spent_claim", "protocol_sha256": count.PROTOCOL_SHA256,
            "started_at": claim["started_at"], "refused_at": refused.get("refused_at"),
            "START_debits": 0, "known_HTTP_invocations": 0, "HTTP_count_exact": True,
            "unreceipted_attempts": [], "receipt_not_persisted_attempts": [], "unpublished_observed_diagnostics": [],
            "charged_bytes": 0, "cumulative_STARTs": 13992, "cumulative_charged_bytes": 23452681,
            "resolved_descriptors": 0, "new_claim_sha256": V3_CLAIM_SHA256, "authority": count.authority(),
            "fixed_diagnostic": {"stage": "claim_custody_open", "category": "local_contract_refusal",
                "errno_name": None, "contract_code": "held_custody_file_changed"}}),
            "v3_zero_negative_or_budget_changed")
        require(count.old.parallel.clock(claim["started_at"]) <= count.old.parallel.clock(refused["refused_at"]),
            "v3_zero_original_clocks_changed")
        require(count.old.cache._git(root, ["merge-base", "--is-ancestor", V3_HEAD, guard.binding()[1]], guard) == b"",
            "v3_code_not_lane_ancestor")
        entries = [{"path": name, "sha256": hash_bytes(count.old.cache._git(root,
            ["show", V3_HEAD + ":" + name], guard))} for name in count.code_paths()]
        require(len(entries) == 55 and hash_payload({"git_commit": V3_HEAD, "files": entries})
            == registration["code_identity_sha256"], "v3_exact_historical_code_changed")
        proof = _V3ZeroProof(directory, held, queries, paths, claim_raw, refused_raw)
        yield held, proof
        proof.full_check(); guard.check()


def _preflight_absent_metadata(parent, boundary):
    boundary()
    require(parent.is_absolute() and parent.resolve() == parent, "fixed_probe_parent_required")
    before = parent.lstat()
    stamp = lambda info: (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode))
    require(stat.S_ISDIR(before.st_mode) and before.st_uid == os.getuid()
        and stat.S_IMODE(before.st_mode) == 0o700, "fixed_probe_parent_protection")
    fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        require(stamp(os.fstat(fd)) == stamp(before), "fixed_probe_parent_changed")
        for ordinal in range(1, MAXIMUM_PROBES + 1):
            try:
                os.stat(probe_name(ordinal), dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise CustodyDiagnosticRefusal("REFUSED: fixed_nonclaim_metadata_already_exists")
        require(stamp(os.fstat(fd)) == stamp(parent.lstat()) == stamp(before), "fixed_probe_parent_changed")
    finally:
        os.close(fd)
    boundary()


def run_probe_sequence(*, owned, normal_check, refusal_check, source_full_check, components,
                       registration, clock=_utc_now, monotonic=time.monotonic, began_tick=None,
                       report_sink=lambda report: None, closure_sink=lambda material: None):
    """Diagnostic-only fabricated seams; no source capture or key seam exists."""
    registered()
    require(type(owned) is _OwnedOutput and all(callable(item) for item in
        (normal_check, refusal_check, source_full_check, clock, monotonic, report_sink, closure_sink))
        and type(registration) is dict, "exact_local_probe_bindings")
    registration_raw = canonical_json(registration).encode()
    require(len(registration_raw) <= 32 * 1024, "bounded_diagnostic_registration_required")
    started = None
    tick = monotonic() if began_tick is None else began_tick
    last_clock, last_tick = None, tick
    published, opened, read_count, rows, attempted_publications = [], 0, 0, [], 0
    phase, ordinal, failure, active_probe_path = "source_pre_audit", None, None, None

    def window():
        nonlocal last_tick
        now = monotonic()
        require(type(now) in (int, float) and type(tick) in (int, float)
            and tick <= last_tick <= now and now - tick < MAXIMUM_SECONDS, "finite_diagnostic_window_exhausted")
        last_tick = now

    def normal():
        normal_check(); owned.check(); registered(); window()

    def at():
        nonlocal last_clock
        observed = clock(); value = count.old.parallel.clock(observed)
        require(last_clock is None or last_clock <= value, "diagnostic_clock_backdated")
        last_clock = value
        return observed

    def projected(error, stage):
        binding = ((active_probe_path, normal_check) if stage in
            {"held_custody_open", "held_original_read", "all_probe_original_byte_audit"} else None)
        return project_held_file_mismatch(error, components=components, new_probe_binding=binding)

    try:
        phase = "initial_clock"; started = at()
        phase = "source_pre_audit"
        normal(); source_full_check(); normal()
        for ordinal, (size, additional_check) in enumerate(PROBE_SPECS, 1):
            phase = "metadata_publication"
            normal(); raw = probe_bytes(ordinal, size); name = probe_name(ordinal)
            attempted_publications += 1
            owned.publish(name, raw, parent=True)
            published.append((name, raw, snapshot._file_stamp(os.stat(name,
                dir_fd=owned._anchor[3], follow_symlinks=False))))
            if additional_check:
                phase = "additional_preopen_normal_check"; normal()
            phase = "held_custody_open"
            window()
            with ExitStack() as lifecycle:
                path = owned._anchor[1] / name
                active_probe_path = path
                held = lifecycle.enter_context(count.old.cache.HeldFiles((path,), protected=True, boundary=normal_check))
                opened += 1
                phase = "held_original_read"; window()
                require(held.read(path, MAXIMUM_PROBE_BYTES) == raw, "nonclaim_probe_original_bytes_changed")
                read_count += 1
                held.check(); normal()
            rows.append({"ordinal": ordinal, "bytes": size, "sha256": hash_bytes(raw),
                "additional_preopen_check": additional_check, "read_at": at()})
            active_probe_path = None
        phase = "source_post_audit"
        normal(); source_full_check(); normal()
        phase = "all_probe_original_byte_audit"
        for name, raw, original_stamp in published:
            normal()
            path = owned._anchor[1] / name
            active_probe_path = path
            require(snapshot._file_stamp(path.lstat()) == original_stamp, "earlier_nonclaim_probe_stamp_changed")
            with count.old.cache.HeldFiles((path,), protected=True, boundary=normal_check) as held:
                require(held.read(path, MAXIMUM_PROBE_BYTES) == raw, "earlier_nonclaim_probe_changed")
        active_probe_path = None
        for name, unused_raw, original_stamp in published:
            require(snapshot._file_stamp(os.stat(name, dir_fd=owned._anchor[3], follow_symlinks=False))
                == original_stamp, "earlier_nonclaim_probe_changed_during_final_audit")
        normal()
    except Exception as error:
        failure = {"stage": phase, "ordinal": ordinal,
            **fixed_local_failure(error),
            "held_field_observation": projected(error, phase)}
    try:
        ended = at()
    except Exception as error:
        ended = None
        if failure is None:
            failure = {"stage": "terminal_clock", "ordinal": None,
                **fixed_local_failure(error), "held_field_observation": None}
    value = {"schema": "si-count-local-custody-diagnostic-v3",
        "status": "local_observations_passed_cause_unreproduced" if failure is None else "local_diagnostic_refused",
        "protocol_sha256": PROTOCOL_SHA256, "started_at": started, "completed_at": ended,
        "probes_published": len(published), "probes_opened": opened, "probes_read": read_count,
        "metadata_publication_attempts": attempted_publications,
        "observations": rows, "failure": failure, "authority": authority(),
        "registration": count.old._parse(registration_raw),
        "context_closure": "provisional_source_and_code_contexts_still_open"}
    report = _seal(value)
    report_sink(report)
    refusal_check(); owned.check()
    def publish_report(name, value):
        raw = value.to_bytes()
        owned.publish(name, raw)
        closure_sink((tuple(published), name, raw,
            snapshot._file_stamp(os.stat(name, dir_fd=owned._anchor[2], follow_symlinks=False))))
    publish_report("run.completed.json" if failure is None else "run.refused.json", report)
    if failure is None:
        try:
            normal(); source_full_check(); normal()
        except Exception as error:
            value.update(status="local_diagnostic_refused", failure={"stage": "postpublication_source_audit",
                "ordinal": None, **fixed_local_failure(error),
                "held_field_observation": projected(error, "postpublication_source_audit")})
            report = _seal(value)
            report_sink(report)
            refusal_check(); owned.check(); publish_report("run.refused.json", report)
    return report


def _current_code_after_contexts(root, guard, registration):
    """Fresh bounded code-only custody, after all old source FDs have closed."""
    guard.refresh(); registered()
    names = code_paths()
    require(registration["head"] == guard.binding()[1]
        and registration["remote"] == guard.binding()[2]
        and tuple(row["path"] for row in registration["code_files"]) == names
        and len(names) == 56, "final_exact_diagnostic_registration_required")
    stamps = []
    for row in registration["code_files"]:
        guard.check()
        path = root / row["path"]
        with count.old.cache.HeldFiles((path,), protected=False, boundary=guard.check) as held:
            original_stamp = snapshot._file_stamp(path.lstat())
            raw = held.read(path, 8 * 1024 * 1024)
            committed = count.old.cache._git(root, ["show", registration["head"] + ":" + row["path"]], guard)
            require(type(committed) is bytes and len(committed) <= 8 * 1024 * 1024
                and hash_bytes(raw) == hash_bytes(committed) == row["sha256"],
                "final_diagnostic_committed_code_bytes_changed")
            held.check()
            require(snapshot._file_stamp(path.lstat()) == original_stamp, "final_diagnostic_code_stamp_changed")
            stamps.append((path, original_stamp))
    for path, original in stamps:
        guard.check()
        require(snapshot._file_stamp(path.lstat()) == original, "final_earlier_diagnostic_code_changed")
    require(hash_payload({row["path"]: row["sha256"] for row in registration["code_files"]})
        == registration["code_manifest_sha256"]
        and hash_payload({"git_commit": registration["head"], "files": registration["code_files"]})
        == registration["code_identity_sha256"], "final_diagnostic_code_identity_changed")
    guard.refresh(); registered()


def _audit_closure_material(owned, result, material, extra_controls=()):
    owned.check()
    require(type(material) is tuple and len(material) == 4 and type(material[0]) is tuple
        and material[1] in {"run.completed.json", "run.refused.json"}
        and material[2] == result.to_bytes() and len(material[0]) == result.to_payload()["probes_published"],
        "original_diagnostic_closure_material_required")
    probes, report_name, report_raw, report_stamp = material
    controls = ((report_name, report_raw, report_stamp), *extra_controls)
    expected_names = {row[0] for row in controls}
    # A postpublication source failure legitimately retains both its earlier
    # provisional control and its dominating negative; never delete either.
    if report_name == "run.refused.json" and (owned._anchor[0] / "run.completed.json").exists():
        expected_names.add("run.completed.json")
    require(set(count.old.cache._inventory_names(owned._anchor[2], boundary=owned.check)) == expected_names,
        "diagnostic_output_membership_changed")
    entries = []
    for parent, rows in ((True, probes), (False, controls)):
        for index, (name, raw, original_stamp) in enumerate(rows, 1):
            require((not parent or name == probe_name(index)) and type(raw) is bytes
                and len(raw) <= (MAXIMUM_PROBE_BYTES if parent else 64 * 1024),
                "exact_diagnostic_original_member_required")
            path = owned._anchor[1 if parent else 0] / name
            require(snapshot._file_stamp(path.lstat()) == original_stamp,
                "post_context_original_member_stamp_changed")
            with count.old.cache.HeldFiles((path,), protected=True, boundary=owned.check) as held:
                require(held.read(path, MAXIMUM_PROBE_BYTES if parent else 64 * 1024) == raw,
                    "post_context_original_member_bytes_changed")
            entries.append((path, original_stamp))
    for path, original_stamp in entries:
        require(snapshot._file_stamp(path.lstat()) == original_stamp,
            "post_context_earlier_original_member_changed")
    owned.check()


def _after_contexts(owned, result, *, context_error, final_check, began_tick, closure_material,
                    components=(), monotonic=time.monotonic, clock=_utc_now):
    """Only caller invokes this after its entire source/code ExitStack exits."""
    require(type(owned) is _OwnedOutput and type(result) is CustodyDiagnosticReport,
        "post_context_owned_report_required")
    value = result.to_payload()
    # A prior fixed negative always dominates and must never be overwritten.
    if value["failure"] is not None:
        final_check(); owned.check()
        return result
    if context_error is None:
        try:
            final_check(); owned.check()
            _audit_closure_material(owned, result, closure_material)
            observed = clock()
            require(count.old.parallel.clock(value["completed_at"])
                <= count.old.parallel.clock(observed), "post_context_clock_backdated")
            now = monotonic()
            require(type(now) in (int, float) and type(began_tick) in (int, float)
                and began_tick <= now and now - began_tick < MAXIMUM_SECONDS,
                "finite_diagnostic_context_closure_window_exhausted")
            value.update(status="local_observations_closed_cause_unreproduced",
                context_closure="all_source_and_code_contexts_closed",
                closed_at=observed, provisional_report_sha256=result.sha256)
            closed = _seal(value)
            owned.publish("run.closed.json", closed.to_bytes())
            closed_stamp = snapshot._file_stamp(os.stat("run.closed.json",
                dir_fd=owned._anchor[2], follow_symlinks=False))
            _audit_closure_material(owned, result, closure_material,
                (("run.closed.json", closed.to_bytes(), closed_stamp),))
            final_check(); owned.check()
            # The final code audit can be lengthy: never reuse an earlier
            # metadata observation across that independently guarded pass.
            _audit_closure_material(owned, result, closure_material,
                (("run.closed.json", closed.to_bytes(), closed_stamp),))
            now = monotonic()
            require(type(now) in (int, float) and type(began_tick) in (int, float)
                and began_tick <= now and now - began_tick < MAXIMUM_SECONDS,
                "finite_diagnostic_context_closure_window_exhausted")
            require(count.old.parallel.clock(observed) <= count.old.parallel.clock(clock()),
                "post_context_final_clock_backdated")
            return closed
        except Exception as error:
            context_error = error
            failure_stage = "post_context_closure"
    else:
        failure_stage = "source_or_code_context_exit"
    value.update(status="local_diagnostic_refused", context_closure="terminal_negative",
        failure={"stage": failure_stage, "ordinal": None,
            **fixed_local_failure(context_error),
            "held_field_observation": project_held_file_mismatch(context_error, components=components)})
    refused = _seal(value)
    # Never consult now-closed or failed old source custody to preserve a negative.
    final_check(); owned.check(); owned.publish("run.refused.json", refused.to_bytes())
    return refused


def run_registered(root, *, runtime_head, actual_remote, complete_code_manifest):
    """One prospective invocation; failure_summary safely projects any error."""
    phase = "protocol_registration"
    def mark(value):
        nonlocal phase
        phase = value
    try:
        return _run_registered(root, runtime_head=runtime_head, actual_remote=actual_remote,
            complete_code_manifest=complete_code_manifest, mark=mark)
    except Exception as error:
        if type(error) is _DiagnosticStageFailure:
            raise
        raise _DiagnosticStageFailure(phase, error, seal=_FAILURE_SEAL) from None


def _run_registered(root, *, runtime_head, actual_remote, complete_code_manifest, mark):
    """Authenticate exact code and old evidence, then local NONCLAIM probes."""
    registered(); mark("platform_capability"); _require_capture_platform()
    mark("designated_driver")
    require(root == lane.ROOT and Path(__file__).absolute() == root / DRIVER, "designated_diagnostic_driver_required")
    began = time.monotonic()
    mark("lane_guard_initialization")
    guard = lane.LaneGuard(root, expected_head=runtime_head, expected_remote=actual_remote)
    mark("lane_remote_initialization"); guard.refresh()
    names = code_paths()
    mark("complete_code_manifest_shape")
    require(len(names) == 56 and type(complete_code_manifest) is dict and set(complete_code_manifest) == set(names),
        "exact_complete_56_code_manifest_required")
    owned, result, context_error, registration, components, reports, materials = None, None, None, None, (), [], []
    try:
        try:
            with ExitStack() as stack:
                mark("saved_cache_loading")
                saved = stack.enter_context(count.old.cache.load_registered_cache(root, runtime_head=runtime_head,
                    actual_remote=actual_remote, for_counts=True))
                extras = tuple(name for name in count.code_paths() if name not in count.old.cache.COUNT_CODE_FILES)
                mark("current_extra_code_loading")
                current = stack.enter_context(count.old.cache.HeldFiles(tuple(root / name for name in extras),
                    protected=False, boundary=guard.check))
                composed = count._ComposedCodeCustody(root, saved._anchor[2], current)
                mark("diagnostic_code_loading")
                extra = stack.enter_context(count.old.cache.HeldFiles((root / DRIVER,), protected=False, boundary=guard.check))
                code = _CodeCustody(root, composed, extra)
                mark("current_code_manifest_verification")
                entries, code_sha = count.old.cache._code_manifest(root, runtime_head, names, code, guard)
                require({entry["path"]: entry["sha256"] for entry in entries} == complete_code_manifest,
                    "diagnostic_committed_code_manifest_changed")
                mark("refused_prefix_loading")
                prior = stack.enter_context(snapshot.load_refused_child(root, saved.plan, guard,
                    expected_manifest_sha256=count.PREDECESSOR_MANIFEST_SHA256))
                mark("query_plan_binding"); queries = count.freeze_queries(saved.plan)
                mark("v2_zero_loading")
                zero = stack.enter_context(snapshot.load_zero_start_predecessor(root, guard, queries))
                mark("v3_zero_loading")
                v3_held, v3 = stack.enter_context(_v3_zero(root, guard, queries))
                mark("runtime_registration")
                v2_registration = count.old._parse(zero._anchor[3])["registration"]
                v3_registration = count.old._parse(v3._anchor[4])["registration"]
                registration = {"head": runtime_head, "remote": actual_remote, "branch": lane.BRANCH,
                    "ref": lane.REF, "code_files": entries, "code_file_count": 56,
                    "code_identity_sha256": code_sha, "code_manifest_sha256": hash_payload(complete_code_manifest),
                    "historical_sources": {
                        "refused_prefix": {"head": snapshot.SOURCE_HEAD,
                            "code_identity_sha256": snapshot.SOURCE_CODE_SHA256,
                            "manifest_sha256": count.PREDECESSOR_MANIFEST_SHA256},
                        "v2_zero": {**v2_registration, "claim_sha256": snapshot.ZERO_CLAIM_SHA256,
                            "refusal_sha256": snapshot.ZERO_REFUSAL_SHA256,
                            "code_manifest_sha256": snapshot.ZERO_CODE_MANIFEST_SHA256},
                        "v3_zero": {**v3_registration, "claim_sha256": V3_CLAIM_SHA256,
                            "refusal_sha256": V3_REFUSAL_SHA256}}}
                target = root / OUTPUT
                mark("output_ignore_preflight")
                require(count.old.cache._git(root, ["check-ignore", str(target)], guard).strip() == str(target).encode(),
                    "diagnostic_output_must_be_ignored")
                mark("metadata_absence_preflight"); _preflight_absent_metadata(target.parent, guard.check)
                mark("finite_preflight")
                require(time.monotonic() - began < MAXIMUM_SECONDS, "diagnostic_preflight_window_exhausted")
                mark("output_directory_creation"); directory = _prepare_capture_directory(target)
                # Owned output deliberately outlives the source/code stack so a
                # failed source-context exit can preserve a dominating negative.
                mark("output_custody_open"); owned = _OwnedOutput(directory, guard.check)
                def normal():
                    guard.check(); code.check(); saved.source_custody(); saved.code_custody(); prior.check(); zero.check(); v3.check()
                def full():
                    normal(); guard.refresh(); prior.full_check(); zero.full_check(); v3.full_check()
                    normal()
                def refusal():
                    guard.check(); code.check(); saved.code_custody()
                components = ((saved._anchor[2], "base_code"), (current, "extra_code"), (extra, "probe_code"),
                    *tuple(zip(saved._anchor[1], ("cache_source", "master_source", "matrix_source"))),
                    (zero._anchor[1], "v2_zero"), (v3_held, "v3_zero"))
                mark("local_probe_sequence")
                result = run_probe_sequence(owned=owned, normal_check=normal, refusal_check=refusal,
                    source_full_check=full, components=components, registration=registration,
                    began_tick=began, report_sink=reports.append, closure_sink=materials.append)
                mark("source_code_context_exit")
        except Exception as error:
            context_error = error
        if result is None and reports:
            result = reports[-1]
        if owned is None or result is None:
            # No invented result or successful closure for an unobserved setup.
            if context_error is not None:
                raise context_error
            raise CustodyDiagnosticRefusal("REFUSED: diagnostic_result_missing")
        mark("terminal_context_finalization")
        return _after_contexts(owned, result, context_error=context_error,
            final_check=lambda: _current_code_after_contexts(root, guard, registration),
            began_tick=began, components=components, closure_material=materials[-1] if materials else None)
    finally:
        if owned is not None:
            try:
                owned.close()
            except Exception as error:
                raise _DiagnosticStageFailure("output_custody_close", error, seal=_FAILURE_SEAL) from None
