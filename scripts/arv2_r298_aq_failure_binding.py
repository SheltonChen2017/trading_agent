"""Inert actual AQ failure facts; no DATA/control read or retry authority."""
import hashlib
import json

_FACT = "{\"schema\":\"arv2-r326-AQ-public-failure-binding-v1\",\"binding\":{\"schema\":\"arv2-r298-offline-common-price-sidecar-aq-v1\",\"expected_head\":\"95a2d5a186566831ad020f7503a74a4c01147869\",\"caller_sha256\":\"a454259816eb5ad97aa3d4143d65abc8c96f7c77331071c864f696f396c8c056\",\"profile_sha256\":\"136dd2c838b06eaa22ae61f362ffb1b7a3aeb9bc1f21953d97408550d85291bc\"},\"producer\":{\"actual_exit\":2,\"bound\":null,\"completion_observed_at\":\"2026-10-27T14:14:10.805486+00:00\",\"dispatched_at\":\"2026-10-27T14:14:07.049662+00:00\",\"spawn_observed\":true,\"stderr_bytes\":0,\"stderr_sha256\":\"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\",\"stdout_bytes\":327,\"stdout_sha256\":\"38e2561181b2cdd62e3327440748949fb4a64b1fcea18377d46948244de60892\"},\"validator\":{\"actual_exit\":71,\"bound\":null,\"completion_observed_at\":\"2026-10-27T14:14:10.814049+00:00\",\"dispatched_at\":\"2026-10-27T14:14:10.805670+00:00\",\"spawn_observed\":true,\"stderr_bytes\":53,\"stderr_sha256\":\"d34a4e4359a4dc36526cf5b363da32f7b7594a3a09eea17cbdfd6425b052d93e\",\"stdout_bytes\":0,\"stdout_sha256\":\"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\"},\"finite_stdout_reconstruction\":{\"method\":\"unique_canonical_closed_finite_envelope_SHA256_and_size_join\",\"failure_code\":\"os_error\",\"native_reader_accepted\":false},\"validator_stderr_reconstruction\":{\"method\":\"exact_public_OS_message_SHA256_and_size_join\",\"finite_code\":\"native_sandbox_apply_operation_not_permitted\"},\"accepted_sidecar\":false,\"allocation_and_private_read_stage_known\":false,\"attempt_spent\":true,\"old_control_read_granted\":false,\"new_operation_granted\":false,\"price_input_admitted\":false,\"point_in_time_proven\":false,\"formal_forward_ready\":false,\"paper_or_live_ready\":false}"

def observed_fact():
    return json.loads(_FACT)

def profile_record():
    value = observed_fact()
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
    return {"schema": "arv2-r326-AQ-failure-anchor-profile-v1",
        "observed_fact_sha256": hashlib.sha256(raw).hexdigest(),
        "old_control_read_granted": False, "new_operation_granted": False,
        "price_input_admitted": False, "formal_forward_ready": False, "paper_or_live_ready": False}
