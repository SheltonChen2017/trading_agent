"""Exact recent-window successors of the frozen guarded tilt source.

Period, immutable input and dependent identities change together. No cloud
action, outcome read, or host-global authority override occurs here.
"""

import ast
import dataclasses
import hashlib
import json

from . import accepted_risk_preliminary_package as _package
from . import accepted_risk_six_universe_gate_evaluator as _evaluation
from . import accepted_risk_six_universe_order_qc_projection as _base
from . import accepted_risk_six_universe_order_qc_runtime as _runtime
from . import accepted_risk_six_universe_order_settlement_qc_projection as _settlement
from . import accepted_risk_six_universe_order_tilt_ladder_floor_qc_projection as _prior


class SixUniverseTiltRecentQcProjectionError(ValueError):
    """An exact period, package, profile or source identity changed."""


CANDIDATE_IDS = dict(zip((100, 120, 140, 160, 180, 200),
                        ("R203", "R204", "R205", "R206", "R207", "R208")))
EVALUATION_START_SESSION = "2025-08-01"
EVALUATION_END_SESSION = "2026-09-25"
LAST_DECISION_SESSION = "2026-09-21"
FIRST_EXECUTION_SESSION = "2025-08-04"
EXPECTED_SESSION_COUNT = 290
EXPECTED_RETURN_SESSION_COUNT = 289
EXPECTED_DECISION_COUNT = 61
TERMINAL_CLOCK_RULE = "2026-09-26_00:00_new_york_after_exact_2026-09-25_account_observation"
PROJECTION_SCHEMAS = {p: f"arv2-six-universe-order-qc-projection-tilt{p}-recent-v1"
                      for p in CANDIDATE_IDS}
PROJECTION_ID_PREFIXES = {p: f"arv2-six-universe-order-tilt{p}-recent-qc-projection-"
                          for p in CANDIDATE_IDS}
PROFILE_SCHEMAS = {p: f"arv2-six-universe-order-tilt{p}-recent-profile-v1"
                   for p in CANDIDATE_IDS}
PROFILE_IDS = {p: f"arv2-six-universe-order-matched-revision-tilt{p}-recent-v1"
               for p in CANDIDATE_IDS}
SUMMARY_SCHEMAS = {p: f"arv2-six-universe-order-tilt{p}-recent-summary-v1"
                   for p in CANDIDATE_IDS}
DECISION_TARGET_SCHEMAS = {p: f"arv2-six-universe-order-tilt{p}-recent-decision-target-v1"
                           for p in CANDIDATE_IDS}
TARGET_PATH_SCHEMAS = {p: f"arv2-six-universe-order-tilt{p}-recent-target-path-v1"
                       for p in CANDIDATE_IDS}
TILT_ROLES = {p: f"matched_revision_tilt{p}_recent" for p in CANDIDATE_IDS}
TILT_VARIANTS = {p: f"cap90_matched_revision_tilt{p}_recent_v1"
                 for p in CANDIDATE_IDS}
CAP90_PROFILE_SCHEMA = "arv2-six-universe-order-profile-recent-v1"
BRIDGE_PROFILE_SCHEMA = "arv2-six-universe-order-admission-recent-profile-v1"
MATCHED_PROFILE_ID = "arv2-six-universe-order-matched-cap90-admission-recent-v1"

