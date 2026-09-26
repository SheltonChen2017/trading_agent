"""Pinned R195-R200 per-sleeve-positive revision-tilt projections.

Each candidate derives from the exact R194 16-file closure. The new donor
transfer keeps both its own sleeve allocation and aggregate stock allocation
above zero; no predecessor source, cloud project, or outcome is changed here.
"""

import dataclasses
import hashlib
import json

from . import accepted_risk_six_universe_order_qc_projection as _base
from . import accepted_risk_six_universe_order_tilt100_floor_qc_projection as _r194


class SixUniverseTiltLadderFloorQcProjectionError(ValueError):
    """A candidate rule, frozen predecessor, or exact output pin changed."""


CANDIDATE_IDS = {
    100: "R195", 120: "R196", 140: "R197",
    160: "R198", 180: "R199", 200: "R200",
}
MINIMUM_STOCK_AND_SLEEVE_RESIDUAL_WEIGHT = "1e-30"
PROJECTION_SCHEMAS = {
    percent: f"arv2-six-universe-order-qc-projection-tilt{percent}-guard-settlement-v1"
    for percent in CANDIDATE_IDS
}
PROJECTION_ID_PREFIXES = {
    percent: f"arv2-six-universe-order-tilt{percent}-guard-settlement-qc-projection-"
    for percent in CANDIDATE_IDS
}
PROFILE_SCHEMAS = {
    percent: f"arv2-six-universe-order-tilt{percent}-guard-settlement-profile-v1"
    for percent in CANDIDATE_IDS
}
PROFILE_IDS = {
    percent: f"arv2-six-universe-order-matched-revision-tilt{percent}-guard-settlement-v1"
    for percent in CANDIDATE_IDS
}
DECISION_TARGET_SCHEMAS = {
    percent: f"arv2-six-universe-order-tilt{percent}-guard-decision-target-v1"
    for percent in CANDIDATE_IDS
}
TARGET_PATH_SCHEMAS = {
    percent: f"arv2-six-universe-order-tilt{percent}-guard-target-path-v1"
    for percent in CANDIDATE_IDS
}
SUMMARY_SCHEMAS = {
    percent: f"arv2-six-universe-order-tilt{percent}-guard-settlement-summary-v1"
    for percent in CANDIDATE_IDS
}
TILT_ROLES = {
    percent: f"matched_revision_tilt{percent}_guard" for percent in CANDIDATE_IDS
}
TILT_VARIANTS = {
    percent: f"cap90_matched_revision_tilt{percent}_guard_settlement_v1"
    for percent in CANDIDATE_IDS
}

