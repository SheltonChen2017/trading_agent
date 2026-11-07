"""Offline custody for the first four spent count epochs; never source admission.

No output, claim, count compiler, provider or credential route is exposed.
Ordinary access requires original live source custody. A closed summary exists
only after every source/code context and the final committed-code audit close.
"""
from __future__ import annotations

from contextlib import contextmanager, ExitStack
import math
from pathlib import Path
import time
import weakref

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_count_epoch_ledger as model
from scripts import diagnose_short_interest_count_custody as prior

count, snapshot, lane = prior.count, prior.snapshot, prior.lane
DRIVER = "scripts/load_short_interest_count_epoch_ledger.py"
MODEL = "research/short_interest_etf/native_count_epoch_ledger.py"
PROTOCOL_SHA256 = "5eae769189f3324bcc7cb256b60f4a22b3c734daa24d53f02e3c1cf5cc4dddce"
MAXIMUM_SECONDS = 1800
_SEAL = object()
_WITNESS_MINTS = weakref.WeakKeyDictionary()
_LEDGER_MINTS = weakref.WeakKeyDictionary()
_CODES = frozenset("""epoch_loader_protocol_pending_or_changed epoch_loader_designated_root_required
epoch_loader_exact58_manifest_required epoch_loader_code_changed epoch_loader_code_route_refused
epoch_loader_code_binding_changed epoch_loader_final_code_changed epoch_loader_final_identity_changed
epoch_loader_window_exhausted epoch_loader_clock_refused epoch_loader_factory_required
epoch_loader_binding_changed epoch_loader_source_not_live epoch_loader_not_closed
epoch_loader_latched_failure epoch_loader_mapping_changed epoch_loader_prior_cumulative_changed
epoch_loader_original_manifest_changed epoch_loader_model_changed
epoch_loader_closure_binding_changed
""".split())
_STAGES = frozenset("""protocol_registration platform designated_loader lane_initialization code_manifest
saved_cache_loading composed_code_loading prior_code_loading ledger_code_loading code_verification
recovery_binding refused_snapshot_loading query_plan v2_zero_loading v3_zero_loading epoch_sealing
ledger_sealing source_pre_audit consumer_body consumer_return source_final_audit source_code_context_exit
code_context_final_audit saved_context_final_audit terminal_code_audit terminal_clock closure_sealing
""".split())


class CountEpochLoaderRefusal(ValueError):
    pass


def require(value, code):
    if not value: raise CountEpochLoaderRefusal("REFUSED: " + code)


class _StageFailure(ValueError):
    def __init__(self, stage, error, *, seal):
        require(seal is _SEAL and type(stage) is str and stage in _STAGES,
            "epoch_loader_binding_changed")
        self._anchor = self._identity = stage, error
        super().__init__("count_epoch_loader_refused")


def failure_summary(error):
    stage, original = "unclassified_epoch_loader_failure", error
    if type(error) is _StageFailure:
        try:
            anchor, identity = object.__getattribute__(error, "_anchor"), object.__getattribute__(error, "_identity")
        except AttributeError: anchor, identity = None, object()
        if (anchor is identity and type(anchor) is tuple and len(anchor) == 2
            and type(anchor[0]) is str and anchor[0] in _STAGES): stage, original = anchor
    if type(original) is CountEpochLoaderRefusal:
        arguments = BaseException.args.__get__(original, BaseException)
        code = None
        if type(arguments) is tuple and len(arguments) == 1 and type(arguments[0]) is str:
            code = next((item for item in _CODES if arguments[0] == "REFUSED: " + item), None)
        fixed = {"category": "local_contract_refusal", "errno_name": None, "contract_code": code}
    elif type(original) is model.CountEpochLedgerRefusal: fixed = model.failure_summary(original)
    else: fixed = prior.fixed_local_failure(original)
    return {"stage": stage, **fixed, "held_field_observation": prior.project_held_file_mismatch(original)}


def authority():
    return {"source_only": True, "spent_epoch_accounting_only": True, "provider_HTTP": 0,
        "credential_reads": 0, "new_capture_claims": 0, "new_START_debits": 0,
        "new_charged_bytes": 0, "source_admitted": False, "denominator_admitted": False,
        "historical_PIT_admitted": False, "actual_input_execution_admitted": False,
        "ready_for_backtest": False,
        "outcome_looks": 0, "qc_attempts": 0, "trading_authority": False}


def code_paths(): return tuple(sorted((*prior.code_paths(), MODEL, DRIVER)))