# Literal production identities frozen before any outcome launch.
PINNED_PACKAGE_ID = "arv2-preliminary-qc-package-2649577ac55ac39de37a4a70"
PINNED_PACKAGE_SHA256 = "2649577ac55ac39de37a4a70ab4337274f1887e1a113f0972beefab615121be1"
PINNED_LINEAGE_SHA256 = "c39b6fe27782a7776891aab67c82d816fcd2109b12928cc84643073d140b2dbb"
PINNED_ACTIVATION_KEY = "arv2/preliminary-rating/01820a4b37c320d580bd1977/transport-manifest.json"
PINNED_ACTIVATION_SHA256 = "9ee1013f429ed87e7b7a262cf352c5604cd532ce4eb3e9defffe23be31c39b35"
PINNED_ACTIVATION_BYTE_COUNT = 4523
PINNED_PROFILE_SHA256S = {
    100: "2a14727e763e5cbcbb6c32b08b1e051cf24af210761eacabc288f8e8ae140410",
    120: "9e4d7a788e594834433ec34f957db25caf4f2847598fc8b3423957170195ccb9",
    140: "f8e641731f322c67420c82ccf463cbb5e513fb08961330132855e667daacf271",
    160: "3ff5c516323b945eea28bd1104f3ebaa215ebfb3a70c1ab76f778ec033ada2c5",
    180: "cbfc4c7ad196f50b0dfdd221572b4f26a3fddef6e3cd87781d03e192e2d7a214",
    200: "c84a1a17d23e504044baf63807a83135b4d098062b7a2b98a041336234f1809a",
}
PINNED_PROJECTION_SHA256S = {
    100: "39793ae7247bae5282f93edfbaa5f6828bd4e49332f5b7909cf07baf92557b21",
    120: "dd8eb43587ea2b893992f40ce3b33af4da65415cd3515fed3130e5a2e294fedb",
    140: "78b52a953782257f5fbef2d5dbeaafec2533a5f853e41da1b8ce7117493a8b66",
    160: "d70d5b314f409c70fb16fbbe19171bcb29819fdff0716ca4620657b0775d7f9a",
    180: "7d344126844c46642f52be74daa8f5a702e65e50d8979ee7df78e25f1b3ca7b1",
    200: "9f4df0c75eda0e6aa27ee69351ee044263bfe0f1d79312f0b40a62034a26e85f",
}
PINNED_SOURCE_MANIFEST_SHA256S = {
    100: "f8f706628fc6aefb5756cdaeb382bccdf97231f816fb5367e8d74ffbe1f72911",
    120: "724fbcf56108f2a5d7478f3067c43f4e232ea1ea063c39678684d6a9e52ab501",
    140: "18be41789db4fbfc33daf41daf433713027bb71455774bb416a94624ce8d2b70",
    160: "4cf2518306e18589a193646a320d25a80585fbb5d3a387bad735d50a9a184824",
    180: "e2a11a2c90ae496e64daa1c9d3ce5cdd6248c1110acbdadbd3c7d1886dcd1cdd",
    200: "563f3de21000c4588610f7c43904091d1dafbbfff930f50d1cd193261b954b43",
}
PINNED_TOTAL_SOURCE_BYTES = {percent: 425165 for percent in CANDIDATE_IDS}
_PERIOD_FILE_PINS = {
    "accepted_risk_six_universe_gate_evaluator.py": (
        "c720ed98721894e08618e6c07f6c1b8144adfb7ee5eed39b5e47bc521782d71b", 47903),
    "accepted_risk_six_universe_order_bridge_qc_runtime.py": (
        "a9ba3c466e4c9543f0a348f6f17eb00e7e6ad5154b06b6f870a8e01574a1ff51", 21068),
    "accepted_risk_six_universe_order_qc_runtime.py": (
        "027937df8a596a787a1519837c9294bf75316154fec0948cad13a3e001a55b3b", 56399),
}
_CANDIDATE_FILE_SHA256S = {
    100: (
        "0a8f8a6f2a33cc89c65a16b64ce32274227895a6b7de7ac0357ba068a175e03a",
        "27af2601e99d9a0f2e9c3b083b9efe926e0a190536d376915373cef2b62ca4be",
        "cc95c70c2e9f01cf6ca5f0bfff437e73fae602bfa3793ab4f40a7c0d054b13c1"),
    120: (
        "b355c48716887f8bff3bbe7a0cdd69a3a80ab32c47da5dd0cfaee219963d6859",
        "242a3a5771dab4c0daabe0658e9360bd5958283e6fa319044f1a727087c3de7f",
        "c7851243bdc698edf94fb6e43136c718208810a1f61ef19c5c1b8c0c8bce20c6"),
    140: (
        "c8b489e88abdf1033843afe7ede85113c75f013905bd85500db1094b7498730f",
        "0742fa512d131de3d25714a13610e3a63059324faf8fb63110eddf76a8d8e0a2",
        "343cd7396dbc6bee48b26ae4408fe91d696ab725922d402c2f7c2fc9f13a27b8"),
    160: (
        "6cd4aeed757d6e442f88e2a6682195844fcd03976918a7a655ed995372757034",
        "0b293af1030fd81a700c4fc5703871ada05d257c49f14188441b1eb2582ae82d",
        "ae06879444a1a05606c50e9da7bd547a17c126eb1431ff6130a2fdb4d46fc677"),
    180: (
        "41b562195a18d21224b5a632031b0497e19e5398e5abd169774b93d52d040b5b",
        "2958ac12da56683c7d69aba984ba7e49aebbbef7c9259aaee983e16fbe776f44",
        "a51951a0a4e77758dcaa80ce8086a63135e52b724f46a83f447e68e72cf45c0e"),
    200: (
        "b6a45dfc094f73a23bf42275bb81f54319e87ad29c059f38855ef74f796430ce",
        "7a353c1e656acdf4615c8b2fa67c0c18049c648f4b56e97d192032b32fc1d5e5",
        "98ad4126affd4a69add9dcfbedbfbf59771de4afe79178ccecb1968d49f24413"),
}
_CANDIDATE_FILE_BYTE_COUNTS = {
    "accepted_risk_six_universe_order_tilt_qc_runtime.py": 7898,
    "accepted_risk_six_universe_order_tilt_targets.py": 20877,
    "main.py": 5830,
}
# Reuse the ten unchanged frozen closure files rather than recopying their pins.
PINNED_FILE_SHA256S = {percent: {
    **_prior._r194.PINNED_FILE_SHA256S,
    **{path: pin[0] for path, pin in _PERIOD_FILE_PINS.items()},
    **dict(zip(_CANDIDATE_FILE_BYTE_COUNTS, _CANDIDATE_FILE_SHA256S[percent])),
} for percent in CANDIDATE_IDS}
PINNED_FILE_BYTE_COUNTS = {percent: {
    **_prior._r194.PINNED_FILE_BYTE_COUNTS,
    **{path: pin[1] for path, pin in _PERIOD_FILE_PINS.items()},
    **_CANDIDATE_FILE_BYTE_COUNTS,
} for percent in CANDIDATE_IDS}