PINNED_PROFILE_SHA256S = {
    100: "ecdc210a6f65ea1ee8e2163e4dc3debaf8b0c0996a457c57299dbed1c4198561",
    120: "cf9932e48e2f282713101d8d38dec2e702b08a7796ae8ccb503abff7f32234c1",
    140: "83893aca4ab0dd0b0a98eb39f51b8a8c2f77ef114a1cf231acd9214437c3287f",
    160: "7b4dac4771d1cfaf5851cb8d4c31448d01f8408baa652857292755fe88776a87",
    180: "46d6b61812c48d2d5797ac636e5919e160a6adca6e06005f2f31c596cdc7c778",
    200: "3b6acc8e91cd674d267bde3985b8fc123a5c2fbc809c87acfb9c74b2c3ec215c",
}
PINNED_PROJECTION_SHA256S = {
    100: "c20e2c13ef477e4c1619cb93aafb4fef58c2a36c95f5a514c62d015f5722e28d",
    120: "f8489764d1925f93ecd13092d5ef0d916f681385a12dc817f02115f66328f82e",
    140: "c3edcd8bae80446fd564e4d21a1a8ff3c8a35ee68af914b13de2a344ab596576",
    160: "97fdd9a4332ae2d973399535c2687153e08a81ccd2eb1e4a89daf4270c687a9f",
    180: "773787eac1cce21d27be7dd5256b917c453c3f8474a0a0d24e8b7ef9dd86d09d",
    200: "e8cc677ad751362fe702949ab52daa24ec89ade8bc6b303779a815543ef213cb",
}
PINNED_SOURCE_MANIFEST_SHA256S = {
    100: "75a3cfd8091e6311e34c0295e787969a5ba637fc2da74f9e83c70fd7700fdef3",
    120: "1b933d0f925b3103a875e9960c24741856a33b50e0b3c5c1675bfed07d76c051",
    140: "2456ee4d5089a4d9cd7cdd87068f0d1f5897ce87a6ffb1b4dfd0938ec0bf6082",
    160: "514230dd7bde96f347d2d6eae390d2c7b4fb09403c1ca7cf687f6da228eb383f",
    180: "0cc2299ac2062366046da0a027f88946fe684bcc87f27974ceab174a1da0035f",
    200: "c2bb27d8a851d365d3ab45813e9e62aa3e63fc110cd69cac05b8791585249745",
}
PINNED_TOTAL_SOURCE_BYTES = {
    100: 425_975,
    120: 425_975,
    140: 425_975,
    160: 425_975,
    180: 425_975,
    200: 425_975,
}
PINNED_CHANGED_FILE_SHA256S = {
    100: {
        "accepted_risk_six_universe_order_tilt_targets.py": "e5012dfea1dbaf667a693284168a54c6b4b78a45ff3c9a1b052a3cb20a43a567",
        "accepted_risk_six_universe_order_tilt_qc_runtime.py": "d3a40c7a25fc14bc5013bade0bf643c1f6861f80405c9d18a422fcf3180072c2",
        "main.py": "f7645ae2beacf7654d35e27a151afd476ba3ae8304ec21a54765c4bc1e57e351",
    },
    120: {
        "accepted_risk_six_universe_order_tilt_targets.py": "ea8c2c043bbab8137a8eeecc54520506a9c6265112c40de7f64edd0c3c5b1bb6",
        "accepted_risk_six_universe_order_tilt_qc_runtime.py": "8395a9dfdf1b9b3478eb387f75dfb5da68decd1bdf824c6cc51d8d906da897de",
        "main.py": "fae35e392ef58c052258b050f8daa9fdb3f2182c6704330942681a4e0fc45b95",
    },
    140: {
        "accepted_risk_six_universe_order_tilt_targets.py": "66bca0f109e7400c5e2ee8eabd3c11fcccbfe67b7a00da25cf87d2752ce0adc8",
        "accepted_risk_six_universe_order_tilt_qc_runtime.py": "ba83761d085965f3cf58170757356f0fe4f4f97627c240c0cd835f8765032c44",
        "main.py": "94ecdecb0c4867f15d06ae5a936b8843d373f631ec6aed4f4e702c7ab98224bb",
    },
    160: {
        "accepted_risk_six_universe_order_tilt_targets.py": "09f2794b72b589b5f2519025b8d037b065a4dcd9e68d6a630602d0e91a25c317",
        "accepted_risk_six_universe_order_tilt_qc_runtime.py": "586cb7453493abeb377d833906ba5775fb7a3ede8c6eb70b4bc44e9dab5674c9",
        "main.py": "e10ed11d78d58045c6e0a4d9e76fbcc9bcafa8ed4b727d0a83243dde72290866",
    },
    180: {
        "accepted_risk_six_universe_order_tilt_targets.py": "dfd5c5a60c66e269865bec6b23204aa6e2bc96cb0cee7202334b0ee24dfef3a8",
        "accepted_risk_six_universe_order_tilt_qc_runtime.py": "a7ac51d09e5f28062cb4d2547a946a4e96caaa91616b7f8c80c42afe18723e89",
        "main.py": "06586864b0ec69ea47cdd3b53350f86f3bb0b92a4dd9677074857db4f814e596",
    },
    200: {
        "accepted_risk_six_universe_order_tilt_targets.py": "e03faa4c3578bf14ca01dece6125a9cbcf2959f8aaba0500fd43f61224666865",
        "accepted_risk_six_universe_order_tilt_qc_runtime.py": "c85d19239949645016927ae2e3043664d511e144301d66895d787498e80a0e8e",
        "main.py": "b8fb4131a08170d804f1acec0547f0e75b085207589471676b3b40afbe7a74f9",
    },
}
PINNED_CHANGED_FILE_BYTE_COUNTS = {
    100: {
        "accepted_risk_six_universe_order_tilt_targets.py": 20_873,
        "accepted_risk_six_universe_order_tilt_qc_runtime.py": 7_938,
        "main.py": 6_593,
    },
    120: {
        "accepted_risk_six_universe_order_tilt_targets.py": 20_873,
        "accepted_risk_six_universe_order_tilt_qc_runtime.py": 7_938,
        "main.py": 6_593,
    },
    140: {
        "accepted_risk_six_universe_order_tilt_targets.py": 20_873,
        "accepted_risk_six_universe_order_tilt_qc_runtime.py": 7_938,
        "main.py": 6_593,
    },
    160: {
        "accepted_risk_six_universe_order_tilt_targets.py": 20_873,
        "accepted_risk_six_universe_order_tilt_qc_runtime.py": 7_938,
        "main.py": 6_593,
    },
    180: {
        "accepted_risk_six_universe_order_tilt_targets.py": 20_873,
        "accepted_risk_six_universe_order_tilt_qc_runtime.py": 7_938,
        "main.py": 6_593,
    },
    200: {
        "accepted_risk_six_universe_order_tilt_targets.py": 20_873,
        "accepted_risk_six_universe_order_tilt_qc_runtime.py": 7_938,
        "main.py": 6_593,
    },
}


