"""Pure finite owner scope; no capability, I/O, claim or dispatch API.

Downstream protocol hashes, runtime HEAD and code bytes are separately bound
by the canonical coordinator. Including them here would create self cycles.
"""
import re
from data.hashing import hash_payload
from research.short_interest_etf import native_count_recovery_budget as plans

POLICY_SHA256 = "9d67d93ad79657031befd8849659bc20fc5834173d76a569bccb9307347e3a6c"
ROOT = "/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest"
BRANCH, REF = "codex/strategy-short-interest", "refs/heads/codex/strategy-short-interest"
OWNER_AUTHORITY, DECISION = "SI-AUTH-20261026-02", "SI-DEC-20261027-14"
BASELINE_SHA256 = "b3a8ac9057f8461bd4c450ffc911a5adac8c129ced762e33c5e56660215861e3"
REFUSED_PREFIX_SHA256 = "9be5d93cbc48527c1de98afa7e5b3599abfca63bdb9bdc5eef0f05d727aac4d7"
BODY_PROOF_SHA256 = "d423a349cc4ceb2b17a41bbf55fdf57fa725e9d65f7540afc7e53119c609e00e"
PRIOR_STARTS, PRIOR_CHARGED_BYTES = 13992, 23452681
MAXIMUM_STARTS, MAXIMUM_BYTES = 84005, 4 * 1024 ** 3
MISSING_POSITIONS, CHUNKS, POSITIONS_PER_CHUNK, EXTRA_PER_CHUNK = 67885, 133, 512, 16
MAXIMUM_TRIES, MAXIMUM_INFLIGHT, PAGE_BYTES, CHUNK_SECONDS, FILE_SECONDS = 3, 8, 2097152, 3600, 8
_CODES = frozenset(("count_source_authority_changed", "count_source_authority_unregistered",
    "count_source_prior_run_unresolved"))


class CountSourceAuthorityRefusal(ValueError): pass


def require(value, code):
    if not value: raise CountSourceAuthorityRefusal("REFUSED: " + code)


def failure_summary(error):
    code = None
    if type(error) is CountSourceAuthorityRefusal:
        args = BaseException.args.__get__(error, BaseException)
        if type(args) is tuple and len(args) == 1 and type(args[0]) is str:
            code = next((item for item in _CODES if args[0] == "REFUSED: " + item), None)
    return {"category": "local_contract_refusal" if code is not None else "unknown_local_error",
        "contract_code": code, "errno_name": None}