def _error(message):
    raise SixUniverseTiltRecentQcProjectionError(message)


def _percent(percent):
    if type(percent) is not int or percent not in CANDIDATE_IDS:
        _error("recent tilt percent is not a pinned 100-through-200 candidate")
    return percent


def _record(seed):
    seed = {key: value for key, value in seed.items() if key != "profile_sha256"}
    return json.loads(_base._canonical({
        **seed, "profile_sha256": hashlib.sha256(_base._canonical(seed)).hexdigest(),
    }).decode("ascii"))


def _evaluation_profile():
    profile = _evaluation.TOP10_CAP90_EXPLORATORY_PROFILE
    seed = {key: value for key, value in profile.to_record().items()
            if key not in ("profile_id", "profile_sha256")}
    seed.update({
        "evaluation_start_session": EVALUATION_START_SESSION,
        "evaluation_end_session": EVALUATION_END_SESSION,
        "expected_session_count": EXPECTED_SESSION_COUNT,
        "expected_return_session_count": EXPECTED_RETURN_SESSION_COUNT,
        "expected_decision_session_count": EXPECTED_DECISION_COUNT,
    })
    digest = hashlib.sha256(_base._canonical(seed)).hexdigest()
    return {**seed, "profile_sha256": digest,
            "profile_id": "arv2-six-universe-evaluation-"
            + profile.gate_profile.label + "-" + digest[:24]}


def _geometry():
    evaluation = _evaluation_profile()
    return {
        "evaluation_start_session": EVALUATION_START_SESSION,
        "evaluation_end_session": EVALUATION_END_SESSION,
        "decision_count": EXPECTED_DECISION_COUNT,
        "evaluation_session_count": EXPECTED_SESSION_COUNT,
        "evaluation_profile_id": evaluation["profile_id"],
        "evaluation_profile_sha256": evaluation["profile_sha256"],
        "terminal_clock_rule": TERMINAL_CLOCK_RULE,
    }