def _error(message):
    raise SixUniverseTiltLadderFloorQcProjectionError(message)


def _percent(percent):
    if type(percent) is not int or percent not in CANDIDATE_IDS:
        _error("tilt floor percent is not one of 100, 120, 140, 160, 180, or 200")
    return percent


def _fraction_text(percent):
    return f"{percent // 100}.{percent % 100:02d}"


def _replace_exact(source_bytes, replacements):
    if type(source_bytes) is not bytes or type(replacements) is not tuple:
        _error("tilt floor replacement contract changed")
    try:
        source = source_bytes.decode("ascii")
    except UnicodeError as exc:
        raise SixUniverseTiltLadderFloorQcProjectionError(
            "R194 projected source is not ASCII"
        ) from exc
    for old, new, count in replacements:
        if (type(old) is not str or type(new) is not str or type(count) is not int
                or count < 1 or old == new or source.count(old) != count):
            _error("tilt floor projected source lost an exact replacement point")
        source = source.replace(old, new, count)
    return source.encode("ascii")


def _transforms(percent):
    percent = _percent(percent)
    fraction = _fraction_text(percent)
    target = [
        ('TILT_ROLE = "matched_revision_tilt100_floor"',
         f'TILT_ROLE = "{TILT_ROLES[percent]}"', 1),
        ('DECISION_TARGET_SCHEMA = "arv2-six-universe-order-tilt100-floor-decision-target-v1"',
         f'DECISION_TARGET_SCHEMA = "{DECISION_TARGET_SCHEMAS[percent]}"', 1),
        ('TARGET_PATH_SCHEMA = "arv2-six-universe-order-tilt100-floor-target-path-v1"',
         f'TARGET_PATH_SCHEMA = "{TARGET_PATH_SCHEMAS[percent]}"', 1),
        ('"arv2-six-universe-order-tilt100-floor-target-path-"',
         f'"arv2-six-universe-order-tilt{percent}-guard-target-path-"', 1),
        ('moved = min(room, available, stock_totals[donor_id] - WEIGHT_TRANSFER_QUANTUM)',
         'moved = min(room, available, updated[donor_id] - WEIGHT_TRANSFER_QUANTUM, '
         'stock_totals[donor_id] - WEIGHT_TRANSFER_QUANTUM)', 1),
    ]
    runtime = [
        ('TILT_VARIANT = "cap90_matched_revision_tilt100_floor_settlement_v1"',
         f'TILT_VARIANT = "{TILT_VARIANTS[percent]}"', 1),
        ('TILT_PROFILE_SCHEMA = "arv2-six-universe-order-tilt100-floor-settlement-profile-v1"',
         f'TILT_PROFILE_SCHEMA = "{PROFILE_SCHEMAS[percent]}"', 1),
        ('TILT_SUMMARY_SCHEMA = "arv2-six-universe-order-tilt100-floor-settlement-summary-v1"',
         f'TILT_SUMMARY_SCHEMA = "{SUMMARY_SCHEMAS[percent]}"', 1),
        ('"profile_id": "arv2-six-universe-order-matched-revision-tilt100-floor-settlement-v1",',
         f'"profile_id": "{PROFILE_IDS[percent]}",', 1),
        ('"minimum_stock_residual_weight": "1e-30"',
         f'"minimum_stock_and_sleeve_residual_weight": '
         f'"{MINIMUM_STOCK_AND_SLEEVE_RESIDUAL_WEIGHT}"', 1),
    ]
    main = [
        ('class ARV2SixUniverseOrderTilt100FloorAlgorithm(QCAlgorithm):',
         f'class ARV2SixUniverseOrderTilt{percent}GuardAlgorithm(QCAlgorithm):', 1),
        ("role='matched_revision_tilt100_floor',",
         f"role='{TILT_ROLES[percent]}',", 1),
        ("variant='cap90_matched_revision_tilt100_floor_settlement_v1',",
         f"variant='{TILT_VARIANTS[percent]}',", 1),
    ]
    if percent != 100:
        target.extend((
            ('MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION = Decimal("1.00")',
             f'MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION = Decimal("{fraction}")', 1),
            ('bounded by 100% of its own post-cap',
             f'bounded by {percent}% of its own post-cap', 1),
            ('"maximum_stock_weight_change_fraction": "1.00"',
             f'"maximum_stock_weight_change_fraction": "{fraction}"', 1),
        ))
        runtime.append((
            '"maximum_stock_weight_change_fraction": "1.00"',
            f'"maximum_stock_weight_change_fraction": "{fraction}"', 2,
        ))
    return {
        "accepted_risk_six_universe_order_tilt_targets.py": tuple(target),
        "accepted_risk_six_universe_order_tilt_qc_runtime.py": tuple(runtime),
        "main.py": tuple(main),
    }


