"""Inert public AO transport facts; no credential, data or operational grant."""
import hashlib
import json

_FACT = "{\"schema\":\"arv2-r326-AO-verified-resolver-observation-v1\",\"expected_head\":\"bccc394a3478aa260bb0948c8dc67d4f3051c366\",\"caller_sha256\":\"cd7fe6608ba4b56a748efe8fc1f738d94d6dbfd02da6f724b57644118db4d57d\",\"profile_sha256\":\"e60af01eb261bb1195000957315f420577d6558d52341fee9c24465ff2e1a041\",\"producer\":{\"actual_exit\":0,\"bound\":null,\"completion_observed_at\":\"2026-10-27T12:48:20.819302Z\",\"dispatched_at\":\"2026-10-27T12:48:12.355193Z\",\"spawn_observed\":true,\"stderr_bytes\":0,\"stderr_sha256\":\"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\",\"stdout_bytes\":2776,\"stdout_sha256\":\"ff790b98087a57c321841a08550d3cd4f50343260d512446d39dd16ec8ff6789\"},\"validator\":{\"actual_exit\":0,\"bound\":null,\"completion_observed_at\":\"2026-10-27T12:48:24.604211Z\",\"dispatched_at\":\"2026-10-27T12:48:20.819546Z\",\"spawn_observed\":true,\"stderr_bytes\":0,\"stderr_sha256\":\"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\",\"stdout_bytes\":2776,\"stdout_sha256\":\"ff790b98087a57c321841a08550d3cd4f50343260d512446d39dd16ec8ff6789\"},\"child\":{\"actual_exit\":0,\"bound\":null,\"completion_observed_at\":\"2026-10-27T12:48:20.588981Z\",\"dispatched_at\":\"2026-10-27T12:48:15.996830Z\",\"spawn_observed\":true,\"stderr_bytes\":0,\"stderr_sha256\":\"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\",\"stdout_bytes\":1191,\"stdout_sha256\":\"665a0c7b63768be8abec681117bf66901e52c18dc533997a8d9a05778aea7aad\"},\"report\":{\"byte_count\":2360,\"sha256\":\"a769ed73c93ea4a18d1882aef19dad7af0fd0d901df22be88725a252ca410e75\"},\"journal\":{\"byte_count\":1265,\"sha256\":\"fd89d3d877740c546ee3d1a3012f96f9cc02a9035a797320b5c9547438ec14e4\"},\"stages\":[\"dns\",\"tcp\",\"tls\",\"http\"],\"DNS\":{\"count\":4,\"families\":{\"AF_INET\":2,\"AF_INET6\":2,\"unsupported\":0},\"ordered_inventory_sha256\":\"c9f706a32784e5f18ae0f1776f2ba30f3d3d68e16f68899f8320d60faef4d632\",\"selected_family\":\"AF_INET6\",\"selected_ordinal\":0},\"TLS\":{\"peer_DER_sha256\":\"bd034affabd578a8bdc65e445e28976e25bad12ef95205ff13330e042de23114\",\"version\":\"TLSv1.3\"},\"HEAD_send_attempts\":1,\"first_HTTP_status\":404,\"status_line_byte_count\":24,\"verified_policy_sha256\":\"b7e48e4fb1c0268e11d4102050b04a6ad7d96247c2852f8ec3b87ebf1920b5b6\",\"only_policy_exception\":\"/private/var/run/mDNSResponder\",\"physical_packets\":null,\"credential_access\":false,\"provider_data_endpoint_called\":false,\"price_input_admitted\":false,\"historical_failure_cause_proven\":false,\"fresh_operation_granted\":false,\"point_in_time_proven\":false,\"formal_forward_ready\":false,\"paper_or_live_ready\":false}"

def observed_fact():
    return json.loads(_FACT)

def profile_record():
    raw = json.dumps(observed_fact(), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
    return {"schema": "arv2-r326-AO-public-binding-v1",
        "observed_fact_sha256": hashlib.sha256(raw).hexdigest(),
        "new_operation_or_read_granted": False,
        "historical_failure_cause_proven": False,
        "data_endpoint_or_entitlement_proven": False,
        "point_in_time_proven": False, "formal_forward_ready": False,
        "paper_or_live_ready": False}