def policy():
    actual = (PRIOR_STARTS, PRIOR_CHARGED_BYTES, MAXIMUM_STARTS, MAXIMUM_BYTES, MISSING_POSITIONS,
        CHUNKS, POSITIONS_PER_CHUNK, EXTRA_PER_CHUNK, MAXIMUM_TRIES, MAXIMUM_INFLIGHT,
        PAGE_BYTES, CHUNK_SECONDS, FILE_SECONDS)
    expected = (13992, 23452681, 84005, 4294967296, 67885, 133, 512, 16, 3, 8, 2097152, 3600, 8)
    require(all(type(value) is int and value == target for value, target in zip(actual, expected)),
        "count_source_authority_changed")
    require(all(type(value) is str for value in (ROOT, BRANCH, REF, OWNER_AUTHORITY, DECISION))
        and (ROOT, BRANCH, REF, OWNER_AUTHORITY, DECISION) == (
        "/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest",
        "codex/strategy-short-interest", "refs/heads/codex/strategy-short-interest",
        "SI-AUTH-20261026-02", "SI-DEC-20261027-14"),
        "count_source_authority_changed")
    require(all(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value)
        for value in (BASELINE_SHA256, REFUSED_PREFIX_SHA256, BODY_PROOF_SHA256)),
        "count_source_authority_changed")
    original = plans.policy()
    require(BASELINE_SHA256 == plans.BASELINE_LEDGER_SHA256
        and original["prior_STARTs"] == PRIOR_STARTS and original["prior_charged_bytes"] == PRIOR_CHARGED_BYTES
        and original["prospective_cumulative_START_ceiling"] == MAXIMUM_STARTS
        and original["maximum_cumulative_bytes"] == MAXIMUM_BYTES
        and PRIOR_STARTS + MISSING_POSITIONS + CHUNKS * EXTRA_PER_CHUNK == MAXIMUM_STARTS,
        "count_source_authority_changed")
    return {"schema": "si-finite-count-source-authority-v1", "owner_authority": OWNER_AUTHORITY,
        "decision": DECISION, "root": ROOT, "branch": BRANCH, "origin_ref": REF,
        "baseline_ledger_sha256": BASELINE_SHA256, "refused_prefix_manifest_sha256": REFUSED_PREFIX_SHA256,
        "Main_authenticated_body_custody_proof_sha256": BODY_PROOF_SHA256,
        "plan_policy_sha256": hash_payload(original),
        "scope": "only_original_missing_native_dated_class_queries_from_genuine_baseline_no_caller_dates_or_URL",
        "protected_dates": "all_original_registered_dates_and_exclusions_unchanged",
        "source": "existing_Massive_native_reported_count_GET_original_descriptor_only",
        "credential": "protected_read_named_keychain_massive_only",
        "prior_STARTs": PRIOR_STARTS, "prior_charged_bytes": PRIOR_CHARGED_BYTES,
        "maximum_cumulative_STARTs": MAXIMUM_STARTS, "maximum_cumulative_bytes": MAXIMUM_BYTES,
        "missing_positions": MISSING_POSITIONS, "chunks": CHUNKS,
        "positions_per_chunk": POSITIONS_PER_CHUNK, "extra_STARTs_per_chunk": EXTRA_PER_CHUNK,
        "maximum_lifetime_tries": MAXIMUM_TRIES, "historical_tries_included": True,
        "maximum_inflight": MAXIMUM_INFLIGHT, "unknown_attempt_charge_bytes": PAGE_BYTES,
        "retry": "statusless_OPEN_allowlisted_transients_only_original_receipt_2_then_10_seconds",
        "hidden_retries": 0, "new_claim": "fixed_new_namespace_once_per_chunk_no_restart_reset_or_adoption",
        "maximum_chunk_seconds": CHUNK_SECONDS, "maximum_file_creation_seconds": FILE_SECONDS,
        "remote_gate": "fresh_exact_matching_origin_evidence_before_each_1_to_8_original_START_roster",
        "settlement": "only_genuine_original_closed_chunk_no_JSON_or_provisional_flag",
        "negative": "preserve_all_original_bytes_claims_STARTs_receipts_unknown_full_page_debits_no_refund",
        "blocked_preservation": "no_network_process_hold_of_original_private_bytes_and_FDs",
        "runtime": "separate_full_working_equals_committed_code_catalogue_HEAD_and_actual_matching_remote",
        "checkpoint": "original_full9_roots_same_mounted_epoch_Main_known_EXIT0_before_requalification",
        "authority": {"count_transport_only": True, "source_admitted": False, "denominator_admitted": False,
            "historical_PIT_admitted": False, "actual_input_execution_admitted": False, "ready_for_backtest": False,
            "daily_source_invocation": False, "QC_or_Safari": False, "purchases_or_new_terms": False,
            "new_credentials": False, "broker_or_trading": False, "outcome_looks": 0, "qc_attempts": 0}}


def registered_sha256():
    value = policy()
    require(type(POLICY_SHA256) is str and re.fullmatch(r"[0-9a-f]{64}", POLICY_SHA256)
        and hash_payload(value) == POLICY_SHA256, "count_source_authority_unregistered")
    return POLICY_SHA256


def require_dispatch_allowed():
    """Keep software validation separate from permission to spend again.

    The E756 run (exec13448, plan2aa15b2f) entered preservation hold. Its
    original process/terminal witness and reservation journal are unavailable.
    Empty START directories and an absent process cannot refund that run or
    establish that its private data was completely preserved. There is no
    caller flag, namespace choice, reset or retry that can release this gate.
    A separately verified accounting/preservation resolution must replace
    this operational policy before another source lease can be issued.

    The registered owner scope above stays unchanged: 84,005 cumulative
    STARTs and 4 GiB are ceilings, not an additional allocation after an
    unresolved run.
    """
    registered_sha256()
    raise CountSourceAuthorityRefusal("REFUSED: count_source_prior_run_unresolved")
