"""Executable, content-addressed preregistration and outcome-access gate."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import threading
import weakref
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping

from data.exchange_calendar import ExchangeCalendarError, is_trading_session

from .artifact_io import (
    ArtifactIOError,
    read_stable_regular,
    revalidate_regular,
)
from .canonical import (
    CanonicalEvidenceError,
    canonical_json_bytes,
    capture_frozen_container_authority,
    frozen_container_authority_is_current,
    require_canonical_json_bytes,
)
from .dataset import (
    DatasetVerificationError,
    capture_clean_git_lineage,
    compute_package_source_sha256,
    git_commit_is_ancestor,
    load_normalized_dataset,
    read_git_bytes,
    read_git_text,
    revalidate_normalized_dataset,
)
from .snapshot import load_verified_snapshot, revalidate_verified_snapshot


class PreregistrationError(ValueError):
    """A research choice is missing, edited, spent, or outcome-contaminating."""


REQUIRED_CELL_IDS = (
    "shared_holdout",
    "contaminated_legacy_periods",
    "canonical_family",
    "channel_family_policy",
    "availability_rule",
    "label_contract",
    "corporate_action_contract",
    "walk_forward_contract",
    "inference_contract",
    "mandatory_controls",
    "missing_control_policy",
    "universe_contract",
    "normalization_contract",
    "stock_topology",
    "topology_comparison_hierarchy",
    "observation_rule_parity",
    "cost_contract",
    "holdings_contract",
    "portfolio_contract",
    "multiplicity_family",
    "historical_evaluation_contract",
    "lane_validation_period",
    "three_lane_selection_correction",
    "valid_null_closes_family",
    "legacy_reproduction_policy",
)

MANDATORY_CONTROLS = (
    "earnings_guidance",
    "immediate_price_jump",
    "liquidity",
    "momentum",
    "sector",
    "size",
    "volatility",
)
_TOP_KEYS = {
    "schema",
    "status",
    "spec_id",
    "spec_hash",
    "producing_commit",
    "reviewed_by",
    "reviewed_at",
    "cells",
    "looks",
}
_CELL_KEYS = {"cell_id", "state", "value", "source"}
_LOOK_KEYS = {
    "look_id",
    "family_id",
    "state",
    "validation_start",
    "validation_end",
    "dataset_id",
    "code_identity",
    "cost_cell_hash",
    "topology_id",
}
_REGISTRY_KEYS = {"schema", "entries"}
_REGISTRY_ENTRY_KEYS = {
    "spec_id",
    "spec_hash",
    "artifact_sha256",
    "spec_path",
    "review_commit",
    "reviewed_by",
    "reviewed_at",
}
_CONTAMINATED_PERIOD_KEYS = {"start", "end", "disposition", "reason"}
_CORPORATE_ACTION_KEYS = {
    "source_id",
    "source_sha256",
    "point_in_time",
    "split_policy",
    "cash_dividend_policy",
    "delisting_policy",
    "missing_terminal_return",
}
_UNIVERSE_KEYS = {
    "security_master_id",
    "security_master_sha256",
    "point_in_time",
    "listing_venues",
    "issuer_incorporation",
    "instrument_types",
    "excluded_instrument_types",
    "share_class_policy",
    "include_delisted",
    "current_ticker_joins",
    "unknown_identity",
}
_NORMALIZATION_KEYS = {
    "population",
    "method",
    "peer_hierarchy",
    "minimum_total_names",
    "minimum_active_names",
    "structural_zero",
    "clipping",
    "residualization",
    "degenerate_group",
}
_HISTORICAL_EVALUATION_KEYS = {
    "eligible_history_start",
    "development_end",
    "history_extension_policy",
    "market_benchmark",
    "regime_signal_timing",
    "stress_rule",
    "boom_rule",
    "ordinary_rule",
    "formal_selection_policy",
    "regime_output_policy",
    "named_episode_policy",
    "named_episodes",
}
_NAMED_EPISODE_KEYS = {"episode_id", "start", "end", "label"}
_STOCK_TOPOLOGY_KEYS = {"topology_id", "primary_cell_id", "cells"}
_STOCK_CELL_KEYS = {
    "cell_id",
    "signal",
    "sign",
    "half_life_sessions",
    "threshold",
    "clip",
    "residualization",
}
_MULTIPLICITY_KEYS = {
    "family_id",
    "alpha",
    "correction",
    "permanent_cell_ids",
    "permanent_look_ids",
}

REVIEWED_SPEC_REGISTRY_PATH = (
    Path(__file__).resolve().parent / "specs" / "reviewed_spec_registry.json"
)
LEGACY_LOCAL_LOOK_LEDGER_PATH = (
    Path(__file__).resolve().parents[2]
    / "artifacts"
    / "analyst_revisions_v2"
    / "permanent_look_ledger.sqlite3"
)
PERMANENT_LOOK_AUTHORITY_PATH = (
    Path(__file__).resolve().parent
    / "specs"
    / "permanent_look_authority.json"
)
INFRASTRUCTURE_LOOK_LEDGER_SCHEMA = "arv2-infrastructure-look-ledger-v1"
INFRASTRUCTURE_LOOK_LEDGER_ID_PREFIX = "arv2-infrastructure-look-ledger-"
INFRASTRUCTURE_LOOK_LEDGER_HASH = (
    "4a726bcdd9b7232f34a1eaf891f7b8f83334002396aa48720b19abd22391305e"
)
INFRASTRUCTURE_LOOK_LEDGER_FILENAME = (
    f"arv2_infrastructure_look_ledger.{INFRASTRUCTURE_LOOK_LEDGER_HASH}.json"
)
INFRASTRUCTURE_LOOK_LEDGER_PATH = (
    Path(__file__).resolve().parent / "specs" / INFRASTRUCTURE_LOOK_LEDGER_FILENAME
)
INFRASTRUCTURE_LOOK_LEDGER_ARTIFACT_SHA256 = (
    "e837946d6fe9d31f16d4a901f878e965036f6931f8ed5bb1806fdb5a1c83cdd9"
)
INFRASTRUCTURE_LOOK_LEDGER_MAX_BYTES = 64 * 1024
INFRASTRUCTURE_LOOK_OWNER_DECISION_ID = (
    "arv2-owner-r082-infrastructure-look-accounting-20260917"
)
_DISCOVERY_RECONCILIATION_ARTIFACT_SHA256 = (
    "67071bcafa3ec65912983ba0c0834a5980ffaac63c0c2c75bb2f4c3720460a15"
)
# Each tuple is: shared ledger ordinal, discovery attempt ordinal, QC project
# id, QC backtest id, terminal status, one-use-permit start, plan SHA-256,
# preparation-summary artifact SHA-256, and execution-permit artifact SHA-256.
# These are identity/status-only facts from a statistics-free reconciliation;
# no result, statistic, log, chart, order, provider row, or outcome was read.
_DISCOVERY_INFRASTRUCTURE_LOOKS = (
    (31, 7, 36536115, "0014d18dc88f67f958d559a183079a86", "Runtime Error", "2026-09-14T15:08:30.552233Z", "9493a2e0644e3cabd50d25a1f574e89678111f087dfcb9ec96aff5307657dc6a", "732f5eba253a6ff2f4cff8a9e878e5092c50cecc52e93a57f2301a13f9f0a873", "48a334b445075da5ef6fa967cbfbafdb29cbfe0374b3ac1cf9c38b85feb7c2e7"),
    (32, 8, 36536326, "1054c989da3711446af17a557b637733", "Runtime Error", "2026-09-14T15:14:33.142831Z", "68646eb3b6c0505d9372ff2e0e8ba895d18523135f06977d56169772bf927132", "9dab0bdae7eb237eb72da29191b04a2fa6960931c6e664c6524861f6ba6c7d9d", "f2f1ad9c4017a537f42c751646f38a835da91651dc449b58777dea10bc69d4d9"),
    (33, 9, 36536574, "73a386ec1c1b7b026afacb85a42fddba", "Runtime Error", "2026-09-14T15:20:43.298730Z", "1cd49971111096dc7826b226f0cb5731bf166cce580ffe9805e0f6a0cd6dcd2d", "4075cb8df1bc2d4f2956fbfccd97f3eb17796656d7f9ff0ad1083a67918b08c7", "cb9752cb3150a5292cdca12674a87d9b3dd8c4a08a97aef89b1416823dd7fccf"),
    (34, 10, 36536795, "44d6fe47dfa9406b3b03215f4dae3306", "Runtime Error", "2026-09-14T15:26:52.820042Z", "03e54b4ad6dadf0157b20bc2d0f34d271f277c1906e93df8b0e36d1f355497a4", "46086d5da7f00328a51ed816ddd0db8523dd5af46adbeeec0ee1b6fcb82ab0ce", "7d6d3e7ad17d535f60ac57cc54774b929f9b3f69fb9a2d00702138b6b17369c7"),
    (35, 12, 36544563, "3711535499f0da3fee6977c66375acbf", "Runtime Error", "2026-09-14T19:08:35.288780Z", "882ff93134754f517813f3b08207285d3eab5a68d9538cafac4663908f2c82cc", "8a919b417246de1a30e79d8bd55a8823d1f54e13c980e1eba8d26d32ed2bc85b", "5db1e2c77b0a6638f56a989d12b8649494eddfeb77b7636b288e8d4c3acff453"),
    (36, 14, 36548449, "a7a5622f29a92bb18be0e52224683743", "Runtime Error", "2026-09-14T20:52:30.669515Z", "7727af3f5a67f53d0a60962b9d6bc354cae2c5b92bbc2838da9c2189cb4c2c01", "8a6b32e4496b404565a5a77d993d1c23aa30139bc4ab374963a5c0756dba6f0c", "b4afdca2fdbf87d71536ae47344c9ba05e9f2659ff5f9054da098b5f1201d3df"),
    (37, 15, 36548598, "526c6affd022a6d3ab95e54adc5d9eed", "Runtime Error", "2026-09-14T20:57:30.007693Z", "c1222692935ca7f047b330bbe79bb2544fe6db4e8bc74f88f3ace70b699a4559", "c836f7e818bc794ebc126e19f1e451fc18177568c1dc86f3e474c7dc9b7f06af", "fbe6f2a84a22aa61482ad4c148888bbbd17c2c1c27e4745919220dc1460fa3cf"),
    (38, 18, 36548747, "5409fcd91a1f3618ce071425591750e5", "Runtime Error", "2026-09-14T21:02:41.854770Z", "18a5bbd1544a74b4464fa612a711365856e6b95905c5c8f0952ef3e598695ab5", "f9d751449ed50fdebd9274dd1e5c6b77f7b32f249bfe7735cbd05abab285eca2", "23aa1bce3749339795c7afbfa5a07f80abc86fb402827b4f4ea77fbe47cde0e6"),
    (39, 19, 36548862, "9493b882011a4b51cc1333b6709e14ad", "Runtime Error", "2026-09-14T21:06:14.325121Z", "2dd2c00c81487830d1d41d2db41804ac6b82210865d725c95f49cf0bd1a96c20", "a2cc3f15740a5fb7ad2a8a405c26ca1b7d21b4f75afed2124fcc5bbec237a1b1", "1d4c4a14d41cc60d98ba728a8aedb2241856fa1a912b6faa4dc647574291dae7"),
    (40, 20, 36549142, "4937c65e0e7d442fd4268102d4cd0d42", "Runtime Error", "2026-09-14T21:15:01.031776Z", "efefbaeadd865346600b0f47d0c34d03bb9cfb294f949a6950fb59734b908ad4", "0350e042d0586cc2aa5f3a84da68f9cc6dec0244bd1ad419c8e93b9208769602", "da31020c70dba83bd1f57856f0b1225fa38da8ed76edbae89dfa6308a06028b0"),
    (41, 21, 36549260, "c2138164f23169cbd1188e8349b9558d", "Runtime Error", "2026-09-14T21:19:25.374328Z", "ef70b8efaafb7170acc3bfce8c08ce7c814870f0ef0c8186db9deba92e866b3b", "3691d4deaa014b081828b4e2502f4a4971f55f8be8c73111a54cff18608801a4", "32d7519e56431464de2800e91f5ec823ab3ecbfe92dd9548d33a1711d053be47"),
    (42, 22, 36549367, "c042d1cf806c5e28b291bb87e0673ac3", "Runtime Error", "2026-09-14T21:23:07.172869Z", "9c1bff27b6652dbd93a4871954199c196de08c997cf3a56959eff433becc6def", "fcc9efc10d164b9c928878da57a47feb597817953e9e4d94d482db876412be44", "1e4f8bb36fe126a185cad837a4ad689ef5d8d9a77e350e7dfa7d82bb2b566963"),
    (43, 23, 36549502, "962664739f6c769f7eea78083deee4d9", "Runtime Error", "2026-09-14T21:27:13.473771Z", "51e642bcbcf68808ff75d4ee36af0026a62f0ada43cfac947c289cd791ecc9f4", "7d9d099d70f30eadd45952e5d6c664af0ba011dc45a18d181d53b5122c8345cc", "6a5c712bbd5079735b10c401f90bfe8fe06cb5f43a4b9f509a37a023d10e5dd1"),
    (44, 24, 36549608, "736d365c3275b072246c47a92bb15752", "Runtime Error", "2026-09-14T21:30:59.423804Z", "f5158cfb42789653c4c76018c0dbeacb44daa496da28a829219dc59e757d9638", "89b531576dbb7ca545993599f8f4253bc3cc307b15dbeb9640e5699617705da0", "91f27f958256d1e9d449dcb945004f858409df5d2acd3852f7c3a7aa8a988279"),
    (45, 25, 36549752, "1501f80835f2a9f763343ca53e34db56", "Runtime Error", "2026-09-14T21:35:46.449525Z", "d8bc2a69ef4e6b81c322b24b929fb36bcf52857f58648364044a58d540ee3ad1", "11a4ec4dad22d7e7d76215578f54f24bb5ff325dd4b1cb1e0d4b845cd348f223", "fdda19d5900c776ab6f8f2343548612c4511b338574362eda48cc6dbc917293f"),
    (46, 26, 36549861, "564537e6ea7831465eaf2c37cb59190e", "Runtime Error", "2026-09-14T21:39:54.588192Z", "26469244b335274ce6ef17a05191705bcade018c931922bcbfa2882cd5146d96", "fe2a6a8637b75418ac07073692d1d0db88ee2927f8552f6f1dd59fec8a37a7f2", "5bbb0eba936bd175b602796b34fdab95ba78d16bb2f9c55111b7748fbcf3b8ab"),
    (47, 27, 36549947, "3c0bd1ff2d1afa826ed1259b59064272", "Runtime Error", "2026-09-14T21:43:02.830087Z", "fa981c59a6fc0c9e043b386f3457ec803758f9a993204e045d0a10017b7aa8fd", "07a0d7325e9685b6b12d92a58cd87abf28fc990f30d6877732859f88063492fb", "48b2789ed929d8410c420a79cc88e2bdc6f2223a57f630c29a1ea10f27f35f3d"),
    (48, 28, 36550029, "18b9eb494c5e843a74ec62de2da831a6", "Runtime Error", "2026-09-14T21:45:42.893554Z", "877a5183c2d2db491807e32d75beca1b5fe28c314c66b91db29cb11d7cccfed3", "4281c70be28deb1d8e66a08745eefe8931961c67f164f5241f9fe1ac75f25dd8", "f1993d33dc558bfd5922731d0f0b4c34e9e108e0fac6916419582b93da09f519"),
    (49, 29, 36550151, "1db646acc22f79250827b5896f2b7824", "Runtime Error", "2026-09-14T21:50:40.433171Z", "82d23cd3ff57407f05e9cc1674a1677047d800658c9387d5d435b6c7fc58fbe3", "d7c7b3e54b3716e98c3f0a7e44cd219ef10941f74b01c6c426a1e9d3b6321aa9", "89a8ccb4b32db37995d03bbe8594b612d447b279ac367f1d92c2c5019e1970db"),
    (50, 30, 36550309, "d81e7304db805a9d5fea3f8159bc23d6", "Runtime Error", "2026-09-14T21:56:10.292118Z", "77ce0d8960ce40a0f1e7dd12e0512419b66033af49217b980811421d9b076dec", "68096c9bc77a048af89b8f39a23d433f32b8d5363da5e7f69d92d57a807249a9", "afcd8aee2d42b54a06393235c99a8239918ced0e388d1b2eef3b1f9d41fb5ed3"),
    (51, 31, 36550360, "0cd205c129624cb83e0e87a580cd5b34", "Runtime Error", "2026-09-14T21:58:27.152407Z", "478236be3c8e2fa5b4e93cb6d1d8c55a643b14c0ead45ba12599a6d8b3f7047e", "61d754bc67a8605f0432e466b1f805b53d5a7a05e026298532724f54f13b00ef", "9102cfbf0e1f28240951df1bc630878de7bc578d9fed7e1db9670bedec5c7f48"),
    (52, 32, 36550482, "1d1ee522af4176cdf8bfeae487d91e03", "Completed.", "2026-09-14T22:03:03.554521Z", "e785951f72883f6e092609732b75cc439b777e5d186bb09119113663ab2f5164", "46449e3eef693faaf4a6cf02e04eb08a4bca41e22af0c6d2f32eecaf96717273", "59eb61ef8e23fd402b000a940df893f28d1cc074120a57a17dc72ea03a46a77d"),
)
_QC_FIRST_PLAN_PATH = (
    Path(__file__).resolve().parent / "specs" / "arv2_qc_first.draft.json"
)
_FOUR_FAMILY_MULTIPLICITY_PATH = (
    Path(__file__).resolve().parent
    / "specs"
    / "arv2_four_family_multiplicity.structural.json"
)
_PERMANENT_LOOK_AUTHORITY_ARTIFACT_SHA256 = (
    "819cb514dfcefd770bd1c0113cfa2484f521ac6dda0c0a36e98f977903ad5990"
)
_QC_FIRST_PLAN_ARTIFACT_SHA256 = (
    "8339238dd5ce32ed7b351aab2662fb408cc7d9a3c62ff89bf8b1d14f20acd081"
)
_FOUR_FAMILY_MULTIPLICITY_ARTIFACT_SHA256 = (
    "2e9f390ec54f01e6635b67972711c38212a5f853489e16c1de2a508212278648"
)
REVIEW_REGISTRY_SCHEMA = "arv2-reviewed-spec-registry-v1"
PERMANENT_LOOK_AUTHORITY_SCHEMA = "arv2-permanent-look-authority-v1"
ZERO_ACCESS_AUTHORITY_ID = "arv2-zero-access-no-external-authority"
OWNER_DECISION_CANDIDATE_STATUS = (
    "owner_decisions_frozen_pending_external_bindings_and_review"
)
PRIMARY_OUTCOME_LOOK_ID = "arv2-look-legacy-v1-migration-only"
SUPERSEDED_LOOK_IDS = frozenset({"arv2-look-stock-primary-001"})
SUPERSEDED_VALIDATION_PERIODS = frozenset(
    {
        (
            "2026-09-01",
            "2027-08-31",
        )
    }
)
LEGACY_V1_OUTCOME_AUTHORITY_RETIRED_REASON = (
    "legacy v1 outcome authority was superseded unspent; a complete reviewed "
    "QC-first v2 evaluation specification is required"
)
_PENDING_SOURCE_CELL_IDS = frozenset(
    {"corporate_action_contract", "universe_contract"}
)
_REVIEWED_AUTHORITY = object()
_MISSING_REVIEWED_ROOT = object()
_PERMIT_AUTHORITY = object()
_REVIEWED_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType["ReviewedPreregistration"],
        Path,
        tuple[object, ...],
        tuple[object, ...],
        "InfrastructureLookLedgerBinding",
    ],
] = {}
_REVIEWED_AUTHORITIES_LOCK = threading.RLock()


def _sha256(value: object, name: str, length: int = 64) -> str:
    if (
        not isinstance(value, str)
        or len(value) != length
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PreregistrationError(f"{name} must be a lowercase {length}-hex digest")
    return value


def _dataset_id(value: object, name: str = "dataset_id") -> str:
    if not isinstance(value, str) or not value.startswith("arv2_ds_"):
        raise PreregistrationError(f"{name} must use arv2_ds_<sha256>")
    _sha256(value.removeprefix("arv2_ds_"), name)
    return value


def _text(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(ord(character) < 32 for character in value)
    ):
        raise PreregistrationError(f"{name} must be canonical non-empty text")
    return value


def _positive_int(value: object, name: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise PreregistrationError(f"{name} must be an integer >= {minimum}")
    return value


def _decimal_text(
    value: object,
    name: str,
    *,
    minimum: Decimal | None = None,
    maximum: Decimal | None = None,
    strictly_positive: bool = False,
) -> Decimal:
    if not isinstance(value, str) or not value or value != value.strip():
        raise PreregistrationError(f"{name} must be a canonical decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise PreregistrationError(f"{name} must be a finite decimal string") from exc
    if not parsed.is_finite() or str(parsed) != value:
        raise PreregistrationError(f"{name} must be a canonical finite decimal string")
    if strictly_positive and parsed <= 0:
        raise PreregistrationError(f"{name} must be positive")
    if minimum is not None and parsed < minimum:
        raise PreregistrationError(f"{name} is below its minimum")
    if maximum is not None and parsed > maximum:
        raise PreregistrationError(f"{name} exceeds its maximum")
    return parsed


def _date(value: object, name: str) -> date:
    if not isinstance(value, str):
        raise PreregistrationError(f"{name} must be canonical YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise PreregistrationError(f"{name} must be canonical YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise PreregistrationError(f"{name} must be canonical YYYY-MM-DD")
    return parsed


def _session(value: object, name: str) -> date:
    parsed = _date(value, name)
    try:
        valid = is_trading_session(parsed.isoformat())
    except ExchangeCalendarError as exc:
        raise PreregistrationError(f"{name} cannot be resolved by the exchange calendar") from exc
    if not valid:
        raise PreregistrationError(f"{name} must be an NYSE trading session")
    return parsed


def _aware_instant(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise PreregistrationError(f"{name} must be an aware ISO instant")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PreregistrationError(f"{name} must be an aware ISO instant") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PreregistrationError(f"{name} must be an aware ISO instant")


def _strict_json(value: object, path: str = "value") -> None:
    if (
        value is None
        or type(value) is str
        or type(value) is bool
        or type(value) is int
    ):
        return
    if isinstance(value, float):
        raise PreregistrationError(f"{path} cannot use binary floating-point")
    if isinstance(value, list):
        for index, item in enumerate(value):
            _strict_json(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        if any(not isinstance(key, str) or not key for key in value):
            raise PreregistrationError(f"{path} keys must be non-empty strings")
        for key, item in value.items():
            _strict_json(item, f"{path}.{key}")
        return
    raise PreregistrationError(f"{path} contains a non-JSON value")


def _reject_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    """Build a JSON object while refusing ambiguous duplicate names."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PreregistrationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _deep_freeze(value: object) -> object:
    """Detach loaded authority from caller-owned mutable JSON containers."""
    if isinstance(value, dict):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _cell_sha256(value: object) -> str:
    _strict_json(value)
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _canonical_payload(raw: Mapping[str, object]) -> bytes:
    without_hash = dict(raw)
    without_hash["spec_hash"] = None
    without_hash["spec_id"] = None
    return json.dumps(
        without_hash, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _reconciled_discovery_infrastructure_entries() -> list[dict[str, object]]:
    """Project the 22 authenticated, statistics-free discovery run identities."""

    entries: list[dict[str, object]] = []
    for position, row in enumerate(_DISCOVERY_INFRASTRUCTURE_LOOKS):
        (
            shared_ordinal,
            attempt_ordinal,
            project_id,
            backtest_id,
            terminal_status,
            started_at_utc,
            plan_sha256,
            preparation_summary_sha256,
            execution_permit_sha256,
        ) = row
        if shared_ordinal != 31 + position:
            raise PreregistrationError(
                "discovery infrastructure-look sequence changed"
            )
        entries.append(
            {
                "accounting_id": (
                    f"arv2-infrastructure-look-fundamental-discovery-"
                    f"a{attempt_ordinal:06d}"
                ),
                "operation_id": (
                    f"arv2-qc-fundamental-discovery-a{attempt_ordinal:06d}"
                ),
                "shared_look_ledger_entry_id": f"R-{shared_ordinal:03d}",
                "look_class": (
                    "outcome_free_qc_fundamental_universe_discovery_"
                    "infrastructure_research_look"
                ),
                "status": terminal_status,
                "phase": "STATISTICS_FREE_TERMINAL_STATUS_RECONCILED",
                "started_at_utc": started_at_utc,
                "finished_at_utc": None,
                "attempt_ordinal": attempt_ordinal,
                "project_id": project_id,
                "backtest_id": backtest_id,
                "plan_sha256": plan_sha256,
                "preparation_summary_artifact_sha256": (
                    preparation_summary_sha256
                ),
                "execution_permit_artifact_sha256": execution_permit_sha256,
                "statistics_free_reconciliation_artifact_sha256": (
                    _DISCOVERY_RECONCILIATION_ARTIFACT_SHA256
                ),
                "compile_state": "BuildSuccess",
                "compile_submission_count": 1,
                "backtest_submission_count": 1,
                "conservative_research_look_count": 1,
                "spent_before_submission": True,
                "same_entry_retry_permitted": False,
                "later_fresh_attempt_permitted": True,
                "organization_binding_authenticated": True,
                "backtest_terminal_status_accessed": True,
                "backtest_detail_endpoint_called": False,
                "performance_statistics_inspected": False,
                "result_values_inspected": False,
                "redacted_log_accessed": False,
                "production_inputs_accessed": False,
                "qc_fundamental_data_access_possible": True,
                "provider_rows_retained_or_disclosed": False,
                "outcomes_accessed": False,
                "orders_permitted": False,
                "development_evaluation_consumed": False,
                "permanent_family_look_consumed": False,
                "confirmatory_alpha_consumed": False,
            }
        )
    return entries


def _r079_infrastructure_look_entry() -> dict[str, object]:
    """Project the spent canary without claiming an aggregate output value."""

    return {
        "accounting_id": "arv2-infrastructure-look-pit-market-cap-membership-r079",
        "operation_id": "arv2-qc-pit-market-cap-membership-coverage-r079",
        "shared_look_ledger_entry_id": "R-079",
        "look_class": (
            "outcome_free_qc_pit_market_cap_membership_coverage_"
            "infrastructure_research_look"
        ),
        "status": "Completed.",
        "phase": "LOCKED_OUTPUT_READ_AMBIGUITY_NO_VALUES_INSPECTED",
        "started_at_utc": "2026-09-17T07:00:00Z",
        "finished_at_utc": None,
        "project_id": 36643367,
        "project_name": (
            "26 ARV2_PIT_MARKET_CAP_MEMBERSHIP_COVERAGE_RETRY - 20260917"
        ),
        "backtest_id": "a2b58090c188fd040217af6c302751b8",
        "backtest_name": (
            "ARV2 outcome-free PIT market-cap and ETF-membership coverage retry 1"
        ),
        "compile_id": (
            "b59b398bbf9998e5d0f8e0d89de890b0-"
            "9111c260885b3d38dbcf7442a7cd54ab"
        ),
        "plan_sha256": (
            "b5d4385ef36764121aaf23ae4df4a4c08bca46a6137f6c8f3b047f207237698f"
        ),
        "projection_sha256": (
            "fc7b6963a4b665bcc16999fa5543c314a9c284228d9e994c15590b90437c150b"
        ),
        "project_source_set_sha256": (
            "d4a7b47ded6928e836c877fc00a1c310bcdad682e80ed1c347c4438d10f173f1"
        ),
        "launch_receipt_artifact_sha256": (
            "cf76f4a0093a8c13086eb502c447e58ca5b5dca28a8fb7c2f933758c2ad78752"
        ),
        "launch_receipt_sha256": (
            "334ec5d733f9fb40cb6a32f3d38da23539d64f6a3d6258be9b342c83f70fb300"
        ),
        "terminal_status_receipt_artifact_sha256": (
            "b6cb6c10707ee401823da0f74e0ade5ecf32c976ba944430dd293a939ab854ea"
        ),
        "terminal_status_receipt_sha256": (
            "ce92a3e69a21808e79fc379885ee8cd344064b68cee5fb6bd2138ec3cf6a4174"
        ),
        "output_read_permit_artifact_sha256": (
            "ddf28ef22c2c1a9bbe91ea63cfec2eb285ba500773481eadd53d481c3a01e272"
        ),
        "output_read_permit_sha256": (
            "7ec1c1ec41cc40043f8169e91ccc76ca9d02a5452681b77b452284963f46aa5f"
        ),
        "compile_state": "BuildSuccess",
        "compile_submission_count": 1,
        "backtest_submission_count": 1,
        "conservative_research_look_count": 1,
        "spent_before_submission": True,
        "same_entry_retry_permitted": False,
        "later_fresh_attempt_requires_new_authority_and_ledger_entry": True,
        "organization_binding_authenticated": True,
        "backtest_terminal_status_accessed": True,
        "include_statistics": False,
        "backtest_detail_endpoint_called": False,
        "performance_statistics_inspected": False,
        "result_values_inspected": False,
        "output_read_permit_spent": True,
        "output_read_outcome_ambiguous": True,
        "terminal_pointer_value_inspected": False,
        "content_addressed_output_value_inspected": False,
        "aggregate_output_values_inspected": False,
        "price_or_return_values_accessed": False,
        "outcomes_accessed": False,
        "raw_input_values_retained_or_disclosed": False,
        "orders_permitted": False,
        "development_evaluation_consumed": False,
        "permanent_family_look_consumed": False,
        "confirmatory_alpha_consumed": False,
        "error": (
            "output read became ambiguous after permit spend; no output object "
            "value was inspected"
        ),
    }


def _r080_infrastructure_look_entry() -> dict[str, object]:
    """Project the bounded named-refusal attestation without outcome access."""

    return {
        "accounting_id": "arv2-infrastructure-look-pit-market-cap-membership-r080",
        "operation_id": "arv2-qc-pit-market-cap-membership-summary-r080",
        "shared_look_ledger_entry_id": "R-080",
        "look_class": (
            "outcome_free_qc_pit_market_cap_membership_coverage_"
            "infrastructure_research_look"
        ),
        "status": "Completed.",
        "phase": "COMPLETED_NAMED_REFUSAL_ATTESTATION_RECONCILED",
        "started_at_utc": "2026-09-17T07:54:14Z",
        "finished_at_utc": None,
        "project_id": 36644379,
        "project_name": (
            "28 ARV2_PIT_MARKET_CAP_MEMBERSHIP_SUMMARY_R080 - 20260917"
        ),
        "backtest_id": "3a9dbca993f41ac41177d2c15bb84450",
        "backtest_name": (
            "ARV2 R080 outcome-free PIT market-cap and ETF-membership summary"
        ),
        "compile_id": (
            "e91fc5cd71eb0d7fdeb69bed5c00dfd2-"
            "357decf66161ed3141fc9657f453c5df"
        ),
        "plan_sha256": (
            "8786f8fb98c52cf4f2292e0b2b7f88c8f0fe774913b642d1340fa8ef7b16ac08"
        ),
        "projection_sha256": (
            "6e4128b67ff7604551bf263a7730a02d247af28d0e37fab5fda966b6882e225f"
        ),
        "project_source_set_sha256": (
            "d511993d530a2ac223d6d9c02fcb303b58ff7ca86f4ae7bbe76509752190ae13"
        ),
        "submission_permit_artifact_sha256": (
            "df8752ce6730c9e5cf0ce1f8dc0d2f5cd1c5dde46bd3d1ac623b79bede055038"
        ),
        "submission_permit_sha256": (
            "148f14a30e170f742e73baf7f46f8a4e7a0e41378bf10a1477d282ada1ad8d81"
        ),
        "launch_receipt_artifact_sha256": (
            "9acada7c62c63b973a52dfa9ad98565c634f0176e6403a902ac96037b439e70a"
        ),
        "launch_receipt_sha256": (
            "1b1bdc49a29cb3274f574d5b6c9d9e147ca31908dbfd7ea98ac8d638d2eba6e0"
        ),
        "terminal_status_receipt_artifact_sha256": (
            "df7c98a7e7b8c35ae028d35ef08b26fed131c8cf51970a55fa0657ecab4f9759"
        ),
        "terminal_status_receipt_sha256": (
            "c1e802860139040d3c4a2a89ee6d9635f90a8bd70b1bacf90f069cddf79d87b2"
        ),
        "output_read_permit_artifact_sha256": (
            "8038446dc52596700d83eee96e2d0335047cdf0ec0776a76215a0410e67906ae"
        ),
        "output_read_permit_sha256": (
            "684f21fcbdf62494e99e74ee8a8e229f3c088fd61b5353d48aa40c9027cc66ec"
        ),
        "attestation_artifact_sha256": (
            "0ca3b24f005475d912a8e74283aef112c9f93331991f8d97a8cc1441818bfcf3"
        ),
        "attestation_schema": (
            "arv2-qc-pit-market-cap-membership-coverage-attestation-v1"
        ),
        "attestation_status": "named_refusal",
        "attestation_safe_reason": (
            "pit_coverage_refused_ValueError_1b17331bb939b176"
        ),
        "compile_state": "BuildSuccess",
        "compile_submission_count": 1,
        "backtest_submission_count": 1,
        "conservative_research_look_count": 1,
        "spent_before_submission": True,
        "same_entry_retry_permitted": False,
        "later_fresh_attempt_requires_new_authority_and_ledger_entry": True,
        "organization_binding_authenticated": True,
        "backtest_terminal_status_accessed": True,
        "include_statistics": False,
        "backtests_read": True,
        "maximum_backtests_read_calls": 1,
        "selected_summary_statistic": (
            "ARV2_PIT_MARKET_CAP_MEMBERSHIP_COVERAGE"
        ),
        "bounded_attestation_selected": True,
        "aggregate_coverage_counts_inspected": False,
        "object_store_export_performed": False,
        "full_receipt_or_pointer_exported": False,
        "performance_statistics_inspected": False,
        "price_or_return_values_accessed": False,
        "outcomes_accessed": False,
        "raw_input_values_retained_or_disclosed": False,
        "security_identifiers_retained_or_disclosed": False,
        "constituent_weights_retained_or_disclosed": False,
        "market_cap_values_retained_or_disclosed": False,
        "orders_permitted": False,
        "development_evaluation_consumed": False,
        "permanent_family_look_consumed": False,
        "confirmatory_alpha_consumed": False,
    }


def _r081_infrastructure_look_entry() -> dict[str, object]:
    """Project the second bounded named refusal without outcome access."""

    return {
        "accounting_id": "arv2-infrastructure-look-pit-market-cap-membership-r081",
        "operation_id": "arv2-qc-pit-market-cap-membership-summary-r081",
        "shared_look_ledger_entry_id": "R-081",
        "look_class": (
            "outcome_free_qc_pit_market_cap_membership_coverage_"
            "infrastructure_research_look"
        ),
        "status": "Completed.",
        "phase": "COMPLETED_NAMED_REFUSAL_ATTESTATION_RECONCILED",
        "started_at_utc": "2026-09-17T08:13:05Z",
        "finished_at_utc": None,
        "project_id": 36644829,
        "project_name": (
            "29 ARV2_PIT_MARKET_CAP_MEMBERSHIP_SUMMARY_R081 - 20260917"
        ),
        "backtest_id": "1cdc40ccd41877743ad907020a6e2e31",
        "backtest_name": (
            "ARV2 R081 outcome-free PIT market-cap and ETF-membership summary retry 1"
        ),
        "compile_id": (
            "0371095ee1bc3fbf7f5149ea6a9510b0-"
            "326f53ae48b19268d987c227d49100d8"
        ),
        "plan_sha256": (
            "bfddaa18a7c11c38a6ec1b66f18a6904590b2bb71c67b00bf733525bd00838f8"
        ),
        "projection_sha256": (
            "17d4cc56a0b3e2a28e442c74c4ff52bea1d57d45fa4cfd17c7da1b93c98887f3"
        ),
        "project_source_set_sha256": (
            "db2cb863496f9c629361ad4fae68ab508bbc2fb30d46f1645dfb20582d420c34"
        ),
        "submission_permit_artifact_sha256": (
            "7546f222dd9c64888cf0bda5ce8fb7b73bbfe8bc1f5ff1b230980c70688e09dc"
        ),
        "submission_permit_sha256": (
            "23cf8385c3692f82ea847d77b22d32e302a21bfb26e058f36258e6a3a785fed2"
        ),
        "launch_receipt_artifact_sha256": (
            "43507b6f28a5757e5ba48c4a852ec5796b9138b66e347c6a0f188ea00c73b444"
        ),
        "launch_receipt_sha256": (
            "abb700387adfa61ffe46fb32eacf05dba4ee8b21b6ccc3926bf73b603733a8a8"
        ),
        "terminal_status_receipt_artifact_sha256": (
            "2024e8a319fc9f4c459d153400210b78cde9c82c4fe772caf50def070106e5c2"
        ),
        "terminal_status_receipt_sha256": (
            "cc95bf29b46abb0dee68fde6130636ac0243ff0d5474faa19d1484abbcb19ff6"
        ),
        "output_read_permit_artifact_sha256": (
            "3feafb0a2b2b94a90e08ae9a0c7a668998aa56bdf1c639efc1db9ffc79b03543"
        ),
        "output_read_permit_sha256": (
            "56442d4aafac600a9ef537b4ea7be1fc648c7a39e4b98a02f3427930849107d8"
        ),
        "attestation_artifact_sha256": (
            "4b12471d87f9a7ed918a6a292775e6bc2527deaabc27bda7b3e80c9a2a0af8a1"
        ),
        "attestation_schema": (
            "arv2-qc-pit-market-cap-membership-coverage-attestation-v1"
        ),
        "attestation_status": "named_refusal",
        "attestation_safe_reason": (
            "pit_coverage_refused_ValueError_bef7b6927d4aa871"
        ),
        "compile_state": "BuildSuccess",
        "compile_submission_count": 1,
        "backtest_submission_count": 1,
        "conservative_research_look_count": 1,
        "spent_before_submission": True,
        "same_entry_retry_permitted": False,
        "later_fresh_attempt_requires_new_authority_and_ledger_entry": True,
        "organization_binding_authenticated": True,
        "backtest_terminal_status_accessed": True,
        "include_statistics": False,
        "backtests_read": True,
        "maximum_backtests_read_calls": 1,
        "selected_summary_statistic": (
            "ARV2_PIT_MARKET_CAP_MEMBERSHIP_COVERAGE"
        ),
        "bounded_attestation_selected": True,
        "aggregate_coverage_counts_inspected": False,
        "object_store_export_performed": False,
        "full_receipt_or_pointer_exported": False,
        "performance_statistics_inspected": False,
        "price_or_return_values_accessed": False,
        "outcomes_accessed": False,
        "raw_input_values_retained_or_disclosed": False,
        "security_identifiers_retained_or_disclosed": False,
        "constituent_weights_retained_or_disclosed": False,
        "market_cap_values_retained_or_disclosed": False,
        "orders_permitted": False,
        "development_evaluation_consumed": False,
        "permanent_family_look_consumed": False,
        "confirmatory_alpha_consumed": False,
    }


def _r082_infrastructure_look_entry() -> dict[str, object]:
    """Project the bounded successful v2 coverage attestation without outcomes."""

    return {
        "accounting_id": "arv2-infrastructure-look-pit-market-cap-membership-r082",
        "operation_id": "arv2-qc-pit-market-cap-membership-summary-r082",
        "shared_look_ledger_entry_id": "R-082",
        "look_class": (
            "outcome_free_qc_pit_market_cap_membership_coverage_"
            "infrastructure_research_look"
        ),
        "status": "Completed.",
        "phase": "COMPLETED_BOUNDED_COVERAGE_ATTESTATION_RECONCILED",
        "started_at_utc": "2026-09-17T08:42:55Z",
        "finished_at_utc": None,
        "project_id": 36645473,
        "project_name": (
            "30 ARV2_PIT_MARKET_CAP_MEMBERSHIP_SUMMARY_R082 - 20260917"
        ),
        "backtest_id": "c90394212ee91c89f0428b3533de45d9",
        "backtest_name": (
            "ARV2 R082 outcome-free PIT market-cap and ETF-membership summary retry 2"
        ),
        "compile_id": (
            "6f80f0c464f878f69df94fd5ef798366-"
            "c31cece9580ac7be5ea7293a9100cd3e"
        ),
        "plan_sha256": (
            "dfdd5f9920bd245c72ed1609f696997f620cd2c4f40e0b62f897aa081b1b1ba9"
        ),
        "projection_sha256": (
            "fb892cce42d48e658137843e5690177054c9b58470c7ee1937607b59591d6583"
        ),
        "project_source_set_sha256": (
            "9c71c5650813c4e9281f8746edd4ff2c658c1883a60f89d779cb75af6e7b812e"
        ),
        "submission_permit_artifact_sha256": (
            "5b192cf286bc7320e66d43ae93559c89a95ef8ee2fbf06e2951b84b82d57d35b"
        ),
        "submission_permit_sha256": (
            "c5ade4b694282d477e9fbf4bc1b313bffd6fff17df770c5f5ab3ca53a05d0990"
        ),
        "launch_receipt_artifact_sha256": (
            "3c7fc06f4f2933c72de9cad05205efb386ad0a03bf9ccaa8a977a1d9f8e7d7e9"
        ),
        "launch_receipt_sha256": (
            "c6a9173748ffe3691d2dc1840ea8784c54a9ec05bace8f00d5c53e19a266f6ab"
        ),
        "terminal_status_receipt_artifact_sha256": (
            "a9e82a7c3285ce8381c49eaf37e12f977d3354fa3eb93e00ade28e0d3aa25799"
        ),
        "terminal_status_receipt_sha256": (
            "b5971e3bed4879bb3b5460a68719d1b1333c7afc117d4d105e8068297473c832"
        ),
        "output_read_permit_artifact_sha256": (
            "e6b66a5f359be2aecef449884b8c69deab66109fc790c9cdf837a80d9c2fdb62"
        ),
        "output_read_permit_sha256": (
            "fb7f4fc95b2bab6ab58290cbdbe12504cdeca1341e6573a47167cdf5d4032f25"
        ),
        "attestation_artifact_sha256": (
            "60e3e3185a301aec3de7b14d5f4ad58cd10dfc4b30c39d387083fea7db74895b"
        ),
        "attestation_receipt_sha256": (
            "86e52b8653290d5aa583ef0b1e1aa4fb0949a3d37ec41c13f311f6c524b6e45f"
        ),
        "attestation_schema": (
            "arv2-qc-pit-market-cap-membership-coverage-attestation-v2"
        ),
        "attestation_status": "completed",
        "decision_session_count": 16,
        "passed_session_count": 16,
        "history_call_count": 16,
        "fetched_source_row_count": 1_944_801,
        "fundamental_duplicate_exact_sid_count": 2,
        "fundamental_duplicate_exact_sid_row_count": 2,
        "compile_state": "BuildSuccess",
        "compile_submission_count": 1,
        "backtest_submission_count": 1,
        "conservative_research_look_count": 1,
        "spent_before_submission": True,
        "same_entry_retry_permitted": False,
        "later_fresh_attempt_requires_new_authority_and_ledger_entry": True,
        "organization_binding_authenticated": True,
        "backtest_terminal_status_accessed": True,
        "include_statistics": False,
        "backtests_read": True,
        "maximum_backtests_read_calls": 1,
        "selected_summary_statistic": (
            "ARV2_PIT_MARKET_CAP_MEMBERSHIP_COVERAGE"
        ),
        "bounded_attestation_selected": True,
        "aggregate_coverage_counts_inspected": True,
        "object_store_export_performed": False,
        "full_receipt_or_pointer_exported": False,
        "performance_statistics_inspected": False,
        "price_or_return_values_accessed": False,
        "outcomes_accessed": False,
        "raw_input_values_retained_or_disclosed": False,
        "security_identifiers_retained_or_disclosed": False,
        "constituent_weights_retained_or_disclosed": False,
        "market_cap_values_retained_or_disclosed": False,
        "orders_permitted": False,
        "development_evaluation_consumed": False,
        "permanent_family_look_consumed": False,
        "confirmatory_alpha_consumed": False,
    }


def _infrastructure_look_ledger_seed() -> dict[str, object]:
    """Return the owner-confirmed accounting record without its identity."""

    return {
        "schema": INFRASTRUCTURE_LOOK_LEDGER_SCHEMA,
        "status": "owner_confirmed_frozen_infrastructure_look_accounting",
        "authority": (
            "accounting_only_no_source_outcome_alpha_family_qc_result_"
            "deployment_order_or_trading_authority"
        ),
        "ledger_id": None,
        "ledger_hash": None,
        "ledger_sequence": 6,
        "append_only_contract": {
            "entry_count": 27,
            "predecessor_entry_count": 26,
            "predecessor_ledger_artifact_sha256": (
                "d268f6e678c6d506fbccf5b675d0c8ca99e4484c059479bc159febe0733c240c"
            ),
            "successor_must_retain_every_prior_entry": True,
        },
        "owner_decision": {
            "decision_id": INFRASTRUCTURE_LOOK_OWNER_DECISION_ID,
            "b5c_consumed_one_infrastructure_research_look": True,
            "discovery_backtests_counted_conservatively": 22,
            "r079_counted_conservatively_after_backtest_launch": True,
            "r079_output_read_ambiguity_did_not_unspend_look": True,
            "r080_counted_after_backtest_launch": True,
            "r080_bounded_named_refusal_read_did_not_change_look_class": True,
            "r081_counted_after_backtest_launch": True,
            "r081_bounded_named_refusal_read_did_not_change_look_class": True,
            "r082_counted_after_backtest_launch": True,
            "r082_bounded_success_read_did_not_change_look_class": True,
            "each_launch_retained_as_a_distinct_non_overwriting_look": True,
            "development_family_permanent_and_alpha_counts_remain_unchanged": True,
            "external_arv2_development_evaluation_total_remains_21": True,
            "ambiguous_submission_is_spent_and_nonretryable": True,
            "this_accounting_artifact_grants_no_access_or_action_authority": True,
        },
        "frozen_ancestor_bindings": {
            "permanent_look_authority": {
                "artifact_sha256": _PERMANENT_LOOK_AUTHORITY_ARTIFACT_SHA256,
                "authority_id": ZERO_ACCESS_AUTHORITY_ID,
                "authority_mode": "zero_access",
                "path": (
                    "research/analyst_revisions_v2/specs/"
                    "permanent_look_authority.json"
                ),
            },
            "qc_first_plan": {
                "artifact_sha256": _QC_FIRST_PLAN_ARTIFACT_SHA256,
                "path": (
                    "research/analyst_revisions_v2/specs/"
                    "arv2_qc_first.draft.json"
                ),
                "plan_hash": (
                    "36e455e72b8750fe3f34773382870e10e62f3f40b5392ae587690bda081b85dc"
                ),
            },
            "four_family_multiplicity": {
                "artifact_sha256": _FOUR_FAMILY_MULTIPLICITY_ARTIFACT_SHA256,
                "overlay_hash": (
                    "54ab0bb69fb6fa162ca3ba6764864b230136c68c017f1e6b669034dda75b806e"
                ),
                "path": (
                    "research/analyst_revisions_v2/specs/"
                    "arv2_four_family_multiplicity.structural.json"
                ),
            },
        },
        "entries": [
            {
                "accounting_id": "arv2-infrastructure-look-b5c-refusal-smoke-002",
                "operation_id": "arv2-qc-b5c-refusal-smoke-002",
                "look_class": "data_free_infrastructure_research_look",
                "status": "LOCKED_BACKTEST_STATUS_AMBIGUITY",
                "phase": "POLLING_STATS_FREE_TERMINAL_STATUS",
                "started_at_utc": "2026-09-12T00:22:40.194284Z",
                "finished_at_utc": "2026-09-12T00:22:47.656173Z",
                "receipt_schema": "arv2-qc-b5c-refusal-smoke-receipt-v1",
                "receipt_artifact_sha256": (
                    "6cef656b40ac988afb1d81cf81784fcfad3ca7381ccfea0baabe4e14a6740fb3"
                ),
                "receipt_byte_count": 3639,
                "driver_artifact_sha256": (
                    "b19a489aca60394a2605363be5a1963a9401c37164c5f0da41ea2d45f39b70c0"
                ),
                "driver_byte_count": 34882,
                "prior_receipt_artifact_sha256": (
                    "f2c3fd7536100bb4a1e1e9a8f5e4b349ff73196d286de7916c8bed5d9930a7ae"
                ),
                "compile_state": "BuildSuccess",
                "compile_submission_count": 1,
                "backtest_submission_count": 1,
                "conservative_research_look_count": 1,
                "spent_before_submission": True,
                "ambiguous_submission_consumes_look": True,
                "retry_authorized": False,
                "organization_binding_authenticated": True,
                "sole_main_authenticated_before_compile": True,
                "backtest_terminal_status_accessed": False,
                "backtest_detail_endpoint_called": False,
                "redacted_log_access_attempted": False,
                "redacted_log_accessed": False,
                "performance_statistics_inspected": False,
                "production_inputs_accessed": False,
                "market_data_accessed_by_algorithm": False,
                "object_store_accessed_by_algorithm": False,
                "provider_rows_accessed": False,
                "orders_permitted": False,
                "development_evaluation_consumed": False,
                "permanent_family_look_consumed": False,
                "confirmatory_alpha_consumed": False,
                "error": (
                    "backtests/list returned a forbidden statistics/result field"
                ),
            }
        ]
        + _reconciled_discovery_infrastructure_entries()
        + [
            _r079_infrastructure_look_entry(),
            _r080_infrastructure_look_entry(),
            _r081_infrastructure_look_entry(),
            _r082_infrastructure_look_entry(),
        ],
        "totals": {
            "infrastructure_research_looks_spent": 27,
            "development_evaluations_spent": 0,
            "permanent_family_looks_spent": 0,
            "confirmatory_alpha_spent": False,
            "prospective_permanent_looks_remaining": 1,
        },
        "capabilities": {
            "grants_source_access": False,
            "grants_provider_access": False,
            "grants_outcome_access": False,
            "grants_infrastructure_look_authority": False,
            "grants_development_evaluation_authority": False,
            "grants_permanent_family_look_authority": False,
            "grants_confirmatory_alpha_authority": False,
            "grants_qc_access": False,
            "grants_result_access": False,
            "grants_deployment": False,
            "grants_orders": False,
            "grants_trading": False,
        },
    }


def _identify_infrastructure_look_ledger(
    seed: Mapping[str, object],
) -> dict[str, object]:
    document = dict(seed)
    document["ledger_id"] = None
    document["ledger_hash"] = None
    digest = hashlib.sha256(canonical_json_bytes(document)).hexdigest()
    document["ledger_hash"] = digest
    document["ledger_id"] = INFRASTRUCTURE_LOOK_LEDGER_ID_PREFIX + digest[:24]
    return document


def _infrastructure_look_ledger_document() -> dict[str, object]:
    return _identify_infrastructure_look_ledger(
        _infrastructure_look_ledger_seed()
    )


@dataclasses.dataclass(frozen=True)
class InfrastructureLookLedgerBinding:
    path: Path
    payload: bytes
    ledger_id: str
    ledger_hash: str
    artifact_sha256: str


def load_infrastructure_look_ledger() -> InfrastructureLookLedgerBinding:
    """Authenticate the additive accounting sidecar and frozen ancestors."""

    try:
        resolved, payload = read_stable_regular(
            INFRASTRUCTURE_LOOK_LEDGER_PATH,
            name="infrastructure-look ledger",
            maximum_bytes=INFRASTRUCTURE_LOOK_LEDGER_MAX_BYTES,
        )
    except ArtifactIOError as exc:
        raise PreregistrationError("infrastructure-look ledger is unavailable") from exc
    artifact_sha256 = hashlib.sha256(payload).hexdigest()
    if artifact_sha256 != INFRASTRUCTURE_LOOK_LEDGER_ARTIFACT_SHA256:
        raise PreregistrationError("infrastructure-look ledger artifact hash changed")
    try:
        raw = require_canonical_json_bytes(payload, "infrastructure-look ledger")
    except CanonicalEvidenceError as exc:
        raise PreregistrationError("infrastructure-look ledger is not canonical") from exc
    if not isinstance(raw, dict):
        raise PreregistrationError("infrastructure-look ledger must be an object")
    expected = _infrastructure_look_ledger_document()
    expected_payload = canonical_json_bytes(expected)
    if payload != expected_payload:
        raise PreregistrationError("infrastructure-look ledger content changed")
    if (
        expected["ledger_hash"] != INFRASTRUCTURE_LOOK_LEDGER_HASH
        or resolved.name != INFRASTRUCTURE_LOOK_LEDGER_FILENAME
    ):
        raise PreregistrationError("infrastructure-look ledger identity changed")

    ancestor_specs = (
        (
            PERMANENT_LOOK_AUTHORITY_PATH,
            _PERMANENT_LOOK_AUTHORITY_ARTIFACT_SHA256,
            "permanent-look authority ancestor",
        ),
        (
            _QC_FIRST_PLAN_PATH,
            _QC_FIRST_PLAN_ARTIFACT_SHA256,
            "QC-first plan ancestor",
        ),
        (
            _FOUR_FAMILY_MULTIPLICITY_PATH,
            _FOUR_FAMILY_MULTIPLICITY_ARTIFACT_SHA256,
            "four-family multiplicity ancestor",
        ),
    )
    authenticated_ancestors: list[tuple[Path, bytes, str]] = []
    try:
        for path, digest, name in ancestor_specs:
            ancestor_path, ancestor_payload = read_stable_regular(
                path,
                name=name,
                maximum_bytes=INFRASTRUCTURE_LOOK_LEDGER_MAX_BYTES,
            )
            if hashlib.sha256(ancestor_payload).hexdigest() != digest:
                raise PreregistrationError(
                    "infrastructure-look ledger frozen ancestor changed"
                )
            authenticated_ancestors.append((ancestor_path, ancestor_payload, name))
        _require_zero_access_authority()
        for ancestor_path, ancestor_payload, name in authenticated_ancestors:
            revalidate_regular(
                ancestor_path,
                ancestor_payload,
                name=name,
                maximum_bytes=INFRASTRUCTURE_LOOK_LEDGER_MAX_BYTES,
            )
        revalidate_regular(
            resolved,
            payload,
            name="infrastructure-look ledger",
            maximum_bytes=INFRASTRUCTURE_LOOK_LEDGER_MAX_BYTES,
        )
    except ArtifactIOError as exc:
        raise PreregistrationError(
            "infrastructure-look ledger or frozen ancestor changed"
        ) from exc
    return InfrastructureLookLedgerBinding(
        path=resolved,
        payload=payload,
        ledger_id=str(expected["ledger_id"]),
        ledger_hash=str(expected["ledger_hash"]),
        artifact_sha256=artifact_sha256,
    )


def require_infrastructure_look_ledger(
    binding: InfrastructureLookLedgerBinding,
) -> InfrastructureLookLedgerBinding:
    if type(binding) is not InfrastructureLookLedgerBinding:
        raise PreregistrationError("infrastructure-look ledger binding changed")
    loaded = load_infrastructure_look_ledger()
    if loaded != binding:
        raise PreregistrationError("infrastructure-look ledger binding changed")
    return binding


@dataclasses.dataclass(frozen=True)
class PreregistrationCell:
    cell_id: str
    value: object
    source: str


@dataclasses.dataclass(frozen=True)
class RegisteredLook:
    look_id: str
    family_id: str
    state: str
    validation_start: str
    validation_end: str
    dataset_id: str
    code_identity: str
    cost_cell_hash: str
    topology_id: str


@dataclasses.dataclass(frozen=True, init=False)
class ReviewedPreregistration:
    spec_id: str
    spec_hash: str
    producing_commit: str
    reviewed_by: str
    reviewed_at: str
    cells: tuple[PreregistrationCell, ...]
    looks: tuple[RegisteredLook, ...]
    source_path: str
    artifact_sha256: str
    review_commit: str
    _authority: object = dataclasses.field(repr=False, compare=False)

    def cell(self, cell_id: str) -> object:
        for cell in self.cells:
            if cell.cell_id == cell_id:
                return cell.value
        raise PreregistrationError(f"required preregistration cell is absent: {cell_id}")


def _authority_value(value: object) -> object:
    if type(value) is MappingProxyType:
        pairs: list[tuple[str, object]] = []
        for key, item in value.items():
            if type(key) is not str:
                raise PreregistrationError(
                    "review authority contains a noncanonical mapping key"
                )
            pairs.append((key, _authority_value(item)))
        return ("mapping", tuple(sorted(pairs)))
    if type(value) is tuple:
        return ("tuple", tuple(_authority_value(item) for item in value))
    if type(value) is str:
        return ("str", value)
    if type(value) is bool:
        return ("bool", value)
    if type(value) is int:
        return ("int", value)
    if value is None:
        return ("none", None)
    raise PreregistrationError("review authority contains noncanonical state")


def _reviewed_fingerprint(
    spec: ReviewedPreregistration,
) -> tuple[object, ...]:
    scalar_values = (
        spec.spec_id,
        spec.spec_hash,
        spec.producing_commit,
        spec.reviewed_by,
        spec.reviewed_at,
        spec.source_path,
        spec.artifact_sha256,
        spec.review_commit,
    )
    if any(type(item) is not str for item in scalar_values) or any(
        type(cell.cell_id) is not str or type(cell.source) is not str
        for cell in spec.cells
    ) or any(
        any(
            type(getattr(look, name)) is not str
            for name in (
                "look_id",
                "family_id",
                "state",
                "validation_start",
                "validation_end",
                "dataset_id",
                "code_identity",
                "cost_cell_hash",
                "topology_id",
            )
        )
        for look in spec.looks
    ):
        raise PreregistrationError("review authority contains noncanonical state")
    return (
        *(_authority_value(item) for item in scalar_values[:5]),
        (
            "cells",
            tuple(
                (
                    _authority_value(cell.cell_id),
                    _authority_value(cell.value),
                    _authority_value(cell.source),
                )
                for cell in spec.cells
            ),
        ),
        (
            "looks",
            tuple(
                (
                    _authority_value(look.look_id),
                    _authority_value(look.family_id),
                    _authority_value(look.state),
                    _authority_value(look.validation_start),
                    _authority_value(look.validation_end),
                    _authority_value(look.dataset_id),
                    _authority_value(look.code_identity),
                    _authority_value(look.cost_cell_hash),
                    _authority_value(look.topology_id),
                )
                for look in spec.looks
            ),
        ),
        *(_authority_value(item) for item in scalar_values[5:]),
    )


def _forget_reviewed_authority(
    identity: int,
    reference: weakref.ReferenceType[ReviewedPreregistration],
) -> None:
    with _REVIEWED_AUTHORITIES_LOCK:
        current = _REVIEWED_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _REVIEWED_AUTHORITIES.pop(identity, None)


def _reviewed_preregistration(
    *,
    spec_id: str,
    spec_hash: str,
    producing_commit: str,
    reviewed_by: str,
    reviewed_at: str,
    cells: tuple[PreregistrationCell, ...],
    looks: tuple[RegisteredLook, ...],
    source_path: str,
    artifact_sha256: str,
    review_commit: str,
    infrastructure_look_ledger: InfrastructureLookLedgerBinding,
) -> ReviewedPreregistration:
    require_infrastructure_look_ledger(infrastructure_look_ledger)
    value = object.__new__(ReviewedPreregistration)
    fields = {
        "spec_id": spec_id,
        "spec_hash": spec_hash,
        "producing_commit": producing_commit,
        "reviewed_by": reviewed_by,
        "reviewed_at": reviewed_at,
        "cells": cells,
        "looks": looks,
        "source_path": source_path,
        "artifact_sha256": artifact_sha256,
        "review_commit": review_commit,
        "_authority": _REVIEWED_AUTHORITY,
    }
    for name, item in fields.items():
        object.__setattr__(value, name, item)
    fingerprint = _reviewed_fingerprint(value)
    frozen_container_authority = capture_frozen_container_authority(
        (
            fields["cells"],
            fields["looks"],
            tuple(cell.value for cell in cells),
        )
    )
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity: _forget_reviewed_authority(key, ref)
    )
    with _REVIEWED_AUTHORITIES_LOCK:
        _REVIEWED_AUTHORITIES[identity] = (
            reference,
            Path(source_path),
            fingerprint,
            frozen_container_authority,
            infrastructure_look_ledger,
        )
    return value


