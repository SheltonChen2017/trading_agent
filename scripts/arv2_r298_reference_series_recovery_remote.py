"""Pure strict-owner/A5 access recovery for the unchanged P experiment.

P stopped before any source edit, compile or job. A new R parent owns a second
attempt; this wrapper changes no scientific source, job name, receipt schema,
result acceptance or lifecycle except using the narrower frozen access policy.
There is no operational entry point or modification of frozen module globals.
"""
from __future__ import annotations

from scripts import arv2_r298_reference_series_phase_remote as frozen
from scripts import arv2_r298_collaborator_access as access


WRAPPER_SCHEMA = 'arv2-r298-reference-series-recovery-remote-r-v1'
SCHEMA, PROJECT_ID, ATTEMPT = frozen.SCHEMA, frozen.PROJECT_ID, frozen.ATTEMPT
PROJECTION_SHA256, PROFILE_SHA256 = frozen.PROJECTION_SHA256, frozen.PROFILE_SHA256
SOURCE_MANIFEST_SHA256 = frozen.SOURCE_MANIFEST_SHA256
BACKTEST_NAME = frozen.BACKTEST_NAME
PAYLOAD_KEYS, FINITE, Refused = frozen.PAYLOAD_KEYS, frozen.FINITE, frozen.Refused
COMPILE_POLLS, COMPILE_INTERVAL = frozen.COMPILE_POLLS, frozen.COMPILE_INTERVAL
CAPACITY_POLLS, CAPACITY_INTERVAL = frozen.CAPACITY_POLLS, frozen.CAPACITY_INTERVAL
STATUS_POLLS, STATUS_INTERVAL = frozen.STATUS_POLLS, frozen.STATUS_INTERVAL
canonical, sha, finite = frozen.canonical, frozen.sha, frozen.finite
failure_evidence = frozen.failure_evidence
select_response, validate_selected = frozen.select_response, frozen.validate_selected
validate_compile_receipt = frozen.validate_compile_receipt
validate_launch_receipt, validate_terminal_receipt = frozen.validate_launch_receipt, frozen.validate_terminal_receipt
validate_result_receipt, validate_result_observation = frozen.validate_result_receipt, frozen.validate_result_observation
validate_partial_observation = frozen.validate_partial_observation
projection, _binding = frozen.projection, frozen._binding


def profile_record():
    return {'schema': WRAPPER_SCHEMA, 'recovery_epoch': 'R', 'scientific_attempt': 2,
        'maximum_scientific_attempts': 3, 'scientific_schema': SCHEMA,
        'scientific_job_name': BACKTEST_NAME, 'scientific_projection_sha256': PROJECTION_SHA256,
        'scientific_profile_sha256': PROFILE_SHA256, 'scientific_source_manifest_sha256': SOURCE_MANIFEST_SHA256,
        'scientific_source_changed': False, 'frozen_p_remote_sha256':
            '660d8f5f2ac8d0bf7f1382d2667db9a229c44ee47d47d96cd1408a927da182fd',
        'strict_access_schema': access.SCHEMA,
        'strict_access_source_sha256': '57333e2d6932f3b75bb42bc59214ebda2ce9afdf65b9054b7edc7ee5cbd37d93',
        'mia_general_row_accepted': False, 'dedicated_owner_required': True,
        'current_access_required_before_every_mutation': True,
        'q_observation_is_access_authority': False, 'frozen_p_profile_documentary_only': True,
        'frozen_p_policy': frozen.profile_record()}


class QuoteDiagnostic(frozen.QuoteDiagnostic):
    """All frozen P bounds/gates, with strictly narrower access validation."""

    def _access(self, prefix):
        project = self._call(prefix + '-project', 'projects/read', {'projectId': PROJECT_ID})
        dedicated = self._call(prefix + '-collaborators', 'projects/collaboration/read', {'projectId': PROJECT_ID})
        checked = access.verify_access(project, dedicated)
        self._event(prefix + '-access', {'event': 'access', 'observation': checked})