def protocol():
    return {"schema": "si-registered-count-epoch-ledger-loader-v1", "driver": DRIVER, "model": MODEL,
        "model_scope_sha256": model._scope_sha256(),
        "decision": "SI-DEC-20261025-02", "maximum_seconds": MAXIMUM_SECONDS,
        "epochs": ["original48", "refused13944", "v2zero", "v3zero"],
        "original_parent_manifest_sha256": count.old.PARENT_MANIFEST_SHA256,
        "original_parent_external_claim_sha256": count.old.PARENT_CLAIM_SHA256,
        "refused_child_FINAL_manifest_sha256": count.PREDECESSOR_MANIFEST_SHA256,
        "refused_child_external_claim_sha256": snapshot.SOURCE_CLAIM_SHA256,
        "refused_child_terminal_refusal_sha256": snapshot.SOURCE_REFUSAL_SHA256,
        "v2_external_claim_sha256": snapshot.ZERO_CLAIM_SHA256,
        "v2_terminal_refusal_sha256": snapshot.ZERO_REFUSAL_SHA256,
        "v3_external_claim_sha256": prior.V3_CLAIM_SHA256,
        "v3_terminal_refusal_sha256": prior.V3_REFUSAL_SHA256,
        "source_replay": "original_audited_cache_prefix_FULL_FINAL_manifest_raw_receipt_unknown_fullpage_history_loaders",
        "mapping": "genuine_RecoveryBinding_parent_child_plan_and_source_selected_original_tickets",
        "positive_chunks_admitted": 0, "claim_restart_retry_allowed": False,
        "closure": "live_access_then_full_original_proofs_each_context_exit_all_success_then_fresh58_committed_code_audit_and_closed_summary",
        "code_paths": list(code_paths()), "authority": authority()}


def registered():
    require(len(code_paths()) == len(set(code_paths())) == 58
        and hash_payload(protocol()) == PROTOCOL_SHA256 and MAXIMUM_SECONDS == 1800,
        "epoch_loader_protocol_pending_or_changed")


class _CodeCustody:
    def __init__(self, root, composed, prior_code, ledger_code):
        require(type(composed) is count._ComposedCodeCustody
            and all(type(item) is count.old.cache.HeldFiles for item in (prior_code, ledger_code)),
            "epoch_loader_code_binding_changed")
        self._anchor = self._identity = root, composed, prior_code, ledger_code

    def check(self):
        require(type(self) is _CodeCustody and self._anchor is self._identity,
            "epoch_loader_code_binding_changed")
        for held in self._anchor[1:]: held.check()

    def read(self, path, maximum):
        self.check(); root, composed, prior_code, ledger_code = self._anchor
        require(path in tuple(root / name for name in code_paths()), "epoch_loader_code_route_refused")
        held = prior_code if path == root / prior.DRIVER else ledger_code if path in (
            root / MODEL, root / DRIVER) else composed
        raw = held.read(path, maximum); self.check(); return raw


@contextmanager
def _checked_code(paths, boundary, phase):
    held = count.old.cache.HeldFiles(paths, protected=False, boundary=boundary)
    try: yield held
    finally:
        try:
            held.check()
        except BaseException:
            phase[0] = "code_context_final_audit"; raise
        finally:
            try: held.close()
            except BaseException:
                phase[0] = "code_context_final_audit"; raise


def _final_code(root, guard, registration, boundary):
    guard.refresh(); boundary()
    entries = registration["code_files"]
    require(tuple(row["path"] for row in entries) == code_paths() and len(entries) == 58
        and registration["head"] == guard.binding()[1] and registration["remote"] == guard.binding()[2],
        "epoch_loader_exact58_manifest_required")
    stamps = []
    for row in entries:
        path = root / row["path"]
        with count.old.cache.HeldFiles((path,), protected=False, boundary=boundary) as held:
            stamp = snapshot._file_stamp(path.lstat()); raw = held.read(path, 8 * 1024 ** 2)
            committed = count.old.cache._git(root, ["show", registration["head"] + ":" + row["path"]], guard)
            require(type(committed) is bytes and len(committed) <= 8 * 1024 ** 2
                and hash_bytes(raw) == hash_bytes(committed) == row["sha256"], "epoch_loader_final_code_changed")
            held.check(); stamps.append((path, stamp))
    for path, stamp in stamps:
        boundary(); require(snapshot._file_stamp(path.lstat()) == stamp, "epoch_loader_final_code_changed")
    require(hash_payload({row["path"]: row["sha256"] for row in entries}) == registration["code_manifest_sha256"]
        and hash_payload({"git_commit": registration["head"], "files": entries}) == registration["code_identity_sha256"],
        "epoch_loader_final_identity_changed")
    guard.refresh(); boundary()


