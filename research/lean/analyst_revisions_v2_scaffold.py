"""Analyst Revisions V2 offline-assembled LEAN scaffold. NO ALPHA STATISTIC.

ARV2-4F-B5B lets a pure host-side contract authenticate these exact bytes as
the prospective ``main.py`` member of an authenticated source inventory.  It
deliberately refuses in ``initialize`` before touching data, Object Store,
results, portfolio state, or any other LEAN service.  Source assembly is not
project creation, upload, compile, launch, result, deployment, order, or
trading authority, and no physical Object Store adapter is present here.

The owner-directed first round is the descriptive 2021--2025 sensitivity.
The separately frozen 2020--2025 formal primary remains authoritative and is
not replaced or rescued by this scaffold.
"""
from AlgorithmImports import *  # noqa: F403  (LEAN's documented entry point)


SCAFFOLD_SCHEMA = "arv2-qc-lean-entry-scaffold-v2"
SOURCE_ASSEMBLY_SCHEMA = "arv2-qc-lean-source-assembly-schema-v1"
STATUS = "offline_source_inventory_authenticated_runtime_refuses"
AUTHORITY = (
    "source_structure_only_no_credential_account_project_configuration_"
    "object_store_provider_input_outcome_upload_compile_launch_result_"
    "deployment_order_or_trading_authority"
)
QC_CLOUD_ENTRY_NAME = "main.py"
SCAFFOLD_ONLY_MARKER = (
    "ARV2-4F-B5B SOURCE_ASSEMBLY_ONLY: QC execution is not authorized"
)
PHYSICAL_ADAPTER_PRESENT = False
REAL_QC_OBJECT_STORE_ACCESS_PERFORMED = False
CLOUD_COMPILE_PERFORMED = False
BACKTEST_PERFORMED = False

EVALUATION_ID = "arv2-eval-stock-historical-qc-001"
ALGORITHM_ID = "arv2-qc-stock-event-study-core-v2"
RUN_CONTRACT_SCHEMA = "arv2-qc-stock-event-study-run-candidate-v2"
RUN_CONTRACT_SOURCE_SHA256 = (
    "a72aa500a5c2d2fe68cfe9a00e6531a8c1a241e212cb8df8e2a7a56dba3d77d5"
)

B4_SCHEMA_ID = "arv2-qc-object-store-read-contract-5dcb6cffb8f9688b"
B4_SCHEMA_SHA256 = (
    "5dcb6cffb8f9688b1a63a0ea452fd7f4c3e706df7941691ede58c95e0f055dd2"
)
B4_SCHEMA_ARTIFACT_SHA256 = (
    "95c3242405dddaaec40af01113a6823235fa74fcf405ab7b30ab5c6a45a8e987"
)
B4_SOURCE_SHA256 = (
    "bf370a894986cec8ac341ef8f43bce91aeab4568295ab94c281ce5defaa4d2e3"
)
B4_SOURCE_CANONICAL_LF_BYTE_COUNT = 57_361

FORMAL_PRIMARY_FOLD_IDS = (
    "arv2-wf-test-2020",
    "arv2-wf-test-2021",
    "arv2-wf-test-2022",
    "arv2-wf-test-2023",
    "arv2-wf-test-2024",
    "arv2-wf-test-2025",
)
DESCRIPTIVE_SENSITIVITY_FOLD_IDS = (
    "arv2-wf-test-2021",
    "arv2-wf-test-2022",
    "arv2-wf-test-2023",
    "arv2-wf-test-2024",
    "arv2-wf-test-2025",
)
CAPABILITY_FLAGS = (
    ("credential_access", False),
    ("qc_account_access", False),
    ("project_creation", False),
    ("project_configuration", False),
    ("object_store_read", False),
    ("object_store_write", False),
    ("provider_access", False),
    ("production_input_read", False),
    ("outcome_access", False),
    ("upload", False),
    ("cloud_compile", False),
    ("backtest_launch", False),
    ("result_access", False),
    ("result_disposition", False),
    ("deployment", False),
    ("orders", False),
    ("trading", False),
)


class AnalystRevisionsV2StockEventStudyScaffold(QCAlgorithm):  # noqa: F405
    """Refuses before a LEAN service and cannot compute an evaluation."""

    def initialize(self):
        raise RuntimeError(SCAFFOLD_ONLY_MARKER)

    def on_end_of_algorithm(self):
        return None