def _matched_profile():
    cap90 = _runtime.require_six_universe_order_profile(
        "matched", variant=_runtime.CAP90_VARIANT)
    cap90.update({**_geometry(), "schema": CAP90_PROFILE_SCHEMA,
                  "profile_id": "arv2-six-universe-order-matched-cap90-recent-v1"})
    cap90 = _record(cap90)
    matched = _settlement.require_settlement_profile("R191")
    matched.update({**_geometry(), "schema": BRIDGE_PROFILE_SCHEMA,
                    "profile_id": MATCHED_PROFILE_ID,
                    "cap90_predecessor_profile_sha256": cap90["profile_sha256"]})
    return _record(matched)


MATCHED_BASELINE_PROFILE_SHA256 = "440c7a683efe7476d88aaab730d87955efcbeb31aac4b559b330ad32f39c4fc6"


def _render_profile(percent):
    percent = _percent(percent)
    profile = _prior.require_tilt_floor_profile(percent)
    matched = _matched_profile()
    if matched["profile_sha256"] != MATCHED_BASELINE_PROFILE_SHA256:
        _error("recent matched profile changed from exact pin")
    profile.update({**_geometry(), "schema": PROFILE_SCHEMAS[percent],
                    "profile_id": PROFILE_IDS[percent], "role": TILT_ROLES[percent],
                    "matched_baseline_profile_sha256": matched["profile_sha256"],
                    "cap90_predecessor_profile_sha256": matched["cap90_predecessor_profile_sha256"],
                    "target_path_schema": TARGET_PATH_SCHEMAS[percent],
                    "decision_target_schema": DECISION_TARGET_SCHEMAS[percent]})
    return _record(profile)


def require_tilt_recent_profile(percent):
    profile = _render_profile(percent)
    if profile["profile_sha256"] != PINNED_PROFILE_SHA256S.get(percent):
        _error("recent tilt profile changed from exact pin")
    return profile


def _replace(source, old, new, count=1):
    if old == new or source.count(old) != count:
        _error("recent source lost an exact replacement point")
    return source.replace(old, new, count)


def _period_source(path, source):
    replacements = ()
    if path == "accepted_risk_six_universe_gate_evaluator.py":
        replacements = (
            ('DECISION_START_SESSION = "2021-01-04"', f'DECISION_START_SESSION = "{EVALUATION_START_SESSION}"'),
            ('EVALUATION_END_SESSION = "2025-12-31"', f'EVALUATION_END_SESSION = "{EVALUATION_END_SESSION}"'),
            ("EXPECTED_SESSION_COUNT = 1_255", "EXPECTED_SESSION_COUNT = 290"),
            ("EXPECTED_RETURN_SESSION_COUNT = 1_254", "EXPECTED_RETURN_SESSION_COUNT = 289"),
            ("EXPECTED_DECISION_SESSION_COUNT = 261", "EXPECTED_DECISION_SESSION_COUNT = 61"),
        )
    elif path == "accepted_risk_six_universe_order_qc_runtime.py":
        replacements = (
            ("EVALUATION_START_SESSION = '2021-01-04'", f"EVALUATION_START_SESSION = '{EVALUATION_START_SESSION}'"),
            ("EVALUATION_END_SESSION = '2025-12-31'", f"EVALUATION_END_SESSION = '{EVALUATION_END_SESSION}'"),
            ("EXPECTED_DECISION_COUNT = 261", "EXPECTED_DECISION_COUNT = 61"),
            ("EXPECTED_SESSION_COUNT = 1255", "EXPECTED_SESSION_COUNT = 290"),
            ("decisions[-1] != '2025-12-29'", f"decisions[-1] != '{LAST_DECISION_SESSION}'"),
            ("CAP90_PROFILE_SCHEMA = 'arv2-six-universe-order-profile-v3'", f"CAP90_PROFILE_SCHEMA = '{CAP90_PROFILE_SCHEMA}'"),
            ("'-cap90-exploratory-v3'", "'-cap90-recent-v1'"),
            ("'2026-01-01_00:00_new_york_after_exact_2025-12-31_account_observation'", repr(TERMINAL_CLOCK_RULE)),
            ("end_clock.month != 1 or end_clock.day != 1", "end_clock.month != 9 or end_clock.day != 26"),
        )
    elif path == "accepted_risk_six_universe_order_bridge_qc_runtime.py":
        replacements = (
            ('BRIDGE_PROFILE_SCHEMA = "arv2-six-universe-order-admission-settlement-profile-v1"', f'BRIDGE_PROFILE_SCHEMA = "{BRIDGE_PROFILE_SCHEMA}"'),
            ('"-cap90-admission-settlement-v1"', '"-cap90-admission-recent-v1"'),
            ("or end_clock.month != 1", "or end_clock.month != 9"),
            ("or end_clock.day != 1", "or end_clock.day != 26"),
        )
    for old, new in replacements:
        source = _replace(source, old, new)
    return source


