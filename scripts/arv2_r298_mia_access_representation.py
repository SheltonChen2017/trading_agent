"""Pure, fixed R298 general-view Mia representation, without access authority.

Only the complete row observed by the separately authenticated H diagnostic is
newly recognized. Its null UID, label and current permissions do not establish
an account, synthetic actor, lease, privacy or permission to retry an operation.
After extracting that exact row from a detached snapshot, every remaining
project/dedicated check is delegated to the unchanged owner/A5 contract. There
is no transport, filesystem, credential, lock, retry or launch entry point.
"""
from __future__ import annotations

from scripts import arv2_r298_collaborator_access as previous


SCHEMA = 'arv2-r298-mia-access-representation-v1'
PROJECT_ID, PROJECT_NAME = previous.PROJECT_ID, previous.PROJECT_NAME
ORGANIZATION_SHA256 = previous.ORGANIZATION_SHA256
OWNER_ROW_SHA256, A5_ROW_SHA256 = previous.OWNER_ROW_SHA256, previous.A5_ROW_SHA256
MIA_ROW_SHA256 = '710488e487086c93979cd034cf19a073d870e63cf92bdc7904cf2c97f5b0fcf2'
MIA_PUBLIC_ID_SHA256 = '4802c36d758c1b43bbbd50cb3428192a80dc3ea0fee517416285436bdf6e6f14'
PREVIOUS_SOURCE_SHA256 = '57333e2d6932f3b75bb42bc59214ebda2ce9afdf65b9054b7edc7ee5cbd37d93'
OBSERVATION_HEAD = '283ec2c3ce0bdc04499dbf476bc42d2b1bb76442'
OBSERVATION_REPORT_SHA256 = '156d7f98e8c68819ef507d15f6d0390729f82afb3bb00f3054de61458a0d7171'
FALSE_FLAGS = {**previous.FALSE_FLAGS, 'exclusive_lease_proven': False,
    'account_identity_proven': False, 'source_permission_granted': False,
    'backtest_launch_authorized': False, 'point_in_time_proven': False,
    'formal_identity_admitted': False, 'formal_forward_ready': False,
    'paper_or_live_ready': False}
FINITE_CODES = previous.FINITE_CODES | frozenset(('general_row_pin',
    'general_row_duplicate', 'general_owner_required', 'mia_row_shape',
    'mia_public_id_pin', 'receipt_shape'))
# Preserve exact exception identity for every unchanged strict predicate.
AccessRefused = previous.AccessRefused
canonical, sha = previous._canonical, previous._sha


def require(condition, code):
    if not condition:
        raise AccessRefused(code)


def finite_error(error):
    if type(error) is AccessRefused:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in FINITE_CODES:
            return {'code': args[0]}
    return {'code': 'unknown'}


def profile_record():
    """Fixed documentary/source bindings, not caller-supplied authority flags."""
    return {'schema': SCHEMA, 'project_id': PROJECT_ID, 'project_name': PROJECT_NAME,
        'organization_sha256': ORGANIZATION_SHA256,
        'owner_row_sha256': OWNER_ROW_SHA256, 'a5_row_sha256': A5_ROW_SHA256,
        'mia_row_sha256': MIA_ROW_SHA256, 'mia_public_id_sha256': MIA_PUBLIC_ID_SHA256,
        'previous_source_sha256': PREVIOUS_SOURCE_SHA256,
        'observation_head': OBSERVATION_HEAD,
        'observation_report_sha256': OBSERVATION_REPORT_SHA256,
        'observation_report_bytes': 5271, 'observation_actual_exit': 0,
        'observation_documentary_only': True,
        'scope': 'pure_pinned_current_general_representation_only',
        'max_general_collaborators': 3, 'exact_dedicated_collaborators': 1,
        'pinned_owner_required': True, 'each_full_row_at_most_once': True,
        'old_strict_verifier_after_exact_mia_extraction': True,
        'response_pin_encoding': 'old_canonical_json_ascii_plus_LF_before_filter',
        'response_pins_are_raw_wire_authentication': False,
        'automatic_pin_refresh': False, 'receipt_is_operational_capability': False,
        **FALSE_FLAGS}


def _mia_shape(row):
    require(row.get('owner') is False and 'uid' in row and row['uid'] is None
        and type(row.get('permission')) is str and row['permission'] == 'write'
        and row.get('liveControl') is True and type(row.get('name')) is str
        and row['name'] == 'Mia' and type(row.get('publicId')) is str
        and 'codeSourceId' not in row and type(row.get('email')) is str,
        'mia_row_shape')
    require(sha(canonical(row['publicId'])) == MIA_PUBLIC_ID_SHA256,
        'mia_public_id_pin')