@dataclasses.dataclass(frozen=True)
class DraftPreregistration:
    status: str
    spec_id: str
    spec_hash: str
    unresolved_owner_decisions: tuple[str, ...]
    pending_external_bindings: tuple[str, ...]
    planned_look_ids: tuple[str, ...]


def _parse_root(path: Path) -> dict[str, object]:
    try:
        raw_bytes = path.read_bytes()
        raw = json.loads(raw_bytes, object_pairs_hook=_reject_duplicate_keys)
    except (OSError, json.JSONDecodeError) as exc:
        raise PreregistrationError("preregistration is unreadable") from exc
    if not isinstance(raw, dict) or set(raw) != _TOP_KEYS:
        raise PreregistrationError("preregistration has missing or unknown root fields")
    if raw["schema"] != "arv2-round0-preregistration-v1":
        raise PreregistrationError("preregistration schema is unsupported")
    _strict_json(raw)
    return raw


def _refuse_superseded_look_id(raw: Mapping[str, object]) -> None:
    looks = raw.get("looks")
    if not isinstance(looks, list):
        return
    for item in looks:
        if isinstance(item, dict) and item.get("look_id") in SUPERSEDED_LOOK_IDS:
            raise PreregistrationError(
                "look identity was superseded unspent and cannot be revived"
            )