class _ClosureWitness:
    __slots__ = ("_parts", "_identity", "__weakref__")

    def __init__(self, anchor, raw, *, seal):
        require(type(self) is _ClosureWitness and self not in _WITNESS_MINTS
            and seal is _SEAL and type(raw) is bytes, "epoch_loader_factory_required")
        value = count.old._parse(raw)
        require(type(value) is dict and type(value.get("started_at")) is str
            and type(value.get("closed_at")) is str, "epoch_loader_closure_binding_changed")
        clocks = value["started_at"], value["closed_at"]
        require(count.old.parallel.clock(clocks[0]) <= count.old.parallel.clock(clocks[1]),
            "epoch_loader_clock_refused")
        self._parts = self._identity = anchor, raw, hash_bytes(raw), anchor[0].sha256, PROTOCOL_SHA256, clocks
        _WITNESS_MINTS[self] = self._parts

    def payload(self, anchor):
        require(type(self) is _ClosureWitness, "epoch_loader_closure_binding_changed")
        try:
            parts, identity = object.__getattribute__(self, "_parts"), object.__getattribute__(self, "_identity")
        except AttributeError:
            raise CountEpochLoaderRefusal("REFUSED: epoch_loader_closure_binding_changed") from None
        require(parts is identity and _WITNESS_MINTS.get(self) is parts and type(parts) is tuple
            and len(parts) == 6 and parts[0] is anchor and type(parts[1]) is bytes
            and count.old._digest(parts[2]) and hash_bytes(parts[1]) == parts[2]
            and count.old._digest(parts[3]) and parts[3] == anchor[0].sha256
            and type(parts[4]) is str and parts[4] == PROTOCOL_SHA256,
            "epoch_loader_closure_binding_changed")
        value, original = count.old._parse(parts[1]), count.old._parse(anchor[1])
        expected = anchor[0].public_summary()
        keys = set(expected) | {"schema", "status", "closed_at", "started_at", "loader_protocol_sha256",
            "head", "remote", "code_identity_sha256", "code_manifest_sha256", "model_ledger_sha256",
            "provisional_ledger_sha256", "authority"}
        require(type(value) is dict and set(value) == keys
            and type(parts[5]) is tuple and len(parts[5]) == 2
            and all(type(item) is str for item in parts[5])
            and value.get("started_at") == parts[5][0] == original["registration"]["started_at"]
            and value.get("closed_at") == parts[5][1]
            and count.old.parallel.clock(parts[5][0]) <= count.old.parallel.clock(parts[5][1])
            and value.get("schema") == "si-count-epoch-ledger-context-closed-v1"
            and value.get("status") == "closed_offline_source_only_slice"
            and value.get("provisional_ledger_sha256") == anchor[3]
            and value.get("loader_protocol_sha256") == PROTOCOL_SHA256
            and value.get("head") == original["registration"]["head"]
            and value.get("remote") == original["registration"]["remote"]
            and value.get("code_identity_sha256") == original["registration"]["code_identity_sha256"]
            and value.get("code_manifest_sha256") == original["registration"]["code_manifest_sha256"]
            and value.get("model_ledger_sha256") == anchor[0].sha256
            and all(count.old._exact(value.get(key), item) for key, item in expected.items()
                if key not in {"schema", "authority"})
            and count.old._exact(value.get("authority"), authority()), "epoch_loader_closure_binding_changed")
        return value


