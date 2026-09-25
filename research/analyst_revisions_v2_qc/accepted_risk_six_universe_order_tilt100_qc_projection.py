"""R193 100% stock-weight tilt from the exact R192 settlement source.

The 16-file order source and R191 matched settlement profile are authenticated
before narrow counted replacements. This is a backtest-only source projection;
it performs no cloud action or result read.
"""

import dataclasses
import hashlib
import json

from . import accepted_risk_six_universe_order_qc_projection as _base
from . import accepted_risk_six_universe_order_settlement_qc_projection as _r192


class SixUniverseTilt100QcProjectionError(ValueError):
    """The R193 predecessor, profile, source, or exact pin changed."""


TILT100_ROLE = "matched_revision_tilt100"
TILT100_VARIANT = "cap90_matched_revision_tilt100_settlement_v1"
TILT100_PROFILE_SCHEMA = "arv2-six-universe-order-tilt100-settlement-profile-v1"
TILT100_PROFILE_ID = "arv2-six-universe-order-matched-revision-tilt100-settlement-v1"
TILT100_SUMMARY_SCHEMA = "arv2-six-universe-order-tilt100-settlement-summary-v1"
TILT100_DECISION_TARGET_SCHEMA = "arv2-six-universe-order-tilt100-decision-target-v1"
TILT100_TARGET_PATH_SCHEMA = "arv2-six-universe-order-tilt100-target-path-v1"
PROJECTION_SCHEMA = "arv2-six-universe-order-qc-projection-tilt100-settlement-v1"
PROJECTION_ID_PREFIX = "arv2-six-universe-order-tilt100-settlement-qc-projection-"

PINNED_R191_PROFILE_SHA256 = (
    "f650044a704a4a0522e4c95c065a3eda3d3de22e8c5425579e04155c88f5220c"
)
PINNED_R192_PROJECTION_SHA256 = (
    "8f5db5bf895a51683d9c7c2a4848c302aeac01284317ceaab9e22d9c9b3c3b09"
)
PINNED_R192_PROFILE_SHA256 = (
    "2c149ea159473f7976f10daa5ad74b0a3f8d0bf6992911e96a58b3a7a490f923"
)
PINNED_R192_SOURCE_MANIFEST_SHA256 = (
    "023707c5709525247ac88384e5ea356655ef5501fb7f07e19b158642456224ae"
)
PINNED_R192_TOTAL_SOURCE_BYTES = 425_742
PINNED_R192_FILE_SHA256S = {
    "accepted_risk_six_universe_order_tilt_targets.py": (
        "efecce41bd727558ac53768ffd68b0b750a27cb20b78386f1c0be5c600f47f2d"
    ),
    "accepted_risk_six_universe_order_tilt_qc_runtime.py": (
        "e2e2e7d562a815db357613063dc63bd294f364c0406242b462c4bcbfe050778a"
    ),
    "main.py": "f1f84068338d14b57ca0ecec7239e1d2f9a47ac7a333a97eb57d2d31aa64a56b",
}
PINNED_R192_FILE_BYTE_COUNTS = {
    "accepted_risk_six_universe_order_tilt_targets.py": 20_749,
    "accepted_risk_six_universe_order_tilt_qc_runtime.py": 7_849,
    "main.py": 6_573,
}

# Exact R192 settlement source occurrences; no shared source is rewritten.
_TRANSFORMS = {
    "accepted_risk_six_universe_order_tilt_targets.py": (
        ('TILT_ROLE = "matched_revision_tilt80"',
         'TILT_ROLE = "matched_revision_tilt100"', 1),
        ('MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION = Decimal("0.80")',
         'MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION = Decimal("1.00")', 1),
        ('DECISION_TARGET_SCHEMA = "arv2-six-universe-order-tilt80-decision-target-v1"',
         f'DECISION_TARGET_SCHEMA = "{TILT100_DECISION_TARGET_SCHEMA}"', 1),
        ('TARGET_PATH_SCHEMA = "arv2-six-universe-order-tilt80-target-path-v1"',
         f'TARGET_PATH_SCHEMA = "{TILT100_TARGET_PATH_SCHEMA}"', 1),
        ('bounded by 80% of its own post-cap',
         'bounded by 100% of its own post-cap', 1),
        ('"maximum_stock_weight_change_fraction": "0.80"',
         '"maximum_stock_weight_change_fraction": "1.00"', 1),
        ('"arv2-six-universe-order-tilt80-target-path-"',
         '"arv2-six-universe-order-tilt100-target-path-"', 1),
    ),
    "accepted_risk_six_universe_order_tilt_qc_runtime.py": (
        ('TILT_VARIANT = "cap90_matched_revision_tilt80_settlement_v1"',
         f'TILT_VARIANT = "{TILT100_VARIANT}"', 1),
        ('TILT_PROFILE_SCHEMA = "arv2-six-universe-order-tilt80-settlement-profile-v1"',
         f'TILT_PROFILE_SCHEMA = "{TILT100_PROFILE_SCHEMA}"', 1),
        ('TILT_SUMMARY_SCHEMA = "arv2-six-universe-order-tilt80-settlement-summary-v1"',
         f'TILT_SUMMARY_SCHEMA = "{TILT100_SUMMARY_SCHEMA}"', 1),
        ('"profile_id": "arv2-six-universe-order-matched-revision-tilt80-settlement-v1"',
         f'"profile_id": "{TILT100_PROFILE_ID}"', 1),
        ('"maximum_stock_weight_change_fraction": "0.80"',
         '"maximum_stock_weight_change_fraction": "1.00"', 2),
    ),
    "main.py": (
        ('class ARV2SixUniverseOrderTilt80Algorithm(QCAlgorithm):',
         'class ARV2SixUniverseOrderTilt100Algorithm(QCAlgorithm):', 1),
        ("role='matched_revision_tilt80',", "role='matched_revision_tilt100',", 1),
        ("variant='cap90_matched_revision_tilt80_settlement_v1',",
         f"variant='{TILT100_VARIANT}',", 1),
    ),
}