def _git(root: Path, *arguments: str, binary: bool = False) -> str | bytes:
    try:
        if binary:
            return read_git_bytes(root, arguments)
        return read_git_text(root, arguments)
    except (DatasetVerificationError, OSError, UnicodeError) as exc:
        raise PreregistrationError("review anchor Git verification could not run") from exc


def _json_object(payload: bytes, name: str) -> dict[str, object]:
    try:
        value = json.loads(payload, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PreregistrationError(f"{name} is not strict JSON") from exc
    if not isinstance(value, dict):
        raise PreregistrationError(f"{name} must be a JSON object")
    _strict_json(value, name)
    return value


def _review_anchor(
    spec_path: Path,
    raw: Mapping[str, object],
) -> tuple[str, str, str]:
    """Bind a reviewed spec to the committed counter-review registry.

    The registry entry is added only after the independent review commit has
    put the exact reviewed spec bytes into Git. This prevents a self-hashed
    caller-created JSON file from granting outcome authority.
    """
    try:
        registry_path = REVIEWED_SPEC_REGISTRY_PATH.resolve(strict=True)
        resolved_spec = spec_path.resolve(strict=True)
    except OSError as exc:
        raise PreregistrationError("reviewed spec or review registry is absent") from exc
    registry_root_text = str(
        _git(registry_path.parent, "rev-parse", "--show-toplevel")
    ).strip()
    spec_root_text = str(_git(resolved_spec.parent, "rev-parse", "--show-toplevel")).strip()
    registry_root = Path(registry_root_text).resolve(strict=True)
    spec_root = Path(spec_root_text).resolve(strict=True)
    if registry_root != spec_root:
        raise PreregistrationError("reviewed spec and review registry are not in one repository")
    try:
        spec_relative = resolved_spec.relative_to(spec_root).as_posix()
        registry_relative = registry_path.relative_to(spec_root).as_posix()
    except ValueError as exc:
        raise PreregistrationError("review anchor escaped its Git repository") from exc

    status = str(
        _git(
            spec_root,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            spec_relative,
            registry_relative,
        )
    )
    if status:
        raise PreregistrationError("reviewed spec and review registry must be committed and clean")
    _git(spec_root, "ls-files", "--error-unmatch", "--", spec_relative)
    _git(spec_root, "ls-files", "--error-unmatch", "--", registry_relative)

    registry = _json_object(registry_path.read_bytes(), "review registry")
    if set(registry) != _REGISTRY_KEYS or registry["schema"] != REVIEW_REGISTRY_SCHEMA:
        raise PreregistrationError("review registry schema or root fields are invalid")
    entries = registry["entries"]
    if not isinstance(entries, list):
        raise PreregistrationError("review registry entries must be a list")
    canonical_registry = _canonical_json(registry)
    committed_registry = _json_object(
        bytes(_git(spec_root, "show", f"HEAD:{registry_relative}", binary=True)),
        "committed review registry",
    )
    if canonical_registry != _canonical_json(committed_registry):
        raise PreregistrationError("working review registry differs from committed registry")

    spec_id = raw.get("spec_id")
    matches: list[dict[str, object]] = []
    seen_ids: set[object] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != _REGISTRY_ENTRY_KEYS:
            raise PreregistrationError("review registry entry fields are invalid")
        if entry["spec_id"] in seen_ids:
            raise PreregistrationError("review registry contains duplicate spec_id")
        seen_ids.add(entry["spec_id"])
        if entry["spec_id"] == spec_id:
            matches.append(entry)
    if len(matches) != 1:
        raise PreregistrationError("reviewed spec has no unique external review anchor")
    anchor = matches[0]
    spec_hash = _sha256(anchor["spec_hash"], "anchored spec_hash")
    artifact_hash = _sha256(anchor["artifact_sha256"], "anchored artifact_sha256")
    review_commit = _sha256(anchor["review_commit"], "review_commit", 40)
    _text(anchor["reviewed_by"], "anchored reviewed_by")
    _aware_instant(anchor["reviewed_at"], "anchored reviewed_at")
    if (
        anchor["spec_path"] != spec_relative
        or spec_hash != raw.get("spec_hash")
        or anchor["reviewed_by"] != raw.get("reviewed_by")
        or anchor["reviewed_at"] != raw.get("reviewed_at")
    ):
        raise PreregistrationError("review anchor does not match the reviewed spec")
    canonical_spec = _canonical_json(raw)
    if artifact_hash != hashlib.sha256(canonical_spec).hexdigest():
        raise PreregistrationError("review anchor does not bind the complete spec artifact")
    _git(spec_root, "cat-file", "-e", f"{review_commit}^{{commit}}")
    try:
        review_is_ancestor = git_commit_is_ancestor(spec_root, review_commit, "HEAD")
    except DatasetVerificationError as exc:
        raise PreregistrationError("independent review ancestry cannot be verified") from exc
    if not review_is_ancestor:
        raise PreregistrationError("independent review commit is not an ancestor of HEAD")
    producing_commit = _sha256(
        raw.get("producing_commit"), "anchored producing_commit", 40
    )
    _git(spec_root, "cat-file", "-e", f"{producing_commit}^{{commit}}")
    try:
        producing_was_reviewed = git_commit_is_ancestor(
            spec_root, producing_commit, review_commit
        )
    except DatasetVerificationError as exc:
        raise PreregistrationError("producing commit ancestry cannot be verified") from exc
    if not producing_was_reviewed:
        raise PreregistrationError(
            "producing commit is not contained in the independent review commit"
        )
    reviewed_blob = _json_object(
        bytes(_git(spec_root, "show", f"{review_commit}:{spec_relative}", binary=True)),
        "reviewed spec blob",
    )
    if _canonical_json(reviewed_blob) != canonical_spec:
        raise PreregistrationError("current spec differs from the independently reviewed blob")
    return str(resolved_spec), artifact_hash, review_commit


def _assert_review_authority(spec: ReviewedPreregistration) -> None:
    if (
        type(spec) is not ReviewedPreregistration
        or getattr(spec, "_authority", None) is not _REVIEWED_AUTHORITY
    ):
        raise PreregistrationError("outcome access requires loader-authenticated review authority")
    with _REVIEWED_AUTHORITIES_LOCK:
        authority = _REVIEWED_AUTHORITIES.get(id(spec))
    if authority is None or authority[0]() is not spec:
        raise PreregistrationError(
            "review authority is not registered to this loader-created object"
        )
    (
        _,
        original_path,
        expected_fingerprint,
        frozen_container_authority,
        infrastructure_look_ledger,
    ) = authority
    require_infrastructure_look_ledger(infrastructure_look_ledger)
    cells_root, looks_root, cell_value_roots = frozen_container_authority[0]
    if (
        getattr(spec, "cells", _MISSING_REVIEWED_ROOT) is not cells_root
        or getattr(spec, "looks", _MISSING_REVIEWED_ROOT) is not looks_root
    ):
        raise PreregistrationError(
            "review authority composite root changed after spec verification"
        )
    if any(type(cell) is not PreregistrationCell for cell in cells_root) or any(
        type(look) is not RegisteredLook for look in looks_root
    ):
        raise PreregistrationError(
            "review authority nested record changed type after spec verification"
        )
    if any(
        getattr(cell, "value", _MISSING_REVIEWED_ROOT) is not expected
        for cell, expected in zip(cells_root, cell_value_roots, strict=True)
    ):
        raise PreregistrationError(
            "review authority cell value root changed after spec verification"
        )
    if not frozen_container_authority_is_current(
        (cells_root, looks_root, cell_value_roots),
        frozen_container_authority,
    ):
        raise PreregistrationError(
            "review authority composite root or descendant container changed "
            "after spec verification"
        )
    try:
        current_fingerprint = _reviewed_fingerprint(spec)
    except AttributeError as exc:
        raise PreregistrationError(
            "review authority changed after spec verification"
        ) from exc
    if current_fingerprint != expected_fingerprint:
        raise PreregistrationError("review authority changed after spec verification")
    reloaded = load_reviewed_preregistration(original_path)
    if _reviewed_fingerprint(reloaded) != expected_fingerprint:
        raise PreregistrationError(
            "reviewed spec bytes, semantics, review anchor, or look bindings changed"
        )


def require_reviewed_preregistration(
    value: object,
) -> ReviewedPreregistration:
    """Return only currently reauthenticated, independently reviewed authority."""
    if type(value) is not ReviewedPreregistration:
        raise PreregistrationError(
            "review authority requires a ReviewedPreregistration"
        )
    _assert_review_authority(value)
    return value


def load_draft_preregistration(path: Path) -> DraftPreregistration:
    raw = _parse_root(path)
    if raw["status"] != OWNER_DECISION_CANDIDATE_STATUS:
        raise PreregistrationError("artifact is not the owner-decision candidate")
    spec_hash = _sha256(raw["spec_hash"], "spec_hash")
    if spec_hash != hashlib.sha256(_canonical_payload(raw)).hexdigest():
        raise PreregistrationError("owner-decision candidate content hash mismatch")
    if raw["spec_id"] != f"arv2-round0-candidate-{spec_hash[:16]}":
        raise PreregistrationError("candidate spec_id is not content-derived")
    _refuse_superseded_look_id(raw)
    if any(
        raw[field] is not None
        for field in ("producing_commit", "reviewed_by", "reviewed_at")
    ):
        raise PreregistrationError(
            "unreviewed candidate cannot claim production or review authority"
        )
    cells = raw["cells"]
    if not isinstance(cells, list) or len(cells) != len(REQUIRED_CELL_IDS):
        raise PreregistrationError("candidate must inventory every required cell")
    values: dict[str, object] = {}
    for expected, cell in zip(REQUIRED_CELL_IDS, cells, strict=True):
        if not isinstance(cell, dict) or set(cell) != _CELL_KEYS or cell["cell_id"] != expected:
            raise PreregistrationError(
                "candidate cells must have exact fields and canonical order"
            )
        expected_state = (
            "frozen_policy_external_binding_required"
            if expected in _PENDING_SOURCE_CELL_IDS
            else "frozen"
        )
        if cell["state"] != expected_state or cell["value"] is None:
            raise PreregistrationError(
                "every owner decision must be populated and frozen; only exact "
                "external source bindings may remain pending"
            )
        _text(cell["source"], f"{expected} source")
        values[expected] = cell["value"]
    _validate_semantics(values, allow_unbound_external_sources=True)

    validation = values["lane_validation_period"]
    multiplicity = values["multiplicity_family"]
    raw_looks = raw["looks"]
    if not isinstance(raw_looks, list) or not raw_looks:
        raise PreregistrationError("candidate must freeze at least one planned look")
    planned_look_ids: list[str] = []
    for item in raw_looks:
        if not isinstance(item, dict) or set(item) != _LOOK_KEYS:
            raise PreregistrationError("planned look has missing or unknown fields")
        look_id = item["look_id"]
        if (
            not isinstance(look_id, str)
            or not look_id.startswith("arv2-look-")
            or look_id in planned_look_ids
        ):
            raise PreregistrationError("planned look_id is invalid or duplicated")
        if look_id in SUPERSEDED_LOOK_IDS:
            raise PreregistrationError(
                "planned look identity was superseded unspent and cannot be revived"
            )
        planned_look_ids.append(look_id)
        if (
            item["state"] != "planned_unbound"
            or item["dataset_id"] is not None
            or item["code_identity"] is not None
        ):
            raise PreregistrationError(
                "candidate looks must remain explicitly unbound and non-executable"
            )
        if (
            item["validation_start"] != validation["start"]
            or item["validation_end"] != validation["end"]
        ):
            raise PreregistrationError(
                "planned look period differs from the frozen validation period"
            )
        if (
            item["family_id"] != multiplicity["family_id"]
            or item["topology_id"] != "stock_primary"
        ):
            raise PreregistrationError("planned look changed family or topology")
        _sha256(item["cost_cell_hash"], "planned look cost_cell_hash")
        if item["cost_cell_hash"] != _cell_sha256(values["cost_contract"]):
            raise PreregistrationError("planned look does not bind the frozen cost cell")
    if tuple(multiplicity["permanent_look_ids"]) != tuple(planned_look_ids):
        raise PreregistrationError(
            "multiplicity family does not cover every planned look"
        )
    pending = (
        "corporate_action_contract.source_id",
        "corporate_action_contract.source_sha256",
        "universe_contract.security_master_id",
        "universe_contract.security_master_sha256",
        f"looks.{planned_look_ids[0]}.dataset_id",
        f"looks.{planned_look_ids[0]}.code_identity",
        "independent_review_anchor",
        "external_permanent_look_authority",
    )
    return DraftPreregistration(
        status=str(raw["status"]),
        spec_id=str(raw["spec_id"]),
        spec_hash=spec_hash,
        unresolved_owner_decisions=(),
        pending_external_bindings=pending,
        planned_look_ids=tuple(planned_look_ids),
    )


def _require_mapping(value: object, name: str, keys: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise PreregistrationError(f"{name} must have exact keys {sorted(keys)}")
    return value


def _string_list(value: object, name: str, *, nonempty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or (nonempty and not value):
        raise PreregistrationError(f"{name} must be a{' non-empty' if nonempty else ''} list")
    materialized = tuple(_text(item, f"{name} item") for item in value)
    if len(materialized) != len(set(materialized)):
        raise PreregistrationError(f"{name} must not contain duplicates")
    return materialized


def _validate_semantics(
    cells: Mapping[str, object],
    *,
    allow_unbound_external_sources: bool = False,
) -> None:
    holdout = _require_mapping(
        cells["shared_holdout"],
        "shared_holdout",
        {"cutoff_session", "reserved_start", "reserved_end", "lane_access_prohibited"},
    )
    cutoff = _session(holdout["cutoff_session"], "shared holdout cutoff")
    reserved_start = _session(holdout["reserved_start"], "shared holdout start")
    reserved_end = _session(holdout["reserved_end"], "shared holdout end")
    if holdout["lane_access_prohibited"] is not True or not cutoff < reserved_start <= reserved_end:
        raise PreregistrationError("shared final holdout is not genuinely reserved")
    contaminated = cells["contaminated_legacy_periods"]
    if not isinstance(contaminated, list) or not contaminated:
        raise PreregistrationError("contaminated legacy periods must be exhaustively classified")
    contaminated_ranges: list[tuple[date, date]] = []
    for index, period in enumerate(contaminated):
        record = _require_mapping(
            period,
            f"contaminated_legacy_periods[{index}]",
            _CONTAMINATED_PERIOD_KEYS,
        )
        start = _date(record["start"], "contaminated period start")
        end = _date(record["end"], "contaminated period end")
        if start > end:
            raise PreregistrationError("contaminated period is reversed")
        if record["disposition"] not in {"discovery_only", "prohibited"}:
            raise PreregistrationError("contaminated period disposition is invalid")
        _text(record["reason"], "contaminated period reason")
        contaminated_ranges.append((start, end))
    ordered_ranges = sorted(contaminated_ranges)
    if any(current[0] <= prior[1] for prior, current in zip(ordered_ranges, ordered_ranges[1:])):
        raise PreregistrationError("contaminated legacy periods overlap")
    if cells["canonical_family"] != "rating_only":
        raise PreregistrationError("first canonical family must be rating_only")
    if cells["channel_family_policy"] != {
        "price_target": "separate_future_family",
        "eps_revision": "separate_future_family",
        "news": "separate_future_family",
    }:
        raise PreregistrationError("non-rating channels must remain separate future families")
    availability = _require_mapping(
        cells["availability_rule"],
        "availability_rule",
        {"exact_clock", "date_only", "ambiguous_clock"},
    )
    if availability != {
        "exact_clock": "first_exchange_open_strictly_after_public_instant",
        "date_only": "second_exchange_session_open_strictly_after_event_date",
        "ambiguous_clock": "refuse",
    }:
        raise PreregistrationError("availability rule is not the conservative V2 contract")
    label = _require_mapping(
        cells["label_contract"],
        "label_contract",
        {"horizon_sessions", "entry", "exit", "missing_exit"},
    )
    horizon = label["horizon_sessions"]
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
        raise PreregistrationError("label horizon must be a positive exchange-session count")
    if label["entry"] != "eligible_session_open" or label["exit"] != "h_session_open":
        raise PreregistrationError("labels must use eligible-open to h-session-open")
    if label["missing_exit"] != "terminal_return_or_named_refusal_never_drop":
        raise PreregistrationError("missing exits cannot be silently dropped")
    corporate = _require_mapping(
        cells["corporate_action_contract"],
        "corporate_action_contract",
        _CORPORATE_ACTION_KEYS,
    )
    if allow_unbound_external_sources:
        if corporate["source_id"] is not None or corporate["source_sha256"] is not None:
            raise PreregistrationError(
                "candidate corporate-action source must remain explicitly unbound"
            )
    else:
        _text(corporate["source_id"], "corporate action source_id")
        _sha256(corporate["source_sha256"], "corporate action source_sha256")
    if corporate != {
        "source_id": corporate["source_id"],
        "source_sha256": corporate["source_sha256"],
        "point_in_time": True,
        "split_policy": "effective_session_point_in_time",
        "cash_dividend_policy": "ex_date_point_in_time_total_return",
        "delisting_policy": "terminal_return_required",
        "missing_terminal_return": "named_refusal_never_drop",
    }:
        raise PreregistrationError("corporate-action and terminal-return rules are unsafe")
    walk = _require_mapping(
        cells["walk_forward_contract"],
        "walk_forward_contract",
        {"train_years", "validation_years", "test_years", "purge_group", "embargo_sessions"},
    )
    if (walk["train_years"], walk["validation_years"], walk["test_years"]) != (5, 2, 1):
        raise PreregistrationError("walk-forward windows must remain 5y/2y/1y")
    if walk["purge_group"] != "decision_date_and_common_event":
        raise PreregistrationError("splits must purge decision date and common event")
    embargo = walk["embargo_sessions"]
    if isinstance(embargo, bool) or not isinstance(embargo, int) or embargo < horizon:
        raise PreregistrationError("embargo must be at least the outcome horizon")
    inference = _require_mapping(
        cells["inference_contract"],
        "inference_contract",
        {"sample_unit", "cluster", "block_length_sessions", "minimum_independent_dates"},
    )
    block = inference["block_length_sessions"]
    minimum_dates = inference["minimum_independent_dates"]
    if inference["sample_unit"] != "decision_date" or inference["cluster"] != "common_event":
        raise PreregistrationError("independent unit and common-event clustering are required")
    if isinstance(block, bool) or not isinstance(block, int) or block < horizon:
        raise PreregistrationError("bootstrap block must cover the outcome horizon")
    if isinstance(minimum_dates, bool) or not isinstance(minimum_dates, int) or minimum_dates < 50:
        raise PreregistrationError("minimum independent dates must be at least 50")
    controls = cells["mandatory_controls"]
    if not isinstance(controls, list) or tuple(controls) != MANDATORY_CONTROLS:
        raise PreregistrationError("mandatory controls are omitted or reordered")
    if cells["missing_control_policy"] != "refuse_row_before_cross_section":
        raise PreregistrationError("missing controls must refuse before the cross-section")
    universe = _require_mapping(
        cells["universe_contract"], "universe_contract", _UNIVERSE_KEYS
    )
    if allow_unbound_external_sources:
        if (
            universe["security_master_id"] is not None
            or universe["security_master_sha256"] is not None
        ):
            raise PreregistrationError(
                "candidate security-master source must remain explicitly unbound"
            )
    else:
        _text(universe["security_master_id"], "security master id")
        _sha256(universe["security_master_sha256"], "security master sha256")
    venues = _string_list(universe["listing_venues"], "listing venues")
    instruments = _string_list(universe["instrument_types"], "instrument types")
    exclusions = _string_list(
        universe["excluded_instrument_types"], "excluded instrument types"
    )
    if (
        universe["point_in_time"] is not True
        or universe["include_delisted"] is not True
        or universe["current_ticker_joins"] is not False
        or universe["unknown_identity"] != "refuse"
        or universe["issuer_incorporation"] != "united_states"
        or venues != ("XASE", "XNAS", "XNYS")
        or instruments != ("common_stock",)
        or exclusions
        != (
            "adr",
            "bdc",
            "closed_end_fund",
            "etf",
            "foreign_ordinary",
            "limited_partnership",
            "preferred_stock",
            "reit",
            "right",
            "trust",
            "unit",
            "warrant",
        )
        or universe["share_class_policy"]
        != "separate_security_with_point_in_time_issuer_link"
    ):
        raise PreregistrationError("universe is not point-in-time and survivorship-safe")
    normalization = _require_mapping(
        cells["normalization_contract"],
        "normalization_contract",
        _NORMALIZATION_KEYS,
    )
    if normalization != {
        "population": "eligible_point_in_time_cross_section",
        "method": "sector_median_mad",
        "peer_hierarchy": ["sector", "refuse"],
        "minimum_total_names": 20,
        "minimum_active_names": 5,
        "structural_zero": "valid_no_event_only",
        "clipping": "frozen_cell_specific",
        "residualization": "mandatory_controls_cross_sectional",
        "degenerate_group": "named_refusal",
    }:
        raise PreregistrationError("normalization contract is incomplete or fail-open")
    topology = _require_mapping(
        cells["stock_topology"], "stock_topology", _STOCK_TOPOLOGY_KEYS
    )
    if topology["topology_id"] != "stock_primary":
        raise PreregistrationError("first topology must remain stock_primary")
    primary_cell_id = _text(topology["primary_cell_id"], "primary stock cell id")
    raw_stock_cells = topology["cells"]
    if (
        primary_cell_id != "arv2-stock-primary-20d"
        or not isinstance(raw_stock_cells, list)
        or len(raw_stock_cells) != 1
    ):
        raise PreregistrationError(
            "stock topology must contain only the frozen primary 20-day cell"
        )
    stock_cell_ids: list[str] = []
    for index, raw_cell in enumerate(raw_stock_cells):
        cell = _require_mapping(
            raw_cell, f"stock_topology.cells[{index}]", _STOCK_CELL_KEYS
        )
        cell_id = _text(cell["cell_id"], "stock cell id")
        if cell_id in stock_cell_ids:
            raise PreregistrationError("stock topology cell IDs are duplicated")
        stock_cell_ids.append(cell_id)
        if (
            cell["signal"] != "rating_change"
            or cell["sign"] != "upgrade_positive_downgrade_negative"
            or cell["residualization"] != "mandatory_controls_cross_sectional"
        ):
            raise PreregistrationError("stock topology changed the rating-only primary family")
        if _positive_int(
            cell["half_life_sessions"], "stock half-life sessions"
        ) != 20:
            raise PreregistrationError("stock half-life must remain 20 sessions")
        if _decimal_text(
            cell["threshold"], "stock threshold", minimum=Decimal("0")
        ) != Decimal("0"):
            raise PreregistrationError("stock threshold must remain zero")
        if _decimal_text(
            cell["clip"], "stock clip", strictly_positive=True
        ) != Decimal("4"):
            raise PreregistrationError("stock clip must remain four")
    if primary_cell_id not in stock_cell_ids:
        raise PreregistrationError("primary stock cell is absent from the frozen topology")
    if cells["topology_comparison_hierarchy"] != ["stock", "industry", "etf"]:
        raise PreregistrationError("stock must precede industry and ETF topology")
    if (
        cells["observation_rule_parity"]
        != "identical_timing_universe_missingness_and_cost_rules_for_signal_and_baselines"
    ):
        raise PreregistrationError("signal and baseline observation rules are not identical")
    costs = _require_mapping(
        cells["cost_contract"], "cost_contract", {"scenario_bps", "units", "missing_adv"}
    )
    if costs != {
        "scenario_bps": ["0", "5", "10", "20"],
        "units": "dollars_then_divide_once_by_nav",
        "missing_adv": "refuse_except_forced_terminal_exit",
    }:
        raise PreregistrationError("cost scenarios or units changed")
    holdings = _require_mapping(
        cells["holdings_contract"],
        "holdings_contract",
        {"minimum_mapped_candidate_weight", "point_in_time", "stale_or_incomplete"},
    )
    if holdings != {
        "minimum_mapped_candidate_weight": "0.99",
        "point_in_time": True,
        "stale_or_incomplete": "refuse",
    }:
        raise PreregistrationError("holdings contract is not fail-closed")
    portfolio = _require_mapping(
        cells["portfolio_contract"],
        "portfolio_contract",
        {"maximum_holdings", "etf_cap", "sector_cap", "cluster_cap", "leverage"},
    )
    if portfolio != {
        "maximum_holdings": 5,
        "etf_cap": "0.20",
        "sector_cap": "0.40",
        "cluster_cap": "0.30",
        "leverage": False,
    }:
        raise PreregistrationError("portfolio hard caps changed")
    historical = _require_mapping(
        cells["historical_evaluation_contract"],
        "historical_evaluation_contract",
        _HISTORICAL_EVALUATION_KEYS,
    )
    history_start = _session(
        historical["eligible_history_start"], "eligible history start"
    )
    development_end = _session(
        historical["development_end"], "historical development end"
    )
    if history_start > development_end:
        raise PreregistrationError("historical evaluation period is reversed")
    if historical != {
        "eligible_history_start": historical["eligible_history_start"],
        "development_end": historical["development_end"],
        "history_extension_policy": (
            "earlier_only_after_independent_source_coverage_and_semantics_review"
        ),
        "market_benchmark": "SPY_total_return",
        "regime_signal_timing": "prior_session_close_only",
        "stress_rule": "trailing_252_session_drawdown_lte_-0.20",
        "boom_rule": (
            "trailing_252_session_total_return_gte_0.20_and_not_stress"
        ),
        "ordinary_rule": "neither_boom_nor_stress",
        "formal_selection_policy": "all_periods_walk_forward_only",
        "regime_output_policy": "descriptive_non_rescuing",
        "named_episode_policy": "descriptive_non_rescuing_no_model_selection",
        "named_episodes": historical["named_episodes"],
    }:
        raise PreregistrationError(
            "historical and regime evaluation contract is not the frozen V2 design"
        )
    episodes = historical["named_episodes"]
    if not isinstance(episodes, list) or not episodes:
        raise PreregistrationError("named historical episodes must be explicit")
    episode_ids: list[str] = []
    episode_labels: list[str] = []
    episode_ranges: list[tuple[date, date]] = []
    for index, episode in enumerate(episodes):
        item = _require_mapping(
            episode,
            f"historical_evaluation_contract.named_episodes[{index}]",
            _NAMED_EPISODE_KEYS,
        )
        episode_id = _text(item["episode_id"], "named episode id")
        if episode_id in episode_ids:
            raise PreregistrationError("named episode IDs are duplicated")
        episode_ids.append(episode_id)
        episode_start = _session(item["start"], "named episode start")
        episode_end = _session(item["end"], "named episode end")
        episode_labels.append(_text(item["label"], "named episode label"))
        if not history_start <= episode_start <= episode_end <= development_end:
            raise PreregistrationError("named episode is outside eligible history")
        episode_ranges.append((episode_start, episode_end))
    ordered_episodes = sorted(episode_ranges)
    if any(
        current[0] <= prior[1]
        for prior, current in zip(ordered_episodes, ordered_episodes[1:])
    ):
        raise PreregistrationError("named historical episodes overlap")
    if not {"boom", "stress"}.issubset(episode_labels):
        raise PreregistrationError(
            "named historical episodes must include boom and stress diagnostics"
        )
    validation = _require_mapping(
        cells["lane_validation_period"],
        "lane_validation_period",
        {"start", "end", "one_shot"},
    )
    validation_start = _session(validation["start"], "lane validation start")
    validation_end = _session(validation["end"], "lane validation end")
    if (validation["start"], validation["end"]) in SUPERSEDED_VALIDATION_PERIODS:
        raise PreregistrationError(
            "lane validation period was superseded unspent by the owner QC-first "
            "sequence and cannot be backfilled or reviewed"
        )
    if validation["one_shot"] is not True or not validation_start <= validation_end <= cutoff:
        raise PreregistrationError("lane validation is not one-shot and holdout-excluded")
    if development_end >= validation_start:
        raise PreregistrationError(
            "historical development must end before prospective validation starts"
        )
    if any(
        validation_start <= contaminated_end and contaminated_start <= validation_end
        for contaminated_start, contaminated_end in contaminated_ranges
    ):
        raise PreregistrationError("lane validation overlaps contaminated discovery history")
    multiplicity = _require_mapping(
        cells["multiplicity_family"], "multiplicity_family", _MULTIPLICITY_KEYS
    )
    if multiplicity["family_id"] != "arv2-rating-only-v1":
        raise PreregistrationError("multiplicity family ID changed")
    alpha = _decimal_text(
        multiplicity["alpha"],
        "multiplicity alpha",
        strictly_positive=True,
        maximum=Decimal("1"),
    )
    if multiplicity["correction"] != "bonferroni_all_registered_cells_and_looks":
        raise PreregistrationError("multiplicity correction is not exhaustive")
    permanent_cells = _string_list(
        multiplicity["permanent_cell_ids"], "permanent cell IDs"
    )
    permanent_looks = _string_list(
        multiplicity["permanent_look_ids"], "permanent look IDs"
    )
    if alpha != Decimal("0.05"):
        raise PreregistrationError("multiplicity alpha must remain 0.05")
    if permanent_cells != ("arv2-stock-primary-20d",):
        raise PreregistrationError("multiplicity family does not cover every stock cell")
    if permanent_looks != (PRIMARY_OUTCOME_LOOK_ID,):
        raise PreregistrationError(
            "multiplicity family permanent-look budget must remain one named look"
        )
    if cells["three_lane_selection_correction"] != 3:
        raise PreregistrationError("three-lane selection family must count all three attempts")
    if cells["valid_null_closes_family"] is not True:
        raise PreregistrationError("a valid null must close the canonical family")
    if cells["legacy_reproduction_policy"] != "non_new_non_v2_offline_registered_only":
        raise PreregistrationError("legacy reproductions cannot enter active evidence")


def load_reviewed_preregistration(path: Path) -> ReviewedPreregistration:
    raw = _parse_root(path)
    if raw["status"] != "reviewed_frozen":
        raise PreregistrationError("outcome access requires a reviewed_frozen preregistration")
    spec_hash = _sha256(raw["spec_hash"], "spec_hash")
    actual_hash = hashlib.sha256(_canonical_payload(raw)).hexdigest()
    if spec_hash != actual_hash:
        raise PreregistrationError("preregistration content hash mismatch")
    if raw["spec_id"] != f"arv2-round0-{spec_hash[:16]}":
        raise PreregistrationError("spec_id is not derived from the complete spec hash")
    _refuse_superseded_look_id(raw)
    producing_commit = _sha256(raw["producing_commit"], "producing_commit", 40)
    if not isinstance(raw["reviewed_by"], str) or not raw["reviewed_by"].strip():
        raise PreregistrationError("reviewed_by must name the independent reviewer")
    _aware_instant(raw["reviewed_at"], "reviewed_at")
    raw_cells = raw["cells"]
    if not isinstance(raw_cells, list) or len(raw_cells) != len(REQUIRED_CELL_IDS):
        raise PreregistrationError("reviewed spec must contain every required cell exactly once")
    cells: list[PreregistrationCell] = []
    for expected, cell in zip(REQUIRED_CELL_IDS, raw_cells, strict=True):
        if not isinstance(cell, dict) or set(cell) != _CELL_KEYS:
            raise PreregistrationError("cell has missing or unknown fields")
        if cell["cell_id"] != expected or cell["state"] != "frozen" or cell["value"] is None:
            raise PreregistrationError("every cell must be frozen, populated, and canonically ordered")
        if not isinstance(cell["source"], str) or not cell["source"].strip():
            raise PreregistrationError("every decision must name its source")
        cells.append(
            PreregistrationCell(
                expected,
                _deep_freeze(cell["value"]),
                str(cell["source"]),
            )
        )
    # Semantics are checked against detached ordinary JSON first. The stored
    # authority below receives an independently deep-frozen copy.
    mutable_by_id = {
        str(cell["cell_id"]): cell["value"] for cell in raw_cells
    }
    _validate_semantics(mutable_by_id)
    raw_looks = raw["looks"]
    if not isinstance(raw_looks, list) or not raw_looks:
        raise PreregistrationError("reviewed spec must register at least one permanent look")
    looks: list[RegisteredLook] = []
    seen: set[str] = set()
    validation = mutable_by_id["lane_validation_period"]
    for item in raw_looks:
        if not isinstance(item, dict) or set(item) != _LOOK_KEYS:
            raise PreregistrationError("look registration has missing or unknown fields")
        look_id = item["look_id"]
        if not isinstance(look_id, str) or not look_id.startswith("arv2-look-") or look_id in seen:
            raise PreregistrationError("look_id is invalid or duplicated")
        if look_id in SUPERSEDED_LOOK_IDS:
            raise PreregistrationError(
                "registered look identity was superseded unspent and cannot be revived"
            )
        seen.add(look_id)
        if item["state"] != "registered_unspent":
            raise PreregistrationError("immutable preregistration may contain only unspent looks")
        if item["validation_start"] != validation["start"] or item["validation_end"] != validation["end"]:
            raise PreregistrationError("look period differs from the frozen lane validation period")
        _dataset_id(item["dataset_id"], "look dataset_id")
        _sha256(item["code_identity"], "look code_identity")
        _sha256(item["cost_cell_hash"], "look cost_cell_hash")
        if not isinstance(item["family_id"], str) or item["family_id"] != "arv2-rating-only-v1":
            raise PreregistrationError("look belongs to an unknown family")
        if item["topology_id"] != "stock_primary":
            raise PreregistrationError("first outcome look must be stock-primary")
        if item["cost_cell_hash"] != _cell_sha256(mutable_by_id["cost_contract"]):
            raise PreregistrationError("look cost_cell_hash does not bind the frozen cost cell")
        looks.append(RegisteredLook(**item))
    multiplicity = mutable_by_id["multiplicity_family"]
    if tuple(multiplicity["permanent_look_ids"]) != tuple(look.look_id for look in looks):
        raise PreregistrationError("multiplicity family does not cover every registered look")
    infrastructure_look_ledger = load_infrastructure_look_ledger()
    source_path, artifact_hash, review_commit = _review_anchor(path, raw)
    return _reviewed_preregistration(
        spec_id=str(raw["spec_id"]),
        spec_hash=spec_hash,
        producing_commit=producing_commit,
        reviewed_by=str(raw["reviewed_by"]),
        reviewed_at=str(raw["reviewed_at"]),
        cells=tuple(cells),
        looks=tuple(looks),
        source_path=source_path,
        artifact_sha256=artifact_hash,
        review_commit=review_commit,
        infrastructure_look_ledger=infrastructure_look_ledger,
    )


@dataclasses.dataclass(frozen=True)
class OutcomeAccessRequest:
    look_id: str
    dataset_id: str
    code_identity: str
    requested_start: str
    requested_end: str
    horizon_sessions: int
    embargo_sessions: int
    block_length_sessions: int
    controls: tuple[str, ...]
    topology_id: str
    cost_cell_hash: str


@dataclasses.dataclass(frozen=True, init=False)
class OutcomeAccessPermit:
    spec_id: str
    spec_hash: str
    spec_artifact_sha256: str
    review_commit: str
    look_id: str
    family_id: str
    dataset_id: str
    code_identity: str
    requested_start: str
    requested_end: str
    horizon_sessions: int
    embargo_sessions: int
    block_length_sessions: int
    controls: tuple[str, ...]
    topology_id: str
    cost_cell_hash: str
    request_sha256: str
    holdout_exclusion_proved: bool
    permit_id: str
    spent_at: str
    authority_id: str
    authority_receipt_id: str
    _authority: object = dataclasses.field(repr=False, compare=False)


def _request_payload(request: OutcomeAccessRequest) -> dict[str, object]:
    return {
        "look_id": request.look_id,
        "dataset_id": request.dataset_id,
        "code_identity": request.code_identity,
        "requested_start": request.requested_start,
        "requested_end": request.requested_end,
        "horizon_sessions": request.horizon_sessions,
        "embargo_sessions": request.embargo_sessions,
        "block_length_sessions": request.block_length_sessions,
        "controls": list(request.controls),
        "topology_id": request.topology_id,
        "cost_cell_hash": request.cost_cell_hash,
    }


def _request_sha256(request: OutcomeAccessRequest) -> str:
    return hashlib.sha256(
        _canonical_json(
            {"schema": "arv2-outcome-access-request-v1", **_request_payload(request)}
        )
    ).hexdigest()


def _outcome_permit(
    *,
    spec: ReviewedPreregistration,
    request: OutcomeAccessRequest,
    look: RegisteredLook,
    authority_id: str,
    authority_receipt_id: str,
    permit_id: str,
    spent_at: str,
) -> OutcomeAccessPermit:
    validated_look, request_hash = _validate_outcome_request(spec, request)
    if validated_look != look:
        raise PreregistrationError("permit look is not the approved registered look")
    _text(authority_id, "authority_id")
    _text(authority_receipt_id, "authority_receipt_id")
    _text(permit_id, "permit_id")
    _aware_instant(spent_at, "spent_at")
    value = object.__new__(OutcomeAccessPermit)
    for name, item in {
        "spec_id": spec.spec_id,
        "spec_hash": spec.spec_hash,
        "spec_artifact_sha256": spec.artifact_sha256,
        "review_commit": spec.review_commit,
        "look_id": request.look_id,
        "family_id": look.family_id,
        "dataset_id": request.dataset_id,
        "code_identity": request.code_identity,
        "requested_start": request.requested_start,
        "requested_end": request.requested_end,
        "horizon_sessions": request.horizon_sessions,
        "embargo_sessions": request.embargo_sessions,
        "block_length_sessions": request.block_length_sessions,
        "controls": request.controls,
        "topology_id": request.topology_id,
        "cost_cell_hash": request.cost_cell_hash,
        "request_sha256": request_hash,
        "holdout_exclusion_proved": True,
        "permit_id": permit_id,
        "spent_at": spent_at,
        "authority_id": authority_id,
        "authority_receipt_id": authority_receipt_id,
        "_authority": _PERMIT_AUTHORITY,
    }.items():
        object.__setattr__(value, name, item)
    return value


# A deletable or substitutable local database is never permanent-look authority.
# Outcome authorization below is exclusively fail-closed until an independently
# pinned cross-machine append-only authority is configured.
def _validate_outcome_request(
    spec: ReviewedPreregistration,
    request: OutcomeAccessRequest,
) -> tuple[RegisteredLook, str]:
    require_reviewed_preregistration(spec)
    if type(request) is not OutcomeAccessRequest:
        raise PreregistrationError("outcome request must be typed")
    _text(request.look_id, "look_id")
    _dataset_id(request.dataset_id)
    _sha256(request.code_identity, "code_identity")
    _sha256(request.cost_cell_hash, "cost_cell_hash")
    _text(request.topology_id, "topology_id")
    if type(request.controls) is not tuple:
        raise PreregistrationError("outcome controls must be an immutable tuple")
    matches = [look for look in spec.looks if look.look_id == request.look_id]
    if len(matches) != 1:
        raise PreregistrationError("research look is unregistered")
    look = matches[0]
    for name in ("dataset_id", "code_identity", "cost_cell_hash", "topology_id"):
        if getattr(request, name) != getattr(look, name):
            raise PreregistrationError(f"outcome request changed frozen {name}")
    if (
        request.requested_start != look.validation_start
        or request.requested_end != look.validation_end
    ):
        raise PreregistrationError(
            "outcome request changed the one-shot validation period"
        )
    start = _session(request.requested_start, "requested_start")
    end = _session(request.requested_end, "requested_end")
    holdout = spec.cell("shared_holdout")
    if not start <= end < _date(holdout["reserved_start"], "shared holdout start"):
        raise PreregistrationError("outcome request touches the shared final holdout")
    label = spec.cell("label_contract")
    walk = spec.cell("walk_forward_contract")
    inference = spec.cell("inference_contract")
    if request.horizon_sessions != label["horizon_sessions"]:
        raise PreregistrationError("outcome horizon changed")
    if (
        request.embargo_sessions != walk["embargo_sessions"]
        or request.embargo_sessions < request.horizon_sessions
    ):
        raise PreregistrationError("split is unpurged or embargo is too short")
    if (
        request.block_length_sessions != inference["block_length_sessions"]
        or request.block_length_sessions < request.horizon_sessions
    ):
        raise PreregistrationError("bootstrap block is shorter than the horizon")
    if request.controls != MANDATORY_CONTROLS:
        raise PreregistrationError(
            "outcome request omitted or changed a mandatory control"
        )
    return look, _request_sha256(request)


def _require_zero_access_authority() -> str:
    """Authenticate the declaration that no permanent spend authority exists."""
    try:
        path = Path(PERMANENT_LOOK_AUTHORITY_PATH).resolve(strict=True)
    except OSError as exc:
        raise PreregistrationError(
            "permanent-look authority is absent; outcome access remains zero-access"
        ) from exc
    if not path.is_file() or path.is_symlink():
        raise PreregistrationError(
            "permanent-look authority must be a regular zero-access artifact"
        )
    authority = _json_object(path.read_bytes(), "permanent-look authority")
    if set(authority) != {"schema", "authority_mode", "authority_id", "entries"}:
        raise PreregistrationError("permanent-look authority fields are invalid")
    if (
        authority["schema"] != PERMANENT_LOOK_AUTHORITY_SCHEMA
        or authority["authority_mode"] != "zero_access"
        or authority["authority_id"] != ZERO_ACCESS_AUTHORITY_ID
        or authority["entries"] != []
    ):
        raise PreregistrationError(
            "no externally pinned append-only spend authority is configured; "
            "the repository authority must remain zero-access"
        )
    return ZERO_ACCESS_AUTHORITY_ID


def authorize_outcome_access(
    spec: ReviewedPreregistration,
    request: OutcomeAccessRequest,
) -> OutcomeAccessPermit:
    """Refuse the retired v1 authority after validating the requested slice."""
    _validate_outcome_request(spec, request)
    raise PreregistrationError(LEGACY_V1_OUTCOME_AUTHORITY_RETIRED_REASON)


def assert_outcome_access_permit(
    permit: OutcomeAccessPermit,
    request: OutcomeAccessRequest | None = None,
) -> None:
    """Reject permits until an external authority can reauthenticate its receipt."""
    if (
        type(permit) is not OutcomeAccessPermit
        or getattr(permit, "_authority", None) is not _PERMIT_AUTHORITY
        or permit.holdout_exclusion_proved is not True
    ):
        raise PreregistrationError("outcome access permit is forged or malformed")
    if request is None or type(request) is not OutcomeAccessRequest:
        raise PreregistrationError(
            "permit reauthentication requires the exact approved outcome request"
        )
    if permit.request_sha256 != _request_sha256(request):
        raise PreregistrationError(
            "outcome access permit was reused for a different slice"
        )
    for name, expected in _request_payload(request).items():
        actual = getattr(permit, name)
        if name == "controls":
            expected = tuple(expected)
        if actual != expected:
            raise PreregistrationError(
                "outcome access permit does not bind the complete approved request"
            )
    _require_zero_access_authority()
    raise PreregistrationError(
        "outcome access permit cannot be authenticated without an externally "
        "pinned append-only authority"
    )


def run_authorized_outcome_slice(
    *,
    preregistration_path: Path,
    snapshot_root: Path,
    dataset_root: Path,
    repository_root: Path,
    request: OutcomeAccessRequest,
    outcome_loader: Callable[[OutcomeAccessPermit, OutcomeAccessRequest], bytes],
) -> bytes:
    """The only bounded outcome-I/O boundary; currently deliberately zero-access.

    The boundary reauthenticates the committed review, raw snapshot, normalized
    dataset, clean committed code, frozen cost cell and exact requested slice
    before seeking a spend receipt. No truthful cross-machine append-only
    authority is configured, so it fails before ``outcome_loader`` executes.
    """
    if not callable(outcome_loader):
        raise PreregistrationError("outcome_loader must be callable")
    spec = load_reviewed_preregistration(preregistration_path)
    require_reviewed_preregistration(spec)
    snapshot = load_verified_snapshot(snapshot_root)
    revalidate_verified_snapshot(snapshot)
    dataset = load_normalized_dataset(dataset_root, snapshot=snapshot)
    revalidate_normalized_dataset(dataset)
    if request.dataset_id != dataset.manifest.dataset_id:
        raise PreregistrationError(
            "requested dataset is not the authenticated normalized dataset"
        )
    lineage = capture_clean_git_lineage(repository_root)
    actual_code_identity = compute_package_source_sha256(lineage.repository_root)
    if request.code_identity != actual_code_identity:
        raise PreregistrationError(
            "requested code identity is not the clean committed package code"
        )
    _validate_outcome_request(spec, request)
    permit = authorize_outcome_access(spec, request)
    assert_outcome_access_permit(permit, request)
    payload = outcome_loader(permit, request)
    if type(payload) is not bytes:
        raise PreregistrationError("outcome loader must return exact bytes")
    return payload