def _candidate_source(path, source, percent, predecessor, activation):
    source = _period_source(path, source)
    replacements = ()
    if path == "accepted_risk_six_universe_order_tilt_targets.py":
        replacements = (
            (_prior.TILT_ROLES[percent], TILT_ROLES[percent]),
            (_prior.DECISION_TARGET_SCHEMAS[percent], DECISION_TARGET_SCHEMAS[percent]),
            (_prior.TARGET_PATH_SCHEMAS[percent], TARGET_PATH_SCHEMAS[percent]),
            (f"arv2-six-universe-order-tilt{percent}-guard-target-path-", f"arv2-six-universe-order-tilt{percent}-recent-target-path-"),
        )
    elif path == "accepted_risk_six_universe_order_tilt_qc_runtime.py":
        replacements = (
            (_prior.TILT_VARIANTS[percent], TILT_VARIANTS[percent]),
            (_prior.PROFILE_SCHEMAS[percent], PROFILE_SCHEMAS[percent]),
            (_prior.SUMMARY_SCHEMAS[percent], SUMMARY_SCHEMAS[percent]),
            (_prior.PROFILE_IDS[percent], PROFILE_IDS[percent]),
            (_settlement.CANDIDATES["R191"]["profile_sha256"], MATCHED_BASELINE_PROFILE_SHA256),
        )
    elif path == "main.py":
        replacements = (
            (f"ARV2SixUniverseOrderTilt{percent}GuardAlgorithm", f"ARV2SixUniverseOrderTilt{percent}RecentAlgorithm"),
            (f"role='{_prior.TILT_ROLES[percent]}',", f"role='{TILT_ROLES[percent]}',"),
            (_prior.TILT_VARIANTS[percent], TILT_VARIANTS[percent]),
            ("self.set_start_date(2020, 11, 1)", "self.set_start_date(2025, 7, 24)"),
            ("self.set_end_date(2025, 12, 31)", "self.set_end_date(2026, 9, 25)"),
            (repr(predecessor.activation_manifest_key), repr(activation.object_store_key)),
            (repr(predecessor.activation_manifest_sha256), repr(activation.content_sha256)),
            (f"activation_manifest_byte_count={predecessor.activation_manifest_byte_count}", f"activation_manifest_byte_count={activation.byte_count}"),
        )
    for old, new in replacements:
        if (path == "main.py" and old == new
                and old.startswith("activation_manifest_byte_count=")):
            # Different immutable manifests may legitimately have equal sizes.
            # Authenticate the binding slot even when its numeric value stays.
            if source.count(old) != 1:
                _error("recent source lost an exact replacement point")
            continue
        source = _replace(source, old, new)
    if path == "main.py":
        # Formatting/comment-only normalization makes room for new bindings.
        tree = ast.parse(source)
        normalized = ast.unparse(tree) + "\n"
        if ast.dump(tree, include_attributes=False) != ast.dump(ast.parse(normalized), include_attributes=False):
            _error("recent main normalization changed executable AST")
        source = normalized
    return source