class RegisteredCountEpochLedger:
    """Original-source-held wrapper; a provisional payload is never closure."""
    __slots__ = ("_anchor", "_identity", "_state", "_state_identity", "_failed", "_closure", "_closure_identity", "__weakref__")

    def __init__(self): raise CountEpochLoaderRefusal("REFUSED: epoch_loader_factory_required")

    def _latch(self):
        object.__setattr__(self, "_failed", True)
        try: original = object.__getattribute__(self, "_state_identity")
        except AttributeError: return
        if type(original) is dict: original["phase"] = "FAILED"

    def _binding(self):
        try:
            anchor, identity, state, original, failed, closure, original_closure = (object.__getattribute__(self, name)
                for name in ("_anchor", "_identity", "_state", "_state_identity", "_failed", "_closure", "_closure_identity"))
        except AttributeError:
            raise CountEpochLoaderRefusal("REFUSED: epoch_loader_binding_changed") from None
        minted = _LEDGER_MINTS.get(self) if type(self) is RegisteredCountEpochLedger else None
        require(type(self) is RegisteredCountEpochLedger and anchor is identity and type(anchor) is tuple
            and type(minted) is tuple and len(minted) == 3 and minted[0] is anchor
            and minted[1] is original and minted[2] is closure
            and len(anchor) == 4 and type(anchor[1]) is bytes and count.old._digest(anchor[3])
            and hash_bytes(anchor[1]) == anchor[3]
            and type(anchor[0]) is model.CountEpochLedger and callable(anchor[2])
            and state is original and type(state) is dict
            and set(state) == {"phase"} and type(state["phase"]) is str
            and state["phase"] in {"LIVE", "CLOSING", "FAILED", "CLOSED"} and type(failed) is bool,
            "epoch_loader_binding_changed")
        require(failed is False and state["phase"] != "FAILED", "epoch_loader_latched_failure")
        anchor[0]._guard()
        require(closure is original_closure and (closure is None or type(closure) is _ClosureWitness),
            "epoch_loader_closure_binding_changed")
        if closure is not None: closure.payload(anchor)
        require((state["phase"] == "CLOSED") == (closure is not None), "epoch_loader_closure_binding_changed")
        return anchor, state

    def _live(self):
        try:
            anchor, state = self._binding()
            require(state["phase"] == "LIVE", "epoch_loader_source_not_live")
            anchor[2](); return anchor
        except BaseException:
            self._latch(); raise

    @property
    def sha256(self): return self._live()[3]

    def private_payload(self): return count.old._parse(self._live()[1])

    def public_summary(self):
        anchor = self._live()
        return {**anchor[0].public_summary(), "custody_status": "source_held_provisional",
            "loader_protocol_sha256": PROTOCOL_SHA256, "authority": authority()}

    def closed_summary(self):
        try:
            unused, state = self._binding()
            require(state["phase"] == "CLOSED", "epoch_loader_not_closed")
            return self._closure.payload(self._anchor)
        except BaseException:
            self._latch(); raise

    def closure_receipt(self): return self.closed_summary()


def _bind_ledger(ledger, registration, normal):
    require(type(ledger) is model.CountEpochLedger, "epoch_loader_model_changed")
    value = object.__new__(RegisteredCountEpochLedger)
    raw = canonical_json({"schema": "si-source-held-count-epoch-ledger-v1",
        "status": "source_held_provisional", "loader_protocol_sha256": PROTOCOL_SHA256,
        "registration": registration, "ledger": ledger.private_payload(), "authority": authority()}).encode()
    anchor = ledger, raw, normal, hash_bytes(raw)
    state = {"phase": "LIVE"}
    for name, item in (("_anchor", anchor), ("_identity", anchor), ("_state", state),
        ("_state_identity", state), ("_failed", False), ("_closure", None),
        ("_closure_identity", None)): object.__setattr__(value, name, item)
    _LEDGER_MINTS[value] = anchor, state, None
    value._live(); return value


def _require_prior_cumulative(original, child, zero, v3):
    """Exact production linkage; toy lifecycle tests name this sole domain seam."""
    totals = [inventory.to_payload() for inventory in (original, child)]
    starts = sum(row["attempts_started"] for row in totals)
    charged = sum(row["charged_response_bytes"] for row in totals)
    for claim_raw, refusal_raw in ((zero._anchor[3], zero._anchor[4]), (v3._anchor[4], v3._anchor[5])):
        claim, negative = count.old._parse(claim_raw), count.old._parse(refusal_raw)
        require(type(claim.get("prior_STARTs")) is int and claim["prior_STARTs"] == starts
            and type(claim.get("prior_charged_bytes")) is int and claim["prior_charged_bytes"] == charged
            and type(negative.get("cumulative_STARTs")) is int and negative["cumulative_STARTs"] == starts
            and type(negative.get("cumulative_charged_bytes")) is int
            and negative["cumulative_charged_bytes"] == charged, "epoch_loader_prior_cumulative_changed")


