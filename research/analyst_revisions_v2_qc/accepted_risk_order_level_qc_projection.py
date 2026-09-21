"""Exact, backtest-only QC source projection for QQQ order-level runs.

The projected runtime may submit simulated ``MarketOnOpenOrder`` requests
inside a QuantConnect backtest.  The source firewall rejects every other
order family, deployment and brokerage capabilities, live mode other than the
runtime's read-only refusal check, dynamic code loading, network/process I/O,
and Object Store writes.  This module only assembles and authenticates source;
it performs no QuantConnect, provider, credential, upload, launch, or result
I/O.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import re
from pathlib import Path

from research.analyst_revisions_v2.canonical import canonical_json_bytes

from . import accepted_risk_delta_order_package as delta_package_builder
from . import accepted_risk_preliminary_package as package_builder
from . import accepted_risk_qqq_order_level_qc_runtime as runtime_builder
from . import accepted_risk_qqq_order_level_v12_qc_runtime as v12_runtime_builder
from . import accepted_risk_qqq_order_level_v13_qc_runtime as v13_runtime_builder
from . import accepted_risk_qqq_order_level_v14_qc_runtime as v14_runtime_builder
from . import accepted_risk_qqq_order_level_v15_qc_runtime as v15_runtime_builder
from . import accepted_risk_qqq_order_level_v16_qc_runtime as v16_runtime_builder
from . import accepted_risk_qqq_order_level_v17_qc_runtime as v17_runtime_builder


class AcceptedRiskOrderLevelQcProjectionError(ValueError):
    """The input lineage, source closure, or capability boundary changed."""


PROJECTION_SCHEMA = "arv2-order-level-qc-source-projection-v1"
SOURCE_SCHEMA = "arv2-order-level-qc-source-file-v1"
MAIN_PROJECT_PATH = "main.py"
RUNTIME_PROJECT_PATH = "accepted_risk_qqq_order_level_qc_runtime.py"
V12_RUNTIME_PROJECT_PATH = "accepted_risk_qqq_order_level_v12_qc_runtime.py"
V13_RUNTIME_PROJECT_PATH = "accepted_risk_qqq_order_level_v13_qc_runtime.py"
V14_RUNTIME_PROJECT_PATH = "accepted_risk_qqq_order_level_v14_qc_runtime.py"
V15_RUNTIME_PROJECT_PATH = "accepted_risk_qqq_order_level_v15_qc_runtime.py"
V16_RUNTIME_PROJECT_PATH = "accepted_risk_qqq_order_level_v16_qc_runtime.py"
V17_RUNTIME_PROJECT_PATH = "accepted_risk_qqq_order_level_v17_qc_runtime.py"
FORCED_EXIT_PROJECT_PATH = "accepted_risk_order_level_forced_exit.py"
MAX_SOURCE_FILE_BYTES = 64_000
# The fixed ten-file closure includes the ETF-residual accounting and
# synchronous order-event authentication. V8's direct QC enum boundary adds
# source bytes. V11 adds an exact CLR-enum reflection bridge; 290,000 is the
# smallest round-number successor that retains the prospective 2,048-byte
# aggregate review margin without weakening the 64,000-byte per-file cap.
MAX_TOTAL_SOURCE_BYTES = 290_000
# V12 is the first profile whose exact closure contains the separately audited
# forced-exit state machine.  Its measured production closure remains below
# 322,952 bytes; 325,000 is the smallest 5,000-byte round ceiling that keeps
# the prospective 2,048-byte review margin.  Legacy profiles retain 290,000.
MAX_FORCED_EXIT_TOTAL_SOURCE_BYTES = 325_000
# V13 adds only the separately versioned end-callback rollover wrapper to the
# exact V12 source closure.  Its measured production closure is 329,308 bytes;
# 335,000 is the smallest 5,000-byte round ceiling retaining the prospective
# 2,048-byte margin.  V12 and legacy profiles keep their narrower ceilings.
MAX_ROLLOVER_TOTAL_SOURCE_BYTES = 335_000
# V14 adds one prospective diagnostic wrapper to the exact V13 closure.  Its
# measured production closure is 344,215 bytes; 350,000 is the smallest
# 5,000-byte round ceiling retaining the prospective 2,048-byte margin.  The
# ceiling is profile-bound so older profiles retain narrower inventories.
MAX_DIAGNOSTIC_TOTAL_SOURCE_BYTES = 350_000
# V15 adds one account-reconciliation wrapper to the exact V14 closure.  Its
# exact production size is pinned by the focused projection test; 365,000 is
# the smallest 5,000-byte round ceiling preserving the review margin.
MAX_ACCOUNT_TOTAL_SOURCE_BYTES = 365_000
# V16 adds one exact mean-exposure-complement wrapper to the immutable V15
# closure.  Its exact production size is pinned by focused projection tests;
# 375,000 is the smallest 5,000-byte round ceiling retaining the margin.
MAX_EXPOSURE_TOTAL_SOURCE_BYTES = 375_000
# V17 adds one fail-closed decision-skip wrapper to the immutable V16
# closure.  Its exact production size is pinned by focused projection tests;
# 400,000 is the smallest 5,000-byte round ceiling retaining the margin.
MAX_SKIP_TOTAL_SOURCE_BYTES = 400_000
MIN_REVIEW_MARGIN_BYTES = 2_048
_ENGINE_ORDER_PROFILE_IDS = (
    v12_runtime_builder.FORCED_EXIT_PROFILE_IDS
    + v13_runtime_builder.ROLLOVER_PROFILE_IDS
    + v14_runtime_builder.DIAGNOSTIC_PROFILE_IDS
    + v15_runtime_builder.ACCOUNT_PROFILE_IDS
    + v16_runtime_builder.EXPOSURE_PROFILE_IDS
    + v17_runtime_builder.SKIP_PROFILE_IDS
)

PROJECT_SOURCE_PATHS = (
    "accepted_risk_preliminary_rating_policy.py",
    "accepted_risk_preliminary_rating_evaluator.py",
    "accepted_risk_preliminary_qc_figi.py",
    "accepted_risk_market_cap_stock_portfolio_tilt.py",
    "accepted_risk_order_level_benchmark.py",
    "accepted_risk_order_level_core.py",
    "accepted_risk_order_level_input_runtime.py",
    "accepted_risk_sequential_r055_score.py",
    RUNTIME_PROJECT_PATH,
)


def _project_source_paths(profile_id: str) -> tuple[str, ...]:
    if profile_id in v17_runtime_builder.SKIP_PROFILE_IDS:
        return PROJECT_SOURCE_PATHS + (
            FORCED_EXIT_PROJECT_PATH,
            V12_RUNTIME_PROJECT_PATH,
            V13_RUNTIME_PROJECT_PATH,
            V14_RUNTIME_PROJECT_PATH,
            V15_RUNTIME_PROJECT_PATH,
            V16_RUNTIME_PROJECT_PATH,
            V17_RUNTIME_PROJECT_PATH,
        )
    if profile_id in v16_runtime_builder.EXPOSURE_PROFILE_IDS:
        return PROJECT_SOURCE_PATHS + (
            FORCED_EXIT_PROJECT_PATH,
            V12_RUNTIME_PROJECT_PATH,
            V13_RUNTIME_PROJECT_PATH,
            V14_RUNTIME_PROJECT_PATH,
            V15_RUNTIME_PROJECT_PATH,
            V16_RUNTIME_PROJECT_PATH,
        )
    if profile_id in v15_runtime_builder.ACCOUNT_PROFILE_IDS:
        return PROJECT_SOURCE_PATHS + (
            FORCED_EXIT_PROJECT_PATH,
            V12_RUNTIME_PROJECT_PATH,
            V13_RUNTIME_PROJECT_PATH,
            V14_RUNTIME_PROJECT_PATH,
            V15_RUNTIME_PROJECT_PATH,
        )
    if profile_id in v14_runtime_builder.DIAGNOSTIC_PROFILE_IDS:
        return PROJECT_SOURCE_PATHS + (
            FORCED_EXIT_PROJECT_PATH,
            V12_RUNTIME_PROJECT_PATH,
            V13_RUNTIME_PROJECT_PATH,
            V14_RUNTIME_PROJECT_PATH,
        )
    if profile_id in v13_runtime_builder.ROLLOVER_PROFILE_IDS:
        return PROJECT_SOURCE_PATHS + (
            FORCED_EXIT_PROJECT_PATH,
            V12_RUNTIME_PROJECT_PATH,
            V13_RUNTIME_PROJECT_PATH,
        )
    return PROJECT_SOURCE_PATHS + (
        (FORCED_EXIT_PROJECT_PATH, V12_RUNTIME_PROJECT_PATH)
        if profile_id in v12_runtime_builder.FORCED_EXIT_PROFILE_IDS
        else ()
    )


def _maximum_total_source_bytes(profile_id: str) -> int:
    if profile_id in v17_runtime_builder.SKIP_PROFILE_IDS:
        return MAX_SKIP_TOTAL_SOURCE_BYTES
    if profile_id in v16_runtime_builder.EXPOSURE_PROFILE_IDS:
        return MAX_EXPOSURE_TOTAL_SOURCE_BYTES
    if profile_id in v15_runtime_builder.ACCOUNT_PROFILE_IDS:
        return MAX_ACCOUNT_TOTAL_SOURCE_BYTES
    if profile_id in v14_runtime_builder.DIAGNOSTIC_PROFILE_IDS:
        return MAX_DIAGNOSTIC_TOTAL_SOURCE_BYTES
    if profile_id in v13_runtime_builder.ROLLOVER_PROFILE_IDS:
        return MAX_ROLLOVER_TOTAL_SOURCE_BYTES
    return (
        MAX_FORCED_EXIT_TOTAL_SOURCE_BYTES
        if profile_id in v12_runtime_builder.FORCED_EXIT_PROFILE_IDS
        else MAX_TOTAL_SOURCE_BYTES
    )


def _require_profile(profile_id: str) -> dict[str, object]:
    if profile_id in v17_runtime_builder.SKIP_PROFILE_IDS:
        return v17_runtime_builder.require_qqq_order_level_profile(profile_id)
    if profile_id in v16_runtime_builder.EXPOSURE_PROFILE_IDS:
        return v16_runtime_builder.require_qqq_order_level_profile(profile_id)
    if profile_id in v15_runtime_builder.ACCOUNT_PROFILE_IDS:
        return v15_runtime_builder.require_qqq_order_level_profile(profile_id)
    if profile_id in v14_runtime_builder.DIAGNOSTIC_PROFILE_IDS:
        return v14_runtime_builder.require_qqq_order_level_profile(profile_id)
    if profile_id in v13_runtime_builder.ROLLOVER_PROFILE_IDS:
        return v13_runtime_builder.require_qqq_order_level_profile(profile_id)
    if profile_id in v12_runtime_builder.FORCED_EXIT_PROFILE_IDS:
        return v12_runtime_builder.require_qqq_order_level_profile(profile_id)
    return runtime_builder.require_qqq_order_level_profile(profile_id)


def _all_profile_ids() -> tuple[str, ...]:
    return (
        runtime_builder.PROFILE_IDS
        + v12_runtime_builder.FORCED_EXIT_PROFILE_IDS
        + v13_runtime_builder.ROLLOVER_PROFILE_IDS
        + v14_runtime_builder.DIAGNOSTIC_PROFILE_IDS
        + v15_runtime_builder.ACCOUNT_PROFILE_IDS
        + v16_runtime_builder.EXPOSURE_PROFILE_IDS
        + v17_runtime_builder.SKIP_PROFILE_IDS
    )

_FUTURE = re.compile(rb"(?m)^\s*from\s+__future__\s+import\s+")
_ALLOWED_IMPORT_MODULES = {
    "AlgorithmImports",
    "accepted_risk_order_level_core",
    "accepted_risk_order_level_forced_exit",
    "accepted_risk_order_level_benchmark",
    "accepted_risk_market_cap_stock_portfolio_tilt",
    "accepted_risk_order_level_input_runtime",
    "accepted_risk_preliminary_qc_figi",
    "accepted_risk_preliminary_rating_evaluator",
    "accepted_risk_preliminary_rating_policy",
    "accepted_risk_qqq_order_level_qc_runtime",
    "accepted_risk_qqq_order_level_v12_qc_runtime",
    "accepted_risk_qqq_order_level_v13_qc_runtime",
    "accepted_risk_qqq_order_level_v14_qc_runtime",
    "accepted_risk_qqq_order_level_v15_qc_runtime",
    "accepted_risk_qqq_order_level_v16_qc_runtime",
    "accepted_risk_qqq_order_level_v17_qc_runtime",
    "accepted_risk_sequential_r055_score",
    "collections",
    "collections.abc",
    "dataclasses",
    "datetime",
    "decimal",
    "enum",
    "fractions",
    "gzip",
    "hashlib",
    "io",
    "itertools",
    "json",
    "math",
    "re",
    "research.analyst_revisions_v2_qc",
    "time",
    "types",
    "typing",
    "zoneinfo",
}
_FORBIDDEN_IMPORT_ROOTS = {
    "builtins",
    "clr",
    "http",
    "importlib",
    "os",
    "pathlib",
    "requests",
    "socket",
    "subprocess",
    "urllib",
    "webbrowser",
    "websocket",
}
_FORBIDDEN_DYNAMIC_CALLS = {
    "compile",
    "eval",
    "exec",
    "getattr",
    "globals",
    "import",
    "locals",
    "setattr",
    "vars",
}
_FORBIDDEN_ORDER_CALLS = {
    "buy",
    "calculateorderquantity",
    "cancel",
    "cancelopenorders",
    "cancelorder",
    "comboleglimitorder",
    "combolimitorder",
    "combomarketorder",
    "exerciseoption",
    "limitiftouchedorder",
    "limitorder",
    "liquidate",
    "marketoncloseorder",
    "marketorder",
    "order",
    "sell",
    "setholdings",
    "stoplimitorder",
    "stopmarketorder",
    "submitorderrequest",
    "trailingstoporder",
    "transactions",
    "updateorderfields",
}
_FORBIDDEN_OPERATION_CALLS = {
    "debug",
    "deploy",
    "download",
    "error",
    "log",
    "quit",
    "setalpha",
    "setbrokeragemodel",
    "setexecution",
    "setportfolioconstruction",
    "setriskmanagement",
    "setuniverseselection",
}
_FORBIDDEN_OBJECT_STORE_WRITES = {
    "clear",
    "delete",
    "getfilepath",
    "save",
    "savebytes",
    "savestring",
}
_FORBIDDEN_CAPABILITY_NAMES = {
    "broker",
    "brokerage",
    "brokeragemodel",
    "deploy",
    "deployment",
    "notify",
    "notifications",
    "paper",
    "papertrade",
    "papertrading",
}


def _normalized(value: str) -> str:
    return value.casefold().replace("_", "")


def _approved_system_enum_import(node: ast.ImportFrom, project_path: str) -> bool:
    return (
        project_path == MAIN_PROJECT_PATH
        and node.module == "System"
        and tuple((item.name, item.asname) for item in node.names) == (
            ("Convert", "_Arv2DotNetConvert"),
            ("Enum", "_Arv2DotNetEnum"),
        )
    )


def _is_self_algorithm(value: ast.AST) -> bool:
    return (
        isinstance(value, ast.Attribute)
        and isinstance(value.value, ast.Name)
        and value.value.id == "self"
        and value.attr == "_algorithm"
    )


def _approved_market_on_open_call(node: ast.Attribute, project_path: str) -> bool:
    return (
        project_path == RUNTIME_PROJECT_PATH
        and _normalized(node.attr) == "marketonopenorder"
        and _is_self_algorithm(node.value)
    )


def _approved_live_mode_read(node: ast.Attribute, project_path: str) -> bool:
    return (
        project_path == RUNTIME_PROJECT_PATH
        and _normalized(node.attr) == "livemode"
        and isinstance(node.ctx, ast.Load)
        and _is_self_algorithm(node.value)
    )


def _approved_fee_order_read(node: ast.Attribute, project_path: str) -> bool:
    return (
        project_path == MAIN_PROJECT_PATH
        and _normalized(node.attr) == "order"
        and isinstance(node.ctx, ast.Load)
        and isinstance(node.value, ast.Name)
        and node.value.id == "parameters"
    )


def _approved_forced_exit_order_lookup(
    node: ast.Attribute,
    parents: dict[ast.AST, ast.AST],
    project_path: str,
    forced_exit_main: bool,
) -> bool:
    """Admit one versioned, read-only engine-order authentication call."""

    if project_path != MAIN_PROJECT_PATH or not forced_exit_main:
        return False
    name = _normalized(node.attr)
    if name == "transactions":
        transactions = node
        order_lookup = parents.get(node)
    elif name == "getorderbyid":
        order_lookup = node
        transactions = node.value
    else:
        return False
    call = parents.get(order_lookup)
    assignment = parents.get(call)
    return (
        isinstance(transactions, ast.Attribute)
        and _normalized(transactions.attr) == "transactions"
        and isinstance(transactions.value, ast.Name)
        and transactions.value.id == "self"
        and isinstance(order_lookup, ast.Attribute)
        and _normalized(order_lookup.attr) == "getorderbyid"
        and order_lookup.value is transactions
        and isinstance(call, ast.Call)
        and call.func is order_lookup
        and len(call.args) == 1
        and isinstance(call.args[0], ast.Attribute)
        and call.args[0].attr == "order_id"
        and isinstance(call.args[0].value, ast.Name)
        and call.args[0].value.id == "event"
        and not call.keywords
        and isinstance(assignment, ast.Assign)
        and len(assignment.targets) == 1
        and isinstance(assignment.targets[0], ast.Name)
        and assignment.targets[0].id == "engine_order"
    )


def _is_exact_forced_exit_main(tree: ast.Module, project_path: str) -> bool:
    """Bind the lookup exception to an exact versioned generated main."""

    if project_path != MAIN_PROJECT_PATH:
        return False
    allowed_imports = {
        "accepted_risk_qqq_order_level_v12_qc_runtime": (
            "AcceptedRiskQqqOrderLevelV12QcRuntime",
            v12_runtime_builder.FORCED_EXIT_PROFILE_IDS,
        ),
        "accepted_risk_qqq_order_level_v13_qc_runtime": (
            "AcceptedRiskQqqOrderLevelV13QcRuntime",
            v13_runtime_builder.ROLLOVER_PROFILE_IDS,
        ),
        "accepted_risk_qqq_order_level_v14_qc_runtime": (
            "AcceptedRiskQqqOrderLevelV14QcRuntime",
            v14_runtime_builder.DIAGNOSTIC_PROFILE_IDS,
        ),
        "accepted_risk_qqq_order_level_v15_qc_runtime": (
            "AcceptedRiskQqqOrderLevelV15QcRuntime",
            v15_runtime_builder.ACCOUNT_PROFILE_IDS,
        ),
        "accepted_risk_qqq_order_level_v16_qc_runtime": (
            "AcceptedRiskQqqOrderLevelV16QcRuntime",
            v16_runtime_builder.EXPOSURE_PROFILE_IDS,
        ),
        "accepted_risk_qqq_order_level_v17_qc_runtime": (
            "AcceptedRiskQqqOrderLevelV17QcRuntime",
            v17_runtime_builder.SKIP_PROFILE_IDS,
        ),
    }
    imports = tuple(
        (
            node.module,
            tuple((item.name, item.asname) for item in node.names),
        )
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module in allowed_imports
    )
    if len(imports) != 1:
        return False
    imported_module, imported_names = imports[0]
    runtime_name, profile_ids = allowed_imports[imported_module]
    expected_names = (
        (runtime_name, "AcceptedRiskQqqOrderLevelQcRuntime"),
        ("STARTING_CASH", None),
    )
    driver_initializers = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        call = node.value
        if not (
            isinstance(target, ast.Attribute)
            and target.attr == "_arv2_driver"
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
            and isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "AcceptedRiskQqqOrderLevelQcRuntime"
        ):
            continue
        profile_keywords = tuple(
            keyword.value
            for keyword in call.keywords
            if keyword.arg == "profile_id"
        )
        driver_initializers.append(profile_keywords)
    return (
        imported_names == expected_names
        and len(driver_initializers) == 1
        and len(driver_initializers[0]) == 1
        and isinstance(driver_initializers[0][0], ast.Constant)
        and driver_initializers[0][0].value in profile_ids
    )


def _audit_cloud_capabilities(text: str, project_path: str) -> None:
    """Reject every cloud capability except one direct simulated MOO call."""

    try:
        tree = ast.parse(text, filename=project_path, feature_version=(3, 11))
    except SyntaxError as exc:
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level QC source is not valid Python AST"
        ) from exc
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    forced_exit_main = _is_exact_forced_exit_main(tree, project_path)
    locally_defined = {
        _normalized(node.name)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = {item.name for item in node.names}
            roots = {item.split(".", 1)[0] for item in modules}
            if roots & _FORBIDDEN_IMPORT_ROOTS or not modules.issubset(
                _ALLOWED_IMPORT_MODULES
            ):
                raise AcceptedRiskOrderLevelQcProjectionError(
                    "order-level QC source imports a forbidden capability"
                )
            continue
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "System":
                if not _approved_system_enum_import(node, project_path):
                    raise AcceptedRiskOrderLevelQcProjectionError(
                        "order-level QC source imports a forbidden capability"
                    )
                continue
            root = module.split(".", 1)[0]
            imported = {_normalized(item.name) for item in node.names}
            if (
                root in _FORBIDDEN_IMPORT_ROOTS
                or module not in _ALLOWED_IMPORT_MODULES
                or imported
                & (
                    _FORBIDDEN_DYNAMIC_CALLS
                    | _FORBIDDEN_ORDER_CALLS
                    | _FORBIDDEN_OPERATION_CALLS
                    | _FORBIDDEN_OBJECT_STORE_WRITES
                    | _FORBIDDEN_CAPABILITY_NAMES
                    | {"marketonopenorder", "livemode"}
                )
            ):
                raise AcceptedRiskOrderLevelQcProjectionError(
                    "order-level QC source imports a forbidden capability"
                )
            continue
        if isinstance(node, ast.Name):
            name = _normalized(node.id)
            if name in _FORBIDDEN_DYNAMIC_CALLS:
                raise AcceptedRiskOrderLevelQcProjectionError(
                    "order-level QC source references a dynamic capability"
                )
            if name in _FORBIDDEN_CAPABILITY_NAMES or name == "marketonopenorder":
                raise AcceptedRiskOrderLevelQcProjectionError(
                    "order-level QC source references an unscoped operational capability"
                )
            continue
        if isinstance(node, ast.Attribute):
            name = _normalized(node.attr)
            if name == "marketonopenorder":
                parent = parents.get(node)
                if (
                    not _approved_market_on_open_call(node, project_path)
                    or not isinstance(parent, ast.Call)
                    or parent.func is not node
                ):
                    raise AcceptedRiskOrderLevelQcProjectionError(
                        "MarketOnOpenOrder is permitted only as the runtime's direct simulated call"
                    )
            elif name == "livemode":
                if not _approved_live_mode_read(node, project_path):
                    raise AcceptedRiskOrderLevelQcProjectionError(
                        "live mode is permitted only as the runtime's read-only refusal check"
                    )
            elif name == "order" and _approved_fee_order_read(
                node, project_path
            ):
                pass
            elif name in {"transactions", "getorderbyid"}:
                if not _approved_forced_exit_order_lookup(
                    node, parents, project_path, forced_exit_main
                ):
                    raise AcceptedRiskOrderLevelQcProjectionError(
                        "engine order lookup is permitted only as the versioned forced-exit generated-main authentication call"
                    )
            elif name in (
                _FORBIDDEN_ORDER_CALLS
                | _FORBIDDEN_OPERATION_CALLS
                | _FORBIDDEN_OBJECT_STORE_WRITES
                | _FORBIDDEN_CAPABILITY_NAMES
                | {"getattribute"}
            ):
                raise AcceptedRiskOrderLevelQcProjectionError(
                    "order-level QC source reaches a forbidden operational capability"
                )
            continue
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                name = _normalized(node.func.attr)
            elif isinstance(node.func, ast.Name):
                name = _normalized(node.func.id)
            else:
                name = None
            if name in _FORBIDDEN_DYNAMIC_CALLS and (
                isinstance(node.func, ast.Name) or name == "getattribute"
            ):
                raise AcceptedRiskOrderLevelQcProjectionError(
                    "order-level QC source calls a dynamic capability"
                )
            if name in _FORBIDDEN_ORDER_CALLS:
                raise AcceptedRiskOrderLevelQcProjectionError(
                    "order-level QC source calls a forbidden operational capability"
                )
            if name in (
                _FORBIDDEN_OPERATION_CALLS
                | _FORBIDDEN_OBJECT_STORE_WRITES
                | _FORBIDDEN_CAPABILITY_NAMES
            ) and not (
                isinstance(node.func, ast.Name)
                and (name in locally_defined or node.func.id.startswith("_"))
            ):
                raise AcceptedRiskOrderLevelQcProjectionError(
                    "order-level QC source calls a forbidden operational capability"
                )


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level QC projection is not canonical ASCII JSON"
        ) from exc


@dataclasses.dataclass(frozen=True, slots=True)
class OrderLevelQcSourceFile:
    schema: str
    project_path: str
    byte_count: int
    content_sha256: str
    source_bytes: bytes = dataclasses.field(repr=False)

    def to_record(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "project_path": self.project_path,
            "byte_count": self.byte_count,
            "content_sha256": self.content_sha256,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class AcceptedRiskOrderLevelQcProjection:
    schema: str
    projection_id: str
    projection_sha256: str
    package_id: str
    package_sha256: str
    package_lineage_sha256: str
    activation_manifest_key: str
    activation_manifest_sha256: str
    activation_manifest_byte_count: int
    profile_id: str
    profile_sha256: str
    source_files: tuple[OrderLevelQcSourceFile, ...]
    total_source_byte_count: int
    preliminary: bool
    formal: bool
    backtest_only: bool
    simulated_order_submission: bool
    market_on_open_orders_only: bool
    live_orders: bool
    paper_orders: bool
    funded_orders: bool
    deployment: bool
    broker_credentials: bool
    trading: bool

    def to_record(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "projection_id": self.projection_id,
            "projection_sha256": self.projection_sha256,
            "package_id": self.package_id,
            "package_sha256": self.package_sha256,
            "package_lineage_sha256": self.package_lineage_sha256,
            "activation_manifest_key": self.activation_manifest_key,
            "activation_manifest_sha256": self.activation_manifest_sha256,
            "activation_manifest_byte_count": self.activation_manifest_byte_count,
            "profile_id": self.profile_id,
            "profile_sha256": self.profile_sha256,
            "source_files": [item.to_record() for item in self.source_files],
            "total_source_byte_count": self.total_source_byte_count,
            "preliminary": self.preliminary,
            "formal": self.formal,
            "backtest_only": self.backtest_only,
            "simulated_order_submission": self.simulated_order_submission,
            "market_on_open_orders_only": self.market_on_open_orders_only,
            "live_orders": self.live_orders,
            "paper_orders": self.paper_orders,
            "funded_orders": self.funded_orders,
            "deployment": self.deployment,
            "broker_credentials": self.broker_credentials,
            "trading": self.trading,
        }


def _validate_source(project_path: str, source: bytes) -> OrderLevelQcSourceFile:
    if (
        type(project_path) is not str
        or "/" in project_path
        or not project_path.endswith(".py")
        or type(source) is not bytes
        or not source
        or len(source) > MAX_SOURCE_FILE_BYTES
        or b"\r" in source
        or b"\x00" in source
        or _FUTURE.search(source) is not None
    ):
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level QC source violates size, path, or future-import guard"
        )
    try:
        text = source.decode("ascii")
    except UnicodeDecodeError as exc:
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level QC source is not exact ASCII"
        ) from exc
    _audit_cloud_capabilities(text, project_path)
    try:
        compile(text, project_path, "exec")
        compile("QC_PRELUDE_SENTINEL = True\n" + text, project_path, "exec")
        compile("from AlgorithmImports import *\n" + text, project_path, "exec")
    except (SyntaxError, ValueError) as exc:
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level QC source does not compile raw and after QC prelude"
        ) from exc
    return OrderLevelQcSourceFile(
        SOURCE_SCHEMA,
        project_path,
        len(source),
        hashlib.sha256(source).hexdigest(),
        source,
    )


def _require_delta_package(value):
    if type(value) is not delta_package_builder.AcceptedRiskDeltaOrderPackage:
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level input package type changed"
        )
    package = package_builder.require_accepted_risk_preliminary_package(
        value.package
    )
    if (
        value.lineage_sha256
        != hashlib.sha256(canonical_json_bytes(value.lineage)).hexdigest()
        or package.source_disposition_sha256 != value.lineage_sha256
        or value.decision_cutoff_session
        != delta_package_builder.DELTA_DECISION_END_SESSION
        or value.final_execution_session
        != delta_package_builder.FINAL_EXECUTION_SESSION
        or value.current_snapshot_identity_only is not True
        or value.refreshed_security_master is not False
        or any(
            getattr(value, field) is not False
            for field in (
                "provider_access",
                "quantconnect_access",
                "outcome_access",
                "orders",
                "trading",
            )
        )
    ):
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level input package lineage or disclosure changed"
        )
    return value, package


def _main_source(
    *,
    activation_manifest_key: str,
    activation_manifest_sha256: str,
    activation_manifest_byte_count: int,
    profile: dict[str, object],
) -> bytes:
    """Render the thin QC entry after the runtime interface is authenticated."""

    engine_order_profile = profile.get("profile_id") in _ENGINE_ORDER_PROFILE_IDS
    try:
        start = tuple(
            int(part) for part in profile["evaluation_start_session"].split("-")
        )
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level profile start session changed"
        ) from exc
    if (
        len(start) != 3
        or profile.get("profile_id") not in _all_profile_ids()
        or profile.get("decision_cutoff_session")
        != delta_package_builder.DELTA_DECISION_END_SESSION
        or profile.get("final_execution_session")
        != delta_package_builder.FINAL_EXECUTION_SESSION
        or profile.get("backtest_only") is not True
        or profile.get("simulated_order_submission") is not True
        or any(
            profile.get(field) is not False
            for field in (
                "live_orders",
                "paper_orders",
                "funded_orders",
                "deployment",
                "broker_credentials",
                "trading",
            )
        )
    ):
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level profile capability or date binding changed"
        )
    end = tuple(
        int(part)
        for part in delta_package_builder.FINAL_EXECUTION_SESSION.split("-")
    )
    preopen_schedule_source = (
        "\n        self.schedule.on(\n"
        "            self.date_rules.every_day(qqq_benchmark),\n"
        "            self.time_rules.before_market_open(qqq_benchmark, 10),\n"
        "            self._arv2_driver.on_before_open,\n"
        "        )"
        if profile.get("execution_submission_timing")
        == "NEXT_AUTHENTICATED_SESSION_PREOPEN_10_MINUTES"
        else ""
    )
    enum_status_source = (
        "            order_status_enum=_arv2_reflected_order_status(OrderStatus),\n"
        if profile["profile_id"] in (
            runtime_builder.REFLECTED_TICKET_PROFILE_IDS
            + _ENGINE_ORDER_PROFILE_IDS
        )
        else "            order_status_enum=OrderStatus,\n"
        if profile["profile_id"] in runtime_builder.ENUM_PREOPEN_PROXY_PROFILE_IDS
        else ""
    )
    reflected_status_source = (
        '''from System import Convert as _Arv2DotNetConvert, Enum as _Arv2DotNetEnum


def _arv2_reflected_order_status(enum_type):
    refusal = "QC OrderStatus reflected map changed"
    try:
        names = tuple(_Arv2DotNetEnum.GetNames(enum_type))
        values = tuple(_Arv2DotNetEnum.GetValues(enum_type))
        numbers = tuple(_Arv2DotNetConvert.ToInt32(value) for value in values)
        reflected_type = values[0].GetType()
        same_type = all(value.GetType() == reflected_type for value in values)
    except Exception as exc:
        raise RuntimeError(refusal) from exc
    expected = (
        ("New", 0), ("Submitted", 1), ("PartiallyFilled", 2),
        ("Filled", 3), ("Canceled", 5), ("None", 6), ("Invalid", 7),
        ("CancelPending", 8), ("UpdateSubmitted", 9),
    )
    if (
        len(names) != len(expected)
        or len(values) != len(expected)
        or any(type(name) is not str for name in names)
        or any(type(number) is not int for number in numbers)
        or tuple(zip(names, numbers)) != expected
        or not same_type
        or any(type(value) is not type(values[0]) for value in values)
        or any(
            value == prior
            for index, value in enumerate(values)
            for prior in values[:index]
        )
    ):
        raise RuntimeError(refusal)

    class ReflectedOrderStatus:
        NEW, SUBMITTED, PARTIALLY_FILLED, FILLED, CANCELED, NONE, INVALID, CANCEL_PENDING, UPDATE_SUBMITTED = values

    return ReflectedOrderStatus


'''
        if profile["profile_id"] in (
            runtime_builder.REFLECTED_TICKET_PROFILE_IDS
            + _ENGINE_ORDER_PROFILE_IDS
        )
        else ""
    )
    # The V10 cloud diagnostic measured 4,764 canonical aggregate bytes.
    # Raise only this profile's generated-main guard; do not modify the
    # shared runtime file, quantize decimals, truncate digests, or rekey JSON.
    statistic_transport_source = (
        "# V10: 4764 exact aggregate bytes exceed the local 4096-byte guard.\n"
        "import accepted_risk_qqq_order_level_qc_runtime as _arv2_runtime_module\n"
        "\n"
        "_arv2_runtime_module.MAXIMUM_STATISTIC_BYTES = 8192\n"
        if profile["profile_id"] in (
            runtime_builder.TICKET_PROFILE_IDS
            + runtime_builder.REFLECTED_TICKET_PROFILE_IDS
            + _ENGINE_ORDER_PROFILE_IDS
        )
        else ""
    )
    order_event_source = (
        "        engine_order = self.transactions.get_order_by_id(event.order_id)\n"
        "        self._arv2_driver.on_order_event(\n"
        "            event, engine_order=engine_order,\n"
        "        )"
        if profile["profile_id"] in _ENGINE_ORDER_PROFILE_IDS
        else "        self._arv2_driver.on_order_event(event)"
    )
    runtime_import_module = (
        "accepted_risk_qqq_order_level_v17_qc_runtime"
        if profile["profile_id"] in v17_runtime_builder.SKIP_PROFILE_IDS
        else
        "accepted_risk_qqq_order_level_v16_qc_runtime"
        if profile["profile_id"] in v16_runtime_builder.EXPOSURE_PROFILE_IDS
        else
        "accepted_risk_qqq_order_level_v15_qc_runtime"
        if profile["profile_id"] in v15_runtime_builder.ACCOUNT_PROFILE_IDS
        else
        "accepted_risk_qqq_order_level_v14_qc_runtime"
        if profile["profile_id"] in v14_runtime_builder.DIAGNOSTIC_PROFILE_IDS
        else "accepted_risk_qqq_order_level_v13_qc_runtime"
        if profile["profile_id"] in v13_runtime_builder.ROLLOVER_PROFILE_IDS
        else "accepted_risk_qqq_order_level_v12_qc_runtime"
        if profile["profile_id"] in v12_runtime_builder.FORCED_EXIT_PROFILE_IDS
        else "accepted_risk_qqq_order_level_qc_runtime"
    )
    runtime_import_binding = (
        "AcceptedRiskQqqOrderLevelV17QcRuntime as AcceptedRiskQqqOrderLevelQcRuntime"
        if profile["profile_id"] in v17_runtime_builder.SKIP_PROFILE_IDS
        else
        "AcceptedRiskQqqOrderLevelV16QcRuntime as AcceptedRiskQqqOrderLevelQcRuntime"
        if profile["profile_id"] in v16_runtime_builder.EXPOSURE_PROFILE_IDS
        else
        "AcceptedRiskQqqOrderLevelV15QcRuntime as AcceptedRiskQqqOrderLevelQcRuntime"
        if profile["profile_id"] in v15_runtime_builder.ACCOUNT_PROFILE_IDS
        else
        "AcceptedRiskQqqOrderLevelV14QcRuntime as AcceptedRiskQqqOrderLevelQcRuntime"
        if profile["profile_id"] in v14_runtime_builder.DIAGNOSTIC_PROFILE_IDS
        else "AcceptedRiskQqqOrderLevelV13QcRuntime as AcceptedRiskQqqOrderLevelQcRuntime"
        if profile["profile_id"] in v13_runtime_builder.ROLLOVER_PROFILE_IDS
        else "AcceptedRiskQqqOrderLevelV12QcRuntime as AcceptedRiskQqqOrderLevelQcRuntime"
        if profile["profile_id"] in v12_runtime_builder.FORCED_EXIT_PROFILE_IDS
        else "AcceptedRiskQqqOrderLevelQcRuntime"
    )
    source = f'''from AlgorithmImports import *
from decimal import Decimal
{reflected_status_source}{statistic_transport_source}from {runtime_import_module} import (
    {runtime_import_binding},
    STARTING_CASH,
)
from accepted_risk_order_level_core import MODELED_FEE_RATE_PER_SIDE


class Arv2TenBpsFeeModel(FeeModel):
    def get_order_fee(self, parameters):
        price = Decimal(str(parameters.security.open))
        quantity = abs(Decimal(str(parameters.order.absolute_quantity)))
        if not price.is_finite() or price <= 0 or not quantity.is_finite():
            raise RuntimeError("ARV2 fee input is invalid")
        return OrderFee(CashAmount(
            price * quantity * MODELED_FEE_RATE_PER_SIDE,
            "USD",
        ))


class ARV2QqqOrderLevelAlgorithm(QCAlgorithm):
    def initialize(self):
        self.set_time_zone("America/New_York")
        self.settings.daily_precise_end_time = True
        self.set_start_date({start[0]}, {start[1]}, {start[2]})
        self.set_end_date({end[0]}, {end[1]}, {end[2]})
        self.set_cash(STARTING_CASH)
        self.universe_settings.asynchronous = False
        self.universe_settings.resolution = Resolution.MINUTE
        self.universe_settings.data_normalization_mode = DataNormalizationMode.RAW
        authority_benchmark = self.add_equity(
            "SPY",
            Resolution.DAILY,
            fill_forward=False,
            leverage=1,
            extended_market_hours=False,
            data_normalization_mode=DataNormalizationMode.TOTAL_RETURN,
        ).symbol
        qqq_benchmark = self.add_equity(
            "QQQ",
            Resolution.MINUTE,
            fill_forward=False,
            leverage=1,
            extended_market_hours={"True" if profile['profile_id'] in runtime_builder.PREOPEN_PROXY_PROFILE_IDS or engine_order_profile else "False"},
            data_normalization_mode=DataNormalizationMode.{"RAW" if profile['profile_id'] in runtime_builder.PROXY_PROFILE_IDS or engine_order_profile else "TOTAL_RETURN"},
        ).symbol
        self.set_benchmark(qqq_benchmark)
        qqq_constituent_universe = self.add_universe(
            self.universe.etf(
                qqq_benchmark,
                self.universe_settings,
                self._arv2_accept_qqq_constituents,
            )
        )
        self._arv2_driver = AcceptedRiskQqqOrderLevelQcRuntime(
            self,
            activation_manifest_key={activation_manifest_key!r},
            activation_manifest_sha256={activation_manifest_sha256!r},
            activation_manifest_byte_count={activation_manifest_byte_count},
            profile_id={profile['profile_id']!r},
            authority_benchmark_symbol=authority_benchmark,
            qqq_benchmark_symbol=qqq_benchmark,
            qqq_constituent_universe=qqq_constituent_universe,
            minute_resolution=Resolution.MINUTE,
            raw_normalization=DataNormalizationMode.RAW,
            trade_bar_type=TradeBar,
            daily_resolution=Resolution.DAILY,
            total_return_normalization=DataNormalizationMode.TOTAL_RETURN,
            fee_model_factory=lambda: Arv2TenBpsFeeModel(),
            slippage_model_factory=lambda: NullSlippageModel(),
{enum_status_source}        )
        self._arv2_driver.initialize()
        self.schedule.on(
            self.date_rules.every_day(qqq_benchmark),
            self.time_rules.after_market_close(qqq_benchmark, 0),
            self._arv2_driver.on_after_close,
        ){preopen_schedule_source}

    def _arv2_accept_qqq_constituents(self, constituents):
        if not hasattr(self, "_arv2_driver"):
            return []
        return self._arv2_driver.accept_qqq_constituents(constituents)

    def on_data(self, data):
        self._arv2_driver.on_data(data)

    def on_securities_changed(self, changes):
        self._arv2_driver.on_securities_changed(changes)

    def on_order_event(self, event):
{order_event_source}

    def on_end_of_algorithm(self):
        self._arv2_driver.on_end_of_algorithm()
'''
    return source.encode("ascii")


def build_accepted_risk_order_level_qc_projection(
    delta_package,
    *,
    profile_id: str,
) -> AcceptedRiskOrderLevelQcProjection:
    delta_package, package = _require_delta_package(delta_package)
    profile = _require_profile(profile_id)
    activation = package.upload_objects[-1]
    if (
        activation.role != "activation_manifest"
        or activation.activation_manifest is not True
        or not activation.object_store_key.endswith("/transport-manifest.json")
    ):
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level package activation descriptor changed"
        )
    root = Path(__file__).resolve().parent
    files = []
    source_paths = _project_source_paths(profile["profile_id"])
    for project_path in source_paths:
        try:
            source = (root / project_path).read_bytes()
        except OSError as exc:
            raise AcceptedRiskOrderLevelQcProjectionError(
                "order-level QC source is unavailable"
            ) from exc
        files.append(_validate_source(project_path, source))
    files.append(
        _validate_source(
            MAIN_PROJECT_PATH,
            _main_source(
                activation_manifest_key=activation.object_store_key,
                activation_manifest_sha256=activation.content_sha256,
                activation_manifest_byte_count=activation.byte_count,
                profile=profile,
            ),
        )
    )
    files.sort(key=lambda item: item.project_path)
    total = sum(item.byte_count for item in files)
    if (
        total + MIN_REVIEW_MARGIN_BYTES
        > _maximum_total_source_bytes(profile["profile_id"])
    ):
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level QC source set exceeds reviewed total size"
        )
    semantic = {
        "schema": PROJECTION_SCHEMA,
        "projection_id": None,
        "projection_sha256": None,
        "package_id": package.package_id,
        "package_sha256": package.package_sha256,
        "package_lineage_sha256": delta_package.lineage_sha256,
        "activation_manifest_key": activation.object_store_key,
        "activation_manifest_sha256": activation.content_sha256,
        "activation_manifest_byte_count": activation.byte_count,
        "profile_id": profile["profile_id"],
        "profile_sha256": profile["profile_sha256"],
        "source_files": [item.to_record() for item in files],
        "total_source_byte_count": total,
        "preliminary": True,
        "formal": False,
        "backtest_only": True,
        "simulated_order_submission": True,
        "market_on_open_orders_only": True,
        "live_orders": False,
        "paper_orders": False,
        "funded_orders": False,
        "deployment": False,
        "broker_credentials": False,
        "trading": False,
    }
    digest = hashlib.sha256(_canonical(semantic)).hexdigest()
    value = AcceptedRiskOrderLevelQcProjection(
        PROJECTION_SCHEMA,
        "arv2-order-level-qc-projection-" + digest[:24],
        digest,
        package.package_id,
        package.package_sha256,
        delta_package.lineage_sha256,
        activation.object_store_key,
        activation.content_sha256,
        activation.byte_count,
        profile["profile_id"],
        profile["profile_sha256"],
        tuple(files),
        total,
        True,
        False,
        True,
        True,
        True,
        False,
        False,
        False,
        False,
        False,
        False,
    )
    package_builder.require_accepted_risk_preliminary_package(package)
    return require_accepted_risk_order_level_qc_projection(value)


def require_accepted_risk_order_level_qc_projection(
    value: AcceptedRiskOrderLevelQcProjection,
) -> AcceptedRiskOrderLevelQcProjection:
    if type(value) is not AcceptedRiskOrderLevelQcProjection:
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level QC projection type changed"
        )
    profile = _require_profile(value.profile_id)
    source_paths = _project_source_paths(value.profile_id)
    maximum_total_source_bytes = _maximum_total_source_bytes(value.profile_id)
    observed_paths = tuple(item.project_path for item in value.source_files)
    if (
        value.schema != PROJECTION_SCHEMA
        or type(value.source_files) is not tuple
        or observed_paths != tuple(sorted((*source_paths, MAIN_PROJECT_PATH)))
        or value.profile_sha256 != profile["profile_sha256"]
        or value.total_source_byte_count
        != sum(item.byte_count for item in value.source_files)
        or (
            value.total_source_byte_count + MIN_REVIEW_MARGIN_BYTES
            > maximum_total_source_bytes
            if value.profile_id in _ENGINE_ORDER_PROFILE_IDS
            else value.total_source_byte_count > maximum_total_source_bytes
        )
        or value.preliminary is not True
        or value.formal is not False
        or value.backtest_only is not True
        or value.simulated_order_submission is not True
        or value.market_on_open_orders_only is not True
        or any(
            getattr(value, field) is not False
            for field in (
                "live_orders",
                "paper_orders",
                "funded_orders",
                "deployment",
                "broker_credentials",
                "trading",
            )
        )
    ):
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level QC projection disclosure or inventory changed"
        )
    rebuilt = tuple(
        _validate_source(item.project_path, item.source_bytes)
        for item in value.source_files
    )
    if rebuilt != value.source_files:
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level QC projected source identity changed"
        )
    main_source = next(
        item.source_bytes
        for item in value.source_files
        if item.project_path == MAIN_PROJECT_PATH
    )
    if main_source != _main_source(
        activation_manifest_key=value.activation_manifest_key,
        activation_manifest_sha256=value.activation_manifest_sha256,
        activation_manifest_byte_count=value.activation_manifest_byte_count,
        profile=profile,
    ):
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level QC main source diverged from its activation or profile"
        )
    semantic = value.to_record()
    semantic["projection_id"] = None
    semantic["projection_sha256"] = None
    digest = hashlib.sha256(_canonical(semantic)).hexdigest()
    if (
        value.projection_sha256 != digest
        or value.projection_id
        != "arv2-order-level-qc-projection-" + digest[:24]
    ):
        raise AcceptedRiskOrderLevelQcProjectionError(
            "order-level QC projection identity changed"
        )
    return value


def iter_accepted_risk_order_level_qc_sources(value):
    projection = require_accepted_risk_order_level_qc_projection(value)
    for item in projection.source_files:
        yield item.project_path, item.source_bytes


__all__ = (
    "AcceptedRiskOrderLevelQcProjection",
    "AcceptedRiskOrderLevelQcProjectionError",
    "OrderLevelQcSourceFile",
    "build_accepted_risk_order_level_qc_projection",
    "iter_accepted_risk_order_level_qc_sources",
    "require_accepted_risk_order_level_qc_projection",
)