def _render_profile(percent):
    percent = _percent(percent)
    baseline = _r194.require_tilt100_floor_profile()
    if (baseline["profile_sha256"] != _r194.PINNED_PROFILE_SHA256
            or baseline["maximum_stock_weight_change_fraction"] != "1.00"
            or baseline["minimum_stock_residual_weight"] != "1e-30"):
        _error("R194 profile changed from exact pin")
    seed = {key: value for key, value in baseline.items()
            if key not in ("profile_sha256", "minimum_stock_residual_weight")}
    seed.update({
        "schema": PROFILE_SCHEMAS[percent],
        "profile_id": PROFILE_IDS[percent],
        "role": TILT_ROLES[percent],
        "target_path_schema": TARGET_PATH_SCHEMAS[percent],
        "decision_target_schema": DECISION_TARGET_SCHEMAS[percent],
        "maximum_stock_weight_change_fraction": _fraction_text(percent),
        "minimum_stock_and_sleeve_residual_weight": (
            MINIMUM_STOCK_AND_SLEEVE_RESIDUAL_WEIGHT
        ),
    })
    return json.loads(_base._canonical({
        **seed, "profile_sha256": hashlib.sha256(_base._canonical(seed)).hexdigest(),
    }).decode("ascii"))


def require_tilt_floor_profile(percent):
    """Return one exact candidate profile; refuse unknown or changed rules."""
    profile = _render_profile(percent)
    if profile["profile_sha256"] != PINNED_PROFILE_SHA256S[percent]:
        _error("tilt floor profile changed from its exact pin")
    return profile