def _build_unpinned(prior_delta_package, latest_package, percent):
    percent = _percent(percent)
    predecessor = _prior.build_tilt_floor_projection(prior_delta_package, percent)
    package = _package.require_accepted_risk_preliminary_package(latest_package)
    activation = package.upload_objects[-1]
    if (package.package_id != PINNED_PACKAGE_ID
            or package.package_sha256 != PINNED_PACKAGE_SHA256
            or package.source_disposition_sha256 != PINNED_LINEAGE_SHA256
            or activation.object_store_key != PINNED_ACTIVATION_KEY
            or activation.content_sha256 != PINNED_ACTIVATION_SHA256
            or activation.byte_count != PINNED_ACTIVATION_BYTE_COUNT
            or activation.role != "activation_manifest"
            or activation.activation_manifest is not True):
        _error("recent package or activation changed from exact pin")
    files = tuple(sorted((_base._source_file(item.project_path, _candidate_source(
        item.project_path, item.source_bytes.decode("ascii"), percent,
        predecessor, activation).encode("ascii")) for item in predecessor.source_files),
        key=lambda item: item.project_path))
    total = sum(item.byte_count for item in files)
    if (len(files) != 16 or len({item.project_path for item in files}) != 16
            or any(item.byte_count > _base.MAXIMUM_QC_SOURCE_CHARACTERS for item in files)
            or total + _base.MINIMUM_REVIEW_MARGIN_BYTES > _base.MAXIMUM_TOTAL_SOURCE_BYTES):
        _error("recent projected source exceeded closure or review budget")
    profile = _render_profile(percent)
    value = dataclasses.replace(
        predecessor, schema=PROJECTION_SCHEMAS[percent], role=TILT_ROLES[percent],
        variant=TILT_VARIANTS[percent], profile_id=PROFILE_IDS[percent],
        profile_sha256=profile["profile_sha256"], package_id=package.package_id,
        package_sha256=package.package_sha256, package_lineage_sha256=PINNED_LINEAGE_SHA256,
        activation_manifest_key=activation.object_store_key,
        activation_manifest_sha256=activation.content_sha256,
        activation_manifest_byte_count=activation.byte_count,
        source_files=files, total_source_byte_count=total)
    semantic = {key: item for key, item in value.to_record().items()
                if key not in ("projection_id", "projection_sha256")}
    digest = hashlib.sha256(_base._canonical(semantic)).hexdigest()
    return dataclasses.replace(value, projection_sha256=digest,
                               projection_id=PROJECTION_ID_PREFIXES[percent] + digest[:24])


def build_short_window_tilt_projection(prior_delta_package, latest_package, percent):
    value = _build_unpinned(prior_delta_package, latest_package, percent)
    manifest = hashlib.sha256(_base._canonical(tuple((item.project_path,
        item.content_sha256, item.byte_count) for item in value.source_files))).hexdigest()
    files = {item.project_path: item for item in value.source_files}
    if (value.projection_sha256 != PINNED_PROJECTION_SHA256S.get(percent)
            or value.profile_sha256 != PINNED_PROFILE_SHA256S.get(percent)
            or manifest != PINNED_SOURCE_MANIFEST_SHA256S.get(percent)
            or value.total_source_byte_count != PINNED_TOTAL_SOURCE_BYTES.get(percent)
            or {path: item.content_sha256 for path, item in files.items()} != PINNED_FILE_SHA256S.get(percent)
            or {path: item.byte_count for path, item in files.items()} != PINNED_FILE_BYTE_COUNTS.get(percent)):
        _error("recent projected profile, source, or manifest changed from exact pin")
    return value


