"""
Versioned personal trading policy.

This is the deterministic definition of what the assistant is allowed to
propose and execute. The language-model/explanation layer may discuss a
trade, but only this policy plus risk.execution_gate can authorize it.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Literal

from config import MAX_POSITION_PCT, MAX_TOTAL_EXPOSURE_PCT
from assistant.process_singleton import ProcessSingleton, ProcessSingletonError

DEFAULT_POLICY_PATH = Path(__file__).resolve().parent / "default_policy.json"
PERSONAL_POLICY_PATH = Path(__file__).resolve().parent / "my_policy.json"
POLICY_PATH_ENV_VAR = "TRADING_ASSISTANT_POLICY"


class PolicyWriteConflictError(RuntimeError):
    """The policy changed after the caller loaded its editing base."""


def resolve_policy_path(
    explicit: str | Path | None = None, *, use_env: bool = True
) -> Path:
    """Resolve which policy file an *entry point* should load.

    Precedence, highest first:

    1. ``explicit`` -- a ``--policy`` flag, or a path the owner typed into
       the UI;
    2. the ``TRADING_ASSISTANT_POLICY`` environment variable;
    3. ``assistant/my_policy.json``, when that file exists;
    4. ``assistant/default_policy.json``.

    Levels 1 and 2 are the caller *naming* a file, so a missing file raises
    instead of falling back. Silently loading a different policy than the
    one asked for is precisely the hidden-default-that-changes-financial-
    behavior hazard this resolver has to avoid. Only the 3 -> 4 step falls
    back, and it falls toward the committed conservative baseline, never
    toward a more permissive file.

    Scope is deliberately narrow. ``load_policy()`` keeps
    ``DEFAULT_POLICY_PATH`` as its own default: library code and tests must
    not change behavior depending on whether an untracked personal policy
    happens to exist on a particular machine.

    Evidence-epoch note: the resolved file's fingerprint is bound into the
    active epoch lineage, so changing *which* file resolves is detected by
    the runtime-lineage check in the observation path and refused outright
    rather than silently absorbed into the evidence.
    """
    if explicit is not None:
        candidate = Path(explicit).expanduser()
        if not candidate.is_file():
            raise FileNotFoundError(f"Policy file not found: {candidate}")
        return candidate

    # use_env=False lets a caller that has ALREADY reported a broken
    # environment variable continue down the rest of the chain, without
    # mutating os.environ to do it. Process-global state is shared across
    # Streamlit's per-session threads, so a pop/restore in a render path
    # is visible to concurrent reruns; a parameter is not.
    env_value = os.environ.get(POLICY_PATH_ENV_VAR, "").strip() if use_env else ""
    if env_value:
        candidate = Path(env_value).expanduser()
        if not candidate.is_file():
            raise FileNotFoundError(
                f"{POLICY_PATH_ENV_VAR} names a policy file that does not "
                f"exist: {candidate}"
            )
        return candidate

    if PERSONAL_POLICY_PATH.is_file():
        return PERSONAL_POLICY_PATH
    return DEFAULT_POLICY_PATH


@dataclasses.dataclass(frozen=True)
class TradingPolicy:
    version: str
    name: str
    execution_mode: Literal["read_only", "paper"] = "read_only"
    max_position_pct: float = MAX_POSITION_PCT
    max_total_exposure_pct: float = MAX_TOTAL_EXPOSURE_PCT
    max_basket_pct: float = 0.40
    max_leveraged_etf_pct: float = 0.20
    min_cash_reserve_pct: float = 0.10
    max_order_value: float = 5_000.0
    max_daily_submitted_notional: float = 25_000.0
    max_daily_order_count: int = 10
    max_open_orders: int = 5
    max_order_age_minutes: float = 30.0
    max_stale_price_minutes: float = 15.0
    max_slippage_pct: float = 1.0
    max_spread_pct: float = 0.5
    earnings_blackout_days: int = 2
    require_earnings_data: bool = False
    allowed_sides: tuple[str, ...] = ("buy", "sell")
    allowed_order_types: tuple[str, ...] = ("market", "limit")
    allow_new_positions: bool = False
    enable_strategy_proposals: bool = False
    # Owner request 2026-08-14. True keeps this project's long-standing
    # whole-share-only ordering; False permits fractional quantities.
    #
    # This lives in the POLICY, not in UI preferences, because it decides
    # what the system may execute. That makes it part of the fingerprint
    # bound into every evidence epoch, so the record shows which share
    # granularity was in force -- evidence gathered under fractional
    # ordering must never silently pool with evidence gathered without it.
    # Adding the field changes the fingerprint even at its safe default, so
    # DEPLOYING it closes the active epoch; that is correct, not a defect.
    #
    # Default True, and every enforcement point defaults the same way
    # independently, so a call site that forgets to pass it refuses rather
    # than admitting a fractional order.
    whole_shares_only: bool = True
    notes: str = ""

    SUPPORTED_SIDES = ("buy", "sell")
    SUPPORTED_ORDER_TYPES = ("market", "limit")

    def validate(self) -> None:
        if self.execution_mode not in ("read_only", "paper"):
            raise ValueError(
                f"execution_mode must be 'read_only' or 'paper', got {self.execution_mode!r}."
            )
        percentage_fields = (
            "max_position_pct",
            "max_total_exposure_pct",
            "max_basket_pct",
            "max_leveraged_etf_pct",
            "min_cash_reserve_pct",
        )
        for field_name in percentage_fields:
            value = getattr(self, field_name)
            if not (math.isfinite(value) and 0 <= value <= 1):
                raise ValueError(f"{field_name} must be a finite number between 0 and 1, got {value}.")
        if self.max_position_pct > self.max_total_exposure_pct:
            raise ValueError("max_position_pct cannot exceed max_total_exposure_pct.")
        # Every one of these feeds a plain `>`/`<` comparison in
        # risk/execution_gate.py -- a NaN there evaluates False no matter
        # what it's compared against, which would silently disable that
        # cap entirely rather than reject the trade (Codex review,
        # 2026-07-27). json.loads() also accepts a literal `NaN` in a
        # policy file by default, so this is reachable from a malformed
        # config, not just a caller bug.
        if not math.isfinite(self.max_order_value) or self.max_order_value <= 0:
            raise ValueError(f"max_order_value must be a positive, finite number, got {self.max_order_value}.")
        if (
            not math.isfinite(self.max_daily_submitted_notional)
            or self.max_daily_submitted_notional <= 0
        ):
            raise ValueError(
                "max_daily_submitted_notional must be a positive, finite number, "
                f"got {self.max_daily_submitted_notional}."
            )
        for field_name in ("max_daily_order_count", "max_open_orders"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer, got {value!r}.")
        if not math.isfinite(self.max_order_age_minutes) or self.max_order_age_minutes <= 0:
            raise ValueError(
                "max_order_age_minutes must be a positive, finite number, "
                f"got {self.max_order_age_minutes}."
            )
        if not math.isfinite(self.max_stale_price_minutes) or self.max_stale_price_minutes <= 0:
            raise ValueError(
                f"max_stale_price_minutes must be a positive, finite number, got {self.max_stale_price_minutes}."
            )
        if not math.isfinite(self.max_slippage_pct) or self.max_slippage_pct < 0:
            raise ValueError(f"max_slippage_pct must be a non-negative, finite number, got {self.max_slippage_pct}.")
        if not math.isfinite(self.max_spread_pct) or self.max_spread_pct < 0:
            raise ValueError(f"max_spread_pct must be a non-negative, finite number, got {self.max_spread_pct}.")
        # isinstance(x, int), not a `< 0` comparison alone: NaN/inf/1.5 are
        # all `float`, not `int`, so this rejects them along with negative
        # values in one check -- a bare `< 0` comparison silently passed
        # NaN (NaN < 0 is False) and would have disabled the earnings
        # blackout check entirely (Codex review, 2026-07-27). bool is
        # excluded even though it's technically an int subclass, so
        # True/False can't silently pass as 1/0.
        if (
            not isinstance(self.earnings_blackout_days, int)
            or isinstance(self.earnings_blackout_days, bool)
            or self.earnings_blackout_days < 0
        ):
            raise ValueError(
                f"earnings_blackout_days must be a non-negative integer, got {self.earnings_blackout_days!r}."
            )
        if not self.allowed_sides:
            raise ValueError("allowed_sides cannot be empty.")
        unsupported_sides = set(self.allowed_sides) - set(self.SUPPORTED_SIDES)
        if unsupported_sides:
            raise ValueError(f"Unsupported allowed_sides: {sorted(unsupported_sides)}.")
        if not self.allowed_order_types:
            raise ValueError("allowed_order_types cannot be empty.")
        unsupported_order_types = set(self.allowed_order_types) - set(self.SUPPORTED_ORDER_TYPES)
        if unsupported_order_types:
            raise ValueError(
                f"Unsupported/unimplemented allowed_order_types: {sorted(unsupported_order_types)}."
            )
        for field_name in (
            "require_earnings_data",
            "allow_new_positions",
            "enable_strategy_proposals",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, bool):
                raise ValueError(f"{field_name} must be a boolean, got {value!r}.")

    def to_dict(self) -> dict:
        result = dataclasses.asdict(self)
        result["allowed_sides"] = list(self.allowed_sides)
        result["allowed_order_types"] = list(self.allowed_order_types)
        return result


def compute_policy_fingerprint(policy: TradingPolicy) -> str:
    """Deterministic fingerprint over every policy field except `notes`
    (free-text/explanatory, not behavior-affecting). Proposals bind to
    this in ADDITION to `version` -- a manually-maintained version string
    alone can't catch an edited-but-not-rebumped policy file (GPT review,
    2026-07-28): two policy files (e.g. a personal one copied from the
    default) can share the same version string yet have materially
    different limits, and approval previously only compared that string.
    Any change to a behavior-affecting field changes this fingerprint
    regardless of whether `version` was bumped, so approval fails closed
    on drift instead of depending on a human remembering to bump it."""
    payload = {k: v for k, v in policy.to_dict().items() if k != "notes"}
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def load_policy(path: str | Path = DEFAULT_POLICY_PATH) -> TradingPolicy:
    policy_path = Path(path)
    raw = json.loads(policy_path.read_text(encoding="utf-8"))
    raw["allowed_sides"] = tuple(raw.get("allowed_sides", ("buy", "sell")))
    raw["allowed_order_types"] = tuple(raw.get("allowed_order_types", ("market", "limit")))
    policy = TradingPolicy(**raw)
    policy.validate()
    return policy


def bump_policy_version(version: str) -> str:
    """Increment the last dot-separated numeric segment ("1.1.0" -> "1.1.1").

    A version string with no trailing numeric segment gets ".1" appended
    rather than being rejected -- the fingerprint, not the version string,
    is what approval actually binds to (see compute_policy_fingerprint), so
    the version's only job here is to be visibly different from its
    predecessor."""
    head, dot, tail = version.rpartition(".")
    if dot and tail.isdigit():
        return f"{head}.{int(tail) + 1}"
    if version.isdigit():
        return str(int(version) + 1)
    return f"{version}.1"


def policy_with_updated_flags(
    policy: TradingPolicy,
    *,
    allow_new_positions: bool | None = None,
    enable_strategy_proposals: bool | None = None,
    whole_shares_only: bool | None = None,
    min_cash_reserve_pct: float | None = None,
) -> TradingPolicy:
    """Return a NEW validated policy with the requested policy fields
    changed and the version bumped.

    `whole_shares_only` and `min_cash_reserve_pct` were added 2026-08-14 for
    the Settings toggles. The cash reserve deliberately reuses the EXISTING
    numeric field rather than gaining a companion boolean: 0 already means
    "no reserve", and a number plus a flag that both encode one rule is one
    refactor away from disagreeing.

    Exists for the UI's protected policy-update workflow
    (docs/reference/UI_FEATURE_CONTROLS_DESIGN.md section 3.1): these two
    flags are authoritative trading policy, not UI preferences, so a change
    must produce a new version and therefore a new fingerprint -- proposals
    created under the previous fingerprint fail validation and must be
    regenerated. That invalidation is the intended fail-closed consequence
    of editing policy, not a bug.

    Raises ValueError if the call would change nothing: a no-op "update"
    that still bumped the version would invalidate every pending proposal
    for no behavioral reason.
    """
    changes: dict[str, object] = {}
    if allow_new_positions is not None and allow_new_positions != policy.allow_new_positions:
        changes["allow_new_positions"] = allow_new_positions
    if (
        enable_strategy_proposals is not None
        and enable_strategy_proposals != policy.enable_strategy_proposals
    ):
        changes["enable_strategy_proposals"] = enable_strategy_proposals
    if whole_shares_only is not None and whole_shares_only != policy.whole_shares_only:
        changes["whole_shares_only"] = whole_shares_only
    if (
        min_cash_reserve_pct is not None
        and float(min_cash_reserve_pct) != float(policy.min_cash_reserve_pct)
    ):
        # validate() enforces the 0..1 bound; an out-of-range value must
        # raise there rather than be silently clamped here.
        changes["min_cash_reserve_pct"] = float(min_cash_reserve_pct)
    if not changes:
        raise ValueError(
            "No policy change requested: the proposed values match the active policy."
        )
    updated = dataclasses.replace(
        policy, version=bump_policy_version(policy.version), **changes
    )
    updated.validate()
    return updated


def save_policy(
    policy: TradingPolicy,
    path: str | Path,
    *,
    expected_fingerprint: str | None = None,
    expected_version: str | None = None,
    allow_unchecked_overwrite: bool = False,
) -> None:
    """Validate, then compare-and-swap the policy as atomic JSON.

    Atomic via write-to-temp-then-os.replace in the destination directory,
    so a crash mid-write can never leave a half-written policy file that a
    later load_policy() would reject (or worse, a truncated-but-parseable
    one). Validation runs BEFORE any filesystem effect: an invalid policy
    must leave the existing file byte-identical.

    UI/editor callers pass both expected values from the policy they rendered.
    An OS file lock serializes comparison and replacement, so a stale tab
    cannot restore an authoritative flag changed by another writer (CXL-004).
    Creating a new path needs no comparison. Replacing an existing policy
    without comparison requires the deliberately explicit
    ``allow_unchecked_overwrite=True`` escape hatch for controlled recovery or
    tests; merely forgetting the expected values fails loudly (CCR-003).
    """
    import uuid

    policy.validate()
    if (expected_fingerprint is None) != (expected_version is None):
        raise ValueError(
            "expected_fingerprint and expected_version must be supplied together"
        )
    if not isinstance(allow_unchecked_overwrite, bool):
        raise ValueError("allow_unchecked_overwrite must be a bool")
    if allow_unchecked_overwrite and expected_fingerprint is not None:
        raise ValueError(
            "allow_unchecked_overwrite cannot be combined with expected policy values"
        )
    destination = Path(path)
    serialized = json.dumps(policy.to_dict(), indent=2) + "\n"
    # FCS-015: uuid-suffixed temp name. A deterministic `.tmp` sibling races
    # between two concurrent writers (two browser tabs both saving policy):
    # both write the same scratch file, so the second clobbers the first's
    # content before either replace() runs. os.replace keeps the DESTINATION
    # untorn either way, so this is a lost update rather than corruption --
    # but it is the same temp-name race fixed in backtest/research_report.py
    # on 2026-07-31, and the fix was never generalized. Cleaned up in a
    # finally so a failed write leaves no litter beside the policy file.
    lock = ProcessSingleton(
        destination.with_name(f".{destination.name}.policy.lock")
    )
    try:
        lock.acquire()
    except ProcessSingletonError as exc:
        raise PolicyWriteConflictError(
            "another policy writer is active; reload before trying again"
        ) from exc
    temp_path = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        if (
            destination.exists()
            and expected_fingerprint is None
            and not allow_unchecked_overwrite
        ):
            raise ValueError(
                "expected_fingerprint and expected_version are required when "
                "overwriting an existing policy; pass "
                "allow_unchecked_overwrite=True only for controlled recovery"
            )
        if expected_fingerprint is not None:
            try:
                current = load_policy(destination)
            except FileNotFoundError as exc:
                raise PolicyWriteConflictError(
                    "the policy was removed after it was loaded; reload before saving"
                ) from exc
            if (
                compute_policy_fingerprint(current) != expected_fingerprint
                or current.version != expected_version
            ):
                raise PolicyWriteConflictError(
                    "the policy changed since it was loaded; reload and review the "
                    "new values before saving"
                )
        temp_path.write_text(serialized, encoding="utf-8")
        os.replace(temp_path, destination)
    finally:
        temp_path.unlink(missing_ok=True)
        lock.release()