def _build_unpinned(delta_package, percent):
    percent = _percent(percent)
    predecessor = _r194.build_tilt100_floor_projection(delta_package)
    if (predecessor.projection_sha256 != _r194.PINNED_PROJECTION_SHA256
            or predecessor.profile_sha256 != _r194.PINNED_PROFILE_SHA256
            or predecessor.total_source_byte_count != _r194.PINNED_TOTAL_SOURCE_BYTES
            or len(predecessor.source_files) != 16):
        _error("R194 source changed from exact pin")
    predecessor_manifest = hashlib.sha256(_base._canonical(tuple(
        (item.project_path, item.content_sha256, item.byte_count)
        for item in predecessor.source_files
    ))).hexdigest()
    if predecessor_manifest != _r194.PINNED_SOURCE_MANIFEST_SHA256:
        _error("R194 manifest changed from exact pin")
    profile = _render_profile(percent)
    transforms = _transforms(percent)
    files = []
    for item in predecessor.source_files:
        if (item.byte_count != len(item.source_bytes)
                or item.content_sha256 != hashlib.sha256(item.source_bytes).hexdigest()
                or item.content_sha256 != _r194.PINNED_FILE_SHA256S[item.project_path]
                or item.byte_count != _r194.PINNED_FILE_BYTE_COUNTS[item.project_path]):
            _error("R194 projected file differs from exact pin")
        files.append(_base._source_file(
            item.project_path,
            _replace_exact(item.source_bytes, transforms[item.project_path])
            if item.project_path in transforms else item.source_bytes,
        ))
    files.sort(key=lambda item: item.project_path)
    if (len(files) != 16 or len({item.project_path for item in files}) != 16
            or any(item.byte_count > _base.MAXIMUM_QC_SOURCE_CHARACTERS
                   for item in files)):
        _error("tilt floor projected closure or per-file budget changed")
    for item in files:
        compile("from AlgorithmImports import *\n" + item.source_bytes.decode("ascii"),
                item.project_path, "exec")
    total = sum(item.byte_count for item in files)
    if total + _base.MINIMUM_REVIEW_MARGIN_BYTES > _base.MAXIMUM_TOTAL_SOURCE_BYTES:
        _error("tilt floor projected source exceeded review budget")
    semantic = {key: value for key, value in predecessor.to_record().items()
                if key not in ("projection_id", "projection_sha256")}
    semantic.update({
        "schema": PROJECTION_SCHEMAS[percent],
        "role": TILT_ROLES[percent],
        "variant": TILT_VARIANTS[percent],
        "profile_id": profile["profile_id"],
        "profile_sha256": profile["profile_sha256"],
        "source_files": [item.to_record() for item in files],
        "total_source_byte_count": total,
    })
    digest = hashlib.sha256(_base._canonical(semantic)).hexdigest()
    value = dataclasses.replace(
        predecessor, schema=PROJECTION_SCHEMAS[percent],
        projection_id=PROJECTION_ID_PREFIXES[percent] + digest[:24],
        projection_sha256=digest, role=TILT_ROLES[percent],
        variant=TILT_VARIANTS[percent], profile_id=profile["profile_id"],
        profile_sha256=profile["profile_sha256"], source_files=tuple(files),
        total_source_byte_count=total,
    )
    if {key: item for key, item in value.to_record().items()
            if key not in ("projection_id", "projection_sha256")} != semantic:
        _error("tilt floor projected source failed self-authentication")
    return value


def build_tilt_floor_projection(delta_package, percent):
    """Build only the independently pinned order-based candidate closure."""
    value = _build_unpinned(delta_package, percent)
    manifest = hashlib.sha256(_base._canonical(tuple(
        (item.project_path, item.content_sha256, item.byte_count)
        for item in value.source_files
    ))).hexdigest()
    files = {item.project_path: item for item in value.source_files}
    expected_hashes = {
        **_r194.PINNED_FILE_SHA256S,
        **PINNED_CHANGED_FILE_SHA256S[percent],
    }
    expected_sizes = {
        **_r194.PINNED_FILE_BYTE_COUNTS,
        **PINNED_CHANGED_FILE_BYTE_COUNTS[percent],
    }
    if (value.projection_sha256 != PINNED_PROJECTION_SHA256S[percent]
            or value.profile_sha256 != PINNED_PROFILE_SHA256S[percent]
            or manifest != PINNED_SOURCE_MANIFEST_SHA256S[percent]
            or value.total_source_byte_count != PINNED_TOTAL_SOURCE_BYTES[percent]
            or set(files) != set(expected_hashes)
            or set(files) != set(expected_sizes)
            or any(files[path].content_sha256 != expected_hashes[path]
                   or files[path].byte_count != expected_sizes[path]
                   for path in files)):
        _error("tilt floor projected profile, source, or manifest changed from exact pin")
    return value


__all__ = (
    "CANDIDATE_IDS", "DECISION_TARGET_SCHEMAS",
    "MINIMUM_STOCK_AND_SLEEVE_RESIDUAL_WEIGHT",
    "PINNED_CHANGED_FILE_BYTE_COUNTS", "PINNED_CHANGED_FILE_SHA256S",
    "PINNED_PROFILE_SHA256S", "PINNED_PROJECTION_SHA256S",
    "PINNED_SOURCE_MANIFEST_SHA256S", "PINNED_TOTAL_SOURCE_BYTES",
    "PROFILE_IDS", "PROFILE_SCHEMAS", "PROJECTION_ID_PREFIXES",
    "PROJECTION_SCHEMAS", "SUMMARY_SCHEMAS", "TILT_ROLES", "TILT_VARIANTS",
    "TARGET_PATH_SCHEMAS", "SixUniverseTiltLadderFloorQcProjectionError",
    "build_tilt_floor_projection", "require_tilt_floor_profile",
)