# Exact R193 output pins from the reviewed 16-file projected closure.
PINNED_TILT100_PROFILE_SHA256 = (
    "c938f20cbcfe2bc3b4d60728b9ec7c9a450a88e5ba3fd0fe43a4c90985abc243"
)
PINNED_TILT100_PROJECTION_SHA256 = (
    "473163be0d2b9281c4c18a2a1565146536d93eab8226dcf5a90556cece77bfb9"
)
PINNED_TILT100_SOURCE_MANIFEST_SHA256 = (
    "2489eb7102ab7d6dd3f555d2aae5bc2c46df6816bd0d3ad4b78be77238d68abb"
)
PINNED_TILT100_TOTAL_SOURCE_BYTES = 425_754
PINNED_TILT100_FILE_SHA256S = {
    "accepted_risk_order_level_core.py": (
        "24542b1c8a6980f9e6390d8cfc22bdace863042c900e6ca2f2cdab960dd07545"
    ),
    "accepted_risk_order_level_forced_exit.py": (
        "21ef6978d7c26b833b0ec553298584c360f03d602f3c244f2fc8645bd113ec3f"
    ),
    "accepted_risk_order_level_input_runtime.py": (
        "a08098648d98a95736471113d48a3e1183f04969d2c2561b1a4f5d6bfc80d7ee"
    ),
    "accepted_risk_preliminary_qc_figi.py": (
        "4ee85d92126e31d3bde9acaffb992a54cf44b02efa876157597b876086da7ca9"
    ),
    "accepted_risk_preliminary_rating_evaluator.py": (
        "2fb9bc8a8f74e37b57acb97f4d20b5820be04b9ee470fc2f34b3a8ea2c804910"
    ),
    "accepted_risk_preliminary_rating_policy.py": (
        "7d45e0c294d03b5775ca6bd911043ea1e9b819e448eb7107fcbf0a2f162e36bd"
    ),
    "accepted_risk_sequential_r055_score.py": (
        "6c34940cb821c04554e9073a77e013d306d059a688dbac02fe5b0511d91d217b"
    ),
    "accepted_risk_simulated_moo_executor.py": (
        "e2f4b5508427e6f4c5bf20813e255cecae1d8652177391eeb226dc56084c5fb7"
    ),
    "accepted_risk_six_universe_gate.py": (
        "158445ae072ef6c66a49b2069c53b02ee805adbccbb9a522650ccd3a72fa9f1e"
    ),
    "accepted_risk_six_universe_gate_evaluator.py": (
        "d0f1ba677c63f2caf3703cd7a4df5fbc8ef6225aac4a2357c7d54003da73eb1c"
    ),
    "accepted_risk_six_universe_order_bridge_qc_runtime.py": (
        "3c4008da47a24c8445fb2c9aa23e9f51eb51def48da38d11b531f8f1a826ee3d"
    ),
    "accepted_risk_six_universe_order_qc_runtime.py": (
        "66cbc2966972467d3d38511e541c984d3932ad1dca2bcf05ccf69830307349b1"
    ),
    "accepted_risk_six_universe_order_targets.py": (
        "0b280fdc1ebcb5f8ab073ff78f3008057e86db14b6254145bc5f86e18d2e5ea0"
    ),
    "accepted_risk_six_universe_order_tilt_targets.py": (
        "1e8fbfd8cda080b8b4fabd9430453b64323cad8313272f50c350d204dcd627be"
    ),
    "accepted_risk_six_universe_order_tilt_qc_runtime.py": (
        "c98a548534e043840bd14074383e42555f2bfd42cee8c10f9f147187e64f6bd7"
    ),
    "main.py": "063edddf8d4032872536ab80b99ec9ac552c29a5615ac051b59fc1b430a08cf8",
}
PINNED_TILT100_FILE_BYTE_COUNTS = {
    "accepted_risk_order_level_core.py": 34_662,
    "accepted_risk_order_level_forced_exit.py": 18_671,
    "accepted_risk_order_level_input_runtime.py": 24_637,
    "accepted_risk_preliminary_qc_figi.py": 29_220,
    "accepted_risk_preliminary_rating_evaluator.py": 59_100,
    "accepted_risk_preliminary_rating_policy.py": 5_074,
    "accepted_risk_sequential_r055_score.py": 6_861,
    "accepted_risk_simulated_moo_executor.py": 37_142,
    "accepted_risk_six_universe_gate.py": 28_896,
    "accepted_risk_six_universe_gate_evaluator.py": 47_908,
    "accepted_risk_six_universe_order_bridge_qc_runtime.py": 21_075,
    "accepted_risk_six_universe_order_qc_runtime.py": 56_398,
    "accepted_risk_six_universe_order_targets.py": 20_927,
    "accepted_risk_six_universe_order_tilt_targets.py": 20_754,
    "accepted_risk_six_universe_order_tilt_qc_runtime.py": 7_853,
    "main.py": 6_576,
}