CORRECTED_INPUT_SHA256 = "66e441f73d624e63464561ba725d30e751d575785abd2aef9b126ad16364aa12"
CORRECTED_INPUT_BYTE_COUNT = 24307
CORRECTED_PROJECTION_SHA256S = {
    100: "a5fff0112a08ca453fac5b01740a89eeb67bc72a1adecbfb1b9cbe686139ab26",
    120: "1aad7dc4b7083dd8d062d08f2ca3d239d142e9c5dc4e93e5fc50fbd6fa5a7b32",
    140: "91747ad28ccf17784a3d40f4bc374a12c74c7289da7be3659739c7fa899ff4d0",
    160: "d79ca9149f963079cbca4de91fbab670454910dc92d3921b97e28f565a6859ea",
    180: "89461345526643e61be70badf7a9610d664434b092ba353fc7f534f050de4882",
    200: "8efe09156adddd25dab77f489220cc6a9aeb5e8481516c75fbd9f24bed6d76cc",
}
CORRECTED_SOURCE_MANIFEST_SHA256S = {
    100: "977023de3f2ad18445d1d5e992417c9ff06e93954085c22f323f4b59f10cea68",
    120: "ad7ae57beeb9ed140cd0441228d5ed274639e9cb45db19e8d662a1e41e240e7e",
    140: "f787e29374076bb36a2cde5499aa8dabf48bc7fdf126a72112364e3f34e22603",
    160: "69628fb750f270d4de148e153bb709fdb85ccc0e84713a21451dd9939857e613",
    180: "22974f9ffc7ec011381f6a187960ad6ad77387483d7367597d1a018cbc9e5a13",
    200: "ed0d135c1c150c489542c69eb027803b9d448d1cee14842ba27ac83aa233e875",
}


def _correct_input_reader(source):
    """Port only Mia's measured direct-read correction, retaining byte authority."""
    original = _prior._r194.PINNED_FILE_SHA256S["accepted_risk_order_level_input_runtime.py"]
    if type(source) is not str or hashlib.sha256(source.encode("ascii")).hexdigest() != original:
        _error("recent direct-read predecessor input source changed")
    old = '''    try:
        contains = store.contains_key(key)
    except Exception as exc:
        raise AcceptedRiskOrderLevelInputRuntimeError(
            "preliminary Object Store existence check failed"
        ) from exc
    if type(contains) is not bool or not contains:
        _error("preliminary Object Store object is unavailable")
'''
    corrected = _replace(source, old, "")
    corrected = _replace(corrected, '"preliminary Object Store object read failed"',
                         '"preliminary Object Store object is unavailable"')
    payload = corrected.encode("ascii")
    if len(payload) != CORRECTED_INPUT_BYTE_COUNT or hashlib.sha256(payload).hexdigest() != CORRECTED_INPUT_SHA256:
        _error("recent direct-read correction differs from retrieved Mia source")
    return corrected


def _build_corrected_unpinned(prior_delta_package, latest_package, percent):
    original = build_short_window_tilt_projection(prior_delta_package, latest_package, percent)
    files = tuple(_base._source_file(item.project_path,
        _correct_input_reader(item.source_bytes.decode("ascii")).encode("ascii"))
        if item.project_path == "accepted_risk_order_level_input_runtime.py" else item
        for item in original.source_files)
    value = dataclasses.replace(original,
        schema=f"arv2-six-universe-order-qc-projection-tilt{percent}-recent-direct-read-v2",
        source_files=files, total_source_byte_count=sum(item.byte_count for item in files))
    semantic = {key: item for key, item in value.to_record().items()
                if key not in ("projection_id", "projection_sha256")}
    digest = hashlib.sha256(_base._canonical(semantic)).hexdigest()
    return dataclasses.replace(value, projection_sha256=digest,
        projection_id=f"arv2-six-universe-order-tilt{percent}-recent-direct-read-qc-projection-" + digest[:24])


def build_corrected_short_window_tilt_projection(prior_delta_package, latest_package, percent):
    """A separately pinned transport correction; all economic profiles unchanged."""
    value = _build_corrected_unpinned(prior_delta_package, latest_package, percent)
    manifest = hashlib.sha256(_base._canonical(tuple((item.project_path,
        item.content_sha256, item.byte_count) for item in value.source_files))).hexdigest()
    if (value.projection_sha256 != CORRECTED_PROJECTION_SHA256S.get(percent)
            or manifest != CORRECTED_SOURCE_MANIFEST_SHA256S.get(percent)
            or value.profile_sha256 != PINNED_PROFILE_SHA256S.get(percent)):
        _error("recent corrected projection differs from independent source pins")
    return value