def _epochs(source, binding, refused, zero, v3):
    binding.check(); refused.check(); zero.full_check(); v3.full_check()
    original, child = refused._prefix.inventory, refused.inventory
    require(original._plan._queries is source.query_plan
        and original._plan.sha256 == binding.parent_plan.sha256
        and child._plan.sha256 == binding.child_plan.sha256,
        "epoch_loader_mapping_changed")
    require(hash_bytes(refused.manifest_raw) == count.PREDECESSOR_MANIFEST_SHA256,
        "epoch_loader_original_manifest_changed")
    _require_prior_cumulative(original, child, zero, v3)
    lineages = (
        (("full_manifest", count.old.PARENT_MANIFEST_SHA256), ("external_claim", count.old.PARENT_CLAIM_SHA256),
            ("protocol", count.old.original.PROTOCOL_SHA256), ("historical_code", count.old.PARENT_CODE_SHA256)),
        (("full_manifest", count.PREDECESSOR_MANIFEST_SHA256), ("external_claim", snapshot.SOURCE_CLAIM_SHA256),
            ("terminal_refusal", snapshot.SOURCE_REFUSAL_SHA256), ("protocol", count.old.PROTOCOL_SHA256),
            ("historical_code", snapshot.SOURCE_CODE_SHA256)),
        (("external_claim", snapshot.ZERO_CLAIM_SHA256), ("terminal_refusal", snapshot.ZERO_REFUSAL_SHA256),
            ("protocol", snapshot.ZERO_PROTOCOL), ("historical_code_manifest", snapshot.ZERO_CODE_MANIFEST_SHA256)),
        (("external_claim", prior.V3_CLAIM_SHA256), ("terminal_refusal", prior.V3_REFUSAL_SHA256),
            ("protocol", count.PROTOCOL_SHA256),
            ("historical_code", count.old._parse(v3._anchor[4])["registration"]["code_identity_sha256"])))
    return tuple(model._seal_registered_epoch_inventory(source, inventory, epoch_id=epoch_id,
        proof_lineage=lineage) for epoch_id, inventory, lineage in zip(
            ("original48", "refused13944", "v2zero", "v3zero"), (original, child, None, None), lineages))