def _error(message):
    raise SixUniverseTilt100QcProjectionError(message)


def _replace_exact(source_bytes, replacements):
    if type(source_bytes) is not bytes or type(replacements) is not tuple:
        _error("R193 replacement contract changed")
    try:
        source = source_bytes.decode("ascii")
    except UnicodeError as exc:
        raise SixUniverseTilt100QcProjectionError(
            "R192 projected source is not ASCII"
        ) from exc
    for old, new, count in replacements:
        if (type(old) is not str or type(new) is not str or type(count) is not int
                or count < 1 or old == new or source.count(old) != count):
            _error("R193 projected source lost an exact replacement point")
        source = source.replace(old, new, count)
    return source.encode("ascii")


def _render_tilt100_profile():
    matched = _r192.require_settlement_profile("R191")
    baseline = _r192.require_settlement_profile("R192")
    if (matched["profile_sha256"] != PINNED_R191_PROFILE_SHA256
            or baseline["profile_sha256"] != PINNED_R192_PROFILE_SHA256
            or baseline["matched_baseline_profile_sha256"] != matched["profile_sha256"]
            or baseline["maximum_stock_weight_change_fraction"] != "0.80"
            or baseline["event_cash_policy_id"] != _r192.SETTLEMENT_POLICY_ID):
        _error("R191/R192 settlement profile changed from exact pin")
    seed = {key: value for key, value in baseline.items()
            if key != "profile_sha256"}
    seed.update({
        "schema": TILT100_PROFILE_SCHEMA,
        "profile_id": TILT100_PROFILE_ID,
        "role": TILT100_ROLE,
        "target_path_schema": TILT100_TARGET_PATH_SCHEMA,
        "decision_target_schema": TILT100_DECISION_TARGET_SCHEMA,
        "maximum_stock_weight_change_fraction": "1.00",
    })
    return json.loads(_base._canonical({
        **seed, "profile_sha256": hashlib.sha256(_base._canonical(seed)).hexdigest(),
    }).decode("ascii"))


def require_tilt100_profile():
    """Return the pinned R193 profile bound to the exact R191 cash policy."""
    profile = _render_tilt100_profile()
    if profile["profile_sha256"] != PINNED_TILT100_PROFILE_SHA256:
        _error("R193 profile changed from its exact pin")
    return profile