def verify_access(project_response, dedicated_response):
    """Match supplied representations only; authenticate no request or lease.

    The old bounded JSON snapshot rejects hostile/non-JSON input before row
    inspection. No field-only Mia inference, policy argument or pin refresh is
    allowed. The complete dedicated snapshot is never filtered or amended.
    """
    project_packet = previous._response(project_response)
    dedicated = previous._response(dedicated_response)
    # Pin supplied canonical snapshots before the sole filtering mutation. A
    # canonical object pin is not transport/raw-wire provenance authentication.
    original_project_sha256 = sha(canonical(project_packet))
    original_dedicated_sha256 = sha(canonical(dedicated))
    projects = project_packet.get('projects')
    require(type(projects) is list and len(projects) == 1
        and type(projects[0]) is dict, 'project_shape')
    project = projects[0]
    rows = project.get('collaborators')
    require(type(rows) is list and 1 <= len(rows) <= 3
        and all(type(row) is dict for row in rows), 'general_collaborators')
    digests = [sha(canonical(row)) for row in rows]
    require(len(set(digests)) == len(digests), 'general_row_duplicate')
    require(OWNER_ROW_SHA256 in digests, 'general_owner_required')
    require(all(digest in (OWNER_ROW_SHA256, A5_ROW_SHA256, MIA_ROW_SHA256)
        for digest in digests), 'general_row_pin')
    remaining = []
    for row, digest in zip(rows, digests):
        if digest == MIA_ROW_SHA256:
            _mia_shape(row)
        else:
            remaining.append(row)
    project['collaborators'] = remaining
    # The old verifier still binds exact project/org/name/owner, positive
    # integer owner UID, idleness, non-public contradiction, dedicated owner
    # permissions, whole owner/A5 rows, and owner equality across both views.
    previous.verify_access(project_packet, dedicated)
    result = {'schema': SCHEMA, 'project_id': PROJECT_ID,
        'organization_sha256': ORGANIZATION_SHA256,
        'owner_row_sha256': OWNER_ROW_SHA256, 'general_count': len(rows),
        'dedicated_count': 1,
        'original_project_response_sha256': original_project_sha256,
        'original_dedicated_response_sha256': original_dedicated_sha256,
        'observed_a5_row_sha256': A5_ROW_SHA256 if A5_ROW_SHA256 in digests else None,
        'observed_mia_row_sha256': MIA_ROW_SHA256 if MIA_ROW_SHA256 in digests else None,
        'matched_current_access_representation': True, **FALSE_FLAGS}
    return validate_receipt(result)


def validate_receipt(value):
    """Closed redacted receipt validation; a copied receipt grants no authority."""
    keys = {'schema', 'project_id', 'organization_sha256', 'owner_row_sha256',
        'general_count', 'dedicated_count', 'observed_a5_row_sha256',
        'observed_mia_row_sha256', 'original_project_response_sha256',
        'original_dedicated_response_sha256', 'matched_current_access_representation',
        *FALSE_FLAGS}
    require(type(value) is dict and all(type(key) is str for key in value)
        and set(value) == keys, 'receipt_shape')
    require(type(value['schema']) is str and value['schema'] == SCHEMA
        and type(value['project_id']) is int and value['project_id'] == PROJECT_ID
        and type(value['organization_sha256']) is str
        and value['organization_sha256'] == ORGANIZATION_SHA256
        and type(value['owner_row_sha256']) is str
        and value['owner_row_sha256'] == OWNER_ROW_SHA256
        and type(value['general_count']) is int and 1 <= value['general_count'] <= 3
        and type(value['dedicated_count']) is int and value['dedicated_count'] == 1
        and value['matched_current_access_representation'] is True
        and all(value[key] is False for key in FALSE_FLAGS), 'receipt_shape')
    for key, pin in (('observed_a5_row_sha256', A5_ROW_SHA256),
            ('observed_mia_row_sha256', MIA_ROW_SHA256)):
        require(value[key] is None or (type(value[key]) is str and value[key] == pin),
            'receipt_shape')
    for key in ('original_project_response_sha256', 'original_dedicated_response_sha256'):
        require(type(value[key]) is str and len(value[key]) == 64
            and all(letter in '0123456789abcdef' for letter in value[key]), 'receipt_shape')
    require(value['general_count'] == 1 + int(value['observed_a5_row_sha256'] is not None)
        + int(value['observed_mia_row_sha256'] is not None), 'receipt_shape')
    # Only fixed primitive fields remain, so copying cannot invoke caller hooks.
    return dict(value)