@contextmanager
def load_registered_count_epoch_ledger(root, *, runtime_head, actual_remote, complete_code_manifest):
    """Read-only first slice; successful context return alone seals closure."""
    phase, loaded, body_error, return_error = ["protocol_registration"], None, None, None
    try:
        registered(); phase[0] = "platform"; prior._require_capture_platform()
        phase[0] = "designated_loader"
        require(root == lane.ROOT and Path(__file__).absolute() == root / DRIVER,
            "epoch_loader_designated_root_required")
        began, previous = time.monotonic(), [None]
        started_at = prior._utc_now(); started_clock = count.old.parallel.clock(started_at)
        def window():
            now = time.monotonic()
            require(type(began) in (int, float) and type(now) in (int, float)
                and math.isfinite(began) and math.isfinite(now) and 0 <= began <= now <= 2 ** 53
                and (previous[0] is None or previous[0] <= now) and now - began < MAXIMUM_SECONDS,
                "epoch_loader_window_exhausted")
            previous[0] = now
        phase[0] = "lane_initialization"
        guard = lane.LaneGuard(root, expected_head=runtime_head, expected_remote=actual_remote); guard.refresh()
        def boundary(): guard.check(); registered(); window()
        boundary()
        phase[0] = "code_manifest"
        require(type(complete_code_manifest) is dict and set(complete_code_manifest) == set(code_paths()),
            "epoch_loader_exact58_manifest_required")
        with ExitStack() as stack:
            phase[0] = "saved_cache_loading"
            saved = stack.enter_context(count.old.cache.load_registered_cache(root,
                runtime_head=runtime_head, actual_remote=actual_remote, for_counts=True))
            def saved_exit_audit():
                try: saved.source_custody(); saved.code_custody(); guard.refresh(); boundary()
                except BaseException:
                    phase[0] = "saved_context_final_audit"; raise
            stack.callback(saved_exit_audit)
            phase[0] = "composed_code_loading"
            extras = tuple(name for name in count.code_paths() if name not in count.old.cache.COUNT_CODE_FILES)
            extra = stack.enter_context(_checked_code(tuple(root / name for name in extras), boundary, phase))
            composed = count._ComposedCodeCustody(root, saved._anchor[2], extra)
            phase[0] = "prior_code_loading"
            prior_code = stack.enter_context(_checked_code((root / prior.DRIVER,), boundary, phase))
            phase[0] = "ledger_code_loading"
            ledger_code = stack.enter_context(_checked_code((root / MODEL, root / DRIVER), boundary, phase))
            code = _CodeCustody(root, composed, prior_code, ledger_code)
            phase[0] = "code_verification"
            entries, identity = count.old.cache._code_manifest(root, runtime_head, code_paths(), code, guard)
            require({row["path"]: row["sha256"] for row in entries} == complete_code_manifest,
                "epoch_loader_code_changed")
            source = saved.plan; phase[0] = "recovery_binding"; binding = count.old.freeze_recovery(source)
            phase[0] = "refused_snapshot_loading"
            refused = stack.enter_context(snapshot.load_refused_child(root, source, guard,
                expected_manifest_sha256=count.PREDECESSOR_MANIFEST_SHA256))
            phase[0] = "query_plan"; queries = count.freeze_queries(source)
            phase[0] = "v2_zero_loading"; zero = stack.enter_context(snapshot.load_zero_start_predecessor(root, guard, queries))
            phase[0] = "v3_zero_loading"; unused_held, v3 = stack.enter_context(prior._v3_zero(root, guard, queries))
            registration = {"head": runtime_head, "remote": actual_remote, "branch": lane.BRANCH,
                "started_at": started_at,
                "ref": lane.REF, "code_files": entries, "code_file_count": 58,
                "code_manifest_sha256": hash_payload(complete_code_manifest), "code_identity_sha256": identity}
            def normal():
                boundary(); code.check(); saved.source_custody(); saved.code_custody()
                binding.check(); refused.check(); zero.check(); v3.check()
            def full():
                normal(); guard.refresh(); refused.full_check(); zero.full_check(); v3.full_check(); normal()
            phase[0] = "epoch_sealing"; epochs = _epochs(source, binding, refused, zero, v3)
            phase[0] = "ledger_sealing"; ledger = model.seal_registered_count_epoch_ledger(source, epochs)
            phase[0] = "source_pre_audit"; full(); loaded = _bind_ledger(ledger, registration, normal)
            original_state = loaded._state_identity
            try:
                phase[0] = "consumer_body"; yield loaded
            except BaseException as error:
                body_error = error; loaded._latch(); raise
            finally:
                if body_error is None:
                    try:
                        unused_anchor, returned_state = loaded._binding()
                        require(returned_state is original_state and returned_state["phase"] == "LIVE",
                            "epoch_loader_source_not_live")
                        original_state["phase"] = "CLOSING"
                    except BaseException as error:
                        return_error = error; loaded._latch()
                phase[0] = "source_final_audit"; full()
                phase[0] = "source_code_context_exit"
                if return_error is not None: raise return_error
        phase[0] = "terminal_code_audit"; _final_code(root, guard, registration, boundary)
        phase[0] = "terminal_clock"; at = prior._utc_now()
        require(started_clock <= count.old.parallel.clock(at), "epoch_loader_clock_refused"); boundary()
        phase[0] = "closure_sealing"
        unused_anchor, final_state = loaded._binding()
        require(loaded._failed is False and loaded._state is loaded._state_identity
            and final_state is original_state and final_state["phase"] == "CLOSING",
            "epoch_loader_latched_failure")
        closed = {**ledger.public_summary(), "schema": "si-count-epoch-ledger-context-closed-v1",
            "status": "closed_offline_source_only_slice", "closed_at": at,
            "started_at": started_at,
            "loader_protocol_sha256": PROTOCOL_SHA256, "head": runtime_head, "remote": actual_remote,
            "code_identity_sha256": registration["code_identity_sha256"],
            "code_manifest_sha256": registration["code_manifest_sha256"], "model_ledger_sha256": ledger.sha256,
            "provisional_ledger_sha256": loaded._anchor[3], "authority": authority()}
        closure_raw = canonical_json(closed).encode(); boundary()
        require(count.old.parallel.clock(at) <= count.old.parallel.clock(prior._utc_now()),
            "epoch_loader_clock_refused")
        window()
        closure = _ClosureWitness(loaded._anchor, closure_raw, seal=_SEAL)
        window()
        _LEDGER_MINTS[loaded] = loaded._anchor, original_state, closure
        loaded._closure = loaded._closure_identity = closure
        loaded._state_identity["phase"] = "CLOSED"
    except BaseException as error:
        if loaded is not None: loaded._latch()
        if isinstance(error, Exception):
            if type(error) is _StageFailure: raise
            stage = "consumer_body" if error is body_error else "consumer_return" if error is return_error else phase[0]
            raise _StageFailure(stage, error, seal=_SEAL) from None
        raise