def _build_unpinned(delta_package):
    predecessor = _r192.build_settlement_projection(delta_package, "R192")
    if (predecessor.projection_sha256 != PINNED_R192_PROJECTION_SHA256
            or predecessor.profile_sha256 != PINNED_R192_PROFILE_SHA256
            or predecessor.total_source_byte_count != PINNED_R192_TOTAL_SOURCE_BYTES
            or len(predecessor.source_files) != 16):
        _error("R192 settlement projection changed from exact pin")
    predecessor_manifest = hashlib.sha256(_base._canonical(tuple(
        (item.project_path, item.content_sha256, item.byte_count)
        for item in predecessor.source_files
    ))).hexdigest()
    if predecessor_manifest != PINNED_R192_SOURCE_MANIFEST_SHA256:
        _error("R192 source manifest changed from exact pin")
    profile = _render_tilt100_profile()
    files = []
    for item in predecessor.source_files:
        if (item.byte_count != len(item.source_bytes)
                or item.content_sha256 != hashlib.sha256(item.source_bytes).hexdigest()):
            _error("R192 projected file identity changed")
        path = item.project_path
        if path in _TRANSFORMS:
            if (item.content_sha256 != PINNED_R192_FILE_SHA256S[path]
                    or item.byte_count != PINNED_R192_FILE_BYTE_COUNTS[path]):
                _error("R192 changed file differs from exact pin")
            files.append(_base._source_file(
                path, _replace_exact(item.source_bytes, _TRANSFORMS[path])))
        else:
            files.append(item)
    files.sort(key=lambda item: item.project_path)
    if (len(files) != 16 or len({item.project_path for item in files}) != 16
            or any(item.byte_count > _base.MAXIMUM_QC_SOURCE_CHARACTERS
                   for item in files)):
        _error("R193 projected source closure or per-file budget changed")
    for item in files:
        compile("from AlgorithmImports import *\n" + item.source_bytes.decode("ascii"),
                item.project_path, "exec")
    total = sum(item.byte_count for item in files)
    if total + _base.MINIMUM_REVIEW_MARGIN_BYTES > _base.MAXIMUM_TOTAL_SOURCE_BYTES:
        _error("R193 projected source exceeded 425,984-byte review budget")
    semantic = {key: value for key, value in predecessor.to_record().items()
                if key not in ("projection_id", "projection_sha256")}
    semantic.update({
        "schema": PROJECTION_SCHEMA,
        "role": TILT100_ROLE,
        "variant": TILT100_VARIANT,
        "profile_id": profile["profile_id"],
        "profile_sha256": profile["profile_sha256"],
        "source_files": [item.to_record() for item in files],
        "total_source_byte_count": total,
    })
    digest = hashlib.sha256(_base._canonical(semantic)).hexdigest()
    value = dataclasses.replace(
        predecessor, schema=PROJECTION_SCHEMA,
        projection_id=PROJECTION_ID_PREFIX + digest[:24],
        projection_sha256=digest, role=TILT100_ROLE, variant=TILT100_VARIANT,
        profile_id=profile["profile_id"], profile_sha256=profile["profile_sha256"],
        source_files=tuple(files), total_source_byte_count=total,
    )
    if {key: item for key, item in value.to_record().items()
            if key not in ("projection_id", "projection_sha256")} != semantic:
        _error("R193 projected source failed self-authentication")
    return value


def build_tilt100_settlement_projection(delta_package):
    """Build only the immutable, order-based R193 QC source closure."""
    value = _build_unpinned(delta_package)
    manifest = hashlib.sha256(_base._canonical(tuple(
        (item.project_path, item.content_sha256, item.byte_count)
        for item in value.source_files
    ))).hexdigest()
    files = {item.project_path: item for item in value.source_files}
    if (value.projection_sha256 != PINNED_TILT100_PROJECTION_SHA256
            or value.profile_sha256 != PINNED_TILT100_PROFILE_SHA256
            or manifest != PINNED_TILT100_SOURCE_MANIFEST_SHA256
            or value.total_source_byte_count != PINNED_TILT100_TOTAL_SOURCE_BYTES
            or set(files) != set(PINNED_TILT100_FILE_SHA256S)
            or set(files) != set(PINNED_TILT100_FILE_BYTE_COUNTS)
            or any(files[path].content_sha256 != PINNED_TILT100_FILE_SHA256S[path]
                   or files[path].byte_count != PINNED_TILT100_FILE_BYTE_COUNTS[path]
                   for path in files)):
        _error("R193 projected profile, source, or manifest changed from exact pin")
    return value


__all__ = (
    "PINNED_TILT100_FILE_BYTE_COUNTS", "PINNED_TILT100_FILE_SHA256S",
    "PINNED_TILT100_PROFILE_SHA256", "PINNED_TILT100_PROJECTION_SHA256",
    "PINNED_TILT100_SOURCE_MANIFEST_SHA256", "PINNED_TILT100_TOTAL_SOURCE_BYTES",
    "PROJECTION_ID_PREFIX", "PROJECTION_SCHEMA", "SixUniverseTilt100QcProjectionError",
    "TILT100_DECISION_TARGET_SCHEMA", "TILT100_PROFILE_ID", "TILT100_PROFILE_SCHEMA",
    "TILT100_ROLE", "TILT100_SUMMARY_SCHEMA", "TILT100_TARGET_PATH_SCHEMA",
    "TILT100_VARIANT", "build_tilt100_settlement_projection",
    "require_tilt100_profile",
)
