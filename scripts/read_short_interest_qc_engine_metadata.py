"""One-request, unexercised QC catalog observation draft; not an engine permit.

Only the named QC environment entries may be read, after an exclusive spent
claim. Authentication material exists in wire memory, never receipts/output.
Root must first prospectively freeze this exact source and decision in its lane
record. This module does not create projects, inspect nodes or launch jobs.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import urllib.error
import urllib.parse
import urllib.request

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts.qualify_finra_short_interest import _require_capture_platform, _guard_lane, _NoRedirect
from scripts.qualify_sharadar_companion import _guard_remote

ROOT = Path('/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest')
PARENT = Path('artifacts/short_interest/private/qc_engine_metadata')
ENDPOINT = 'https://www.quantconnect.com/api/v2/lean/versions/read'
BODY = b'{}'
MAX_BYTES = 2_000_000
CLAIM = 'one-readonly-engine-catalog-request.claim.json'
VERSION_FIELDS = frozenset(('id', 'created', 'description', 'leanHash', 'leanCloudHash', 'name', 'ref', 'public'))
PUBLIC_FIELDS = ('id', 'created', 'leanHash', 'leanCloudHash', 'name', 'ref', 'public')
REASONS = frozenset(('protected_storage_refused', 'request_budget_consumed', 'protocol_refused',
    'scope_changed', 'named_credentials_unavailable', 'credential_echo_discarded',
    'wire_request_refused', 'catalog_response_refused', 'public_version_unavailable'))


class MetadataRefusal(ValueError):
    def __init__(self, reason):
        self.code = reason if reason in REASONS else 'protocol_refused'
        super().__init__('REFUSED: ' + self.code)


def require(value, reason):
    if not value:
        raise MetadataRefusal(reason)


def clock(value):
    try:
        require(type(value) is str and re.fullmatch(
            r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z', value) is not None,
            'catalog_response_refused')
        parsed = datetime.fromisoformat(value[:-1] + '+00:00')
        require(parsed.utcoffset().total_seconds() == 0, 'catalog_response_refused')
        return parsed
    except (TypeError, ValueError, AttributeError):
        raise MetadataRefusal('catalog_response_refused') from None


def _sha(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{40}', value) is not None


def metadata_protocol():
    result = {'schema': 'si-readonly-qc-engine-catalog-protocol-v1',
        'method': 'POST', 'fixed_endpoint': ENDPOINT, 'body': {}, 'maximum_requests': 1,
        'claim_scope': 'fixed_parent_global_not_run_name_code_HEAD_or_invocation_time',
        'claim_before': 'named_environment_read_and_authentication_and_wire',
        'credential_names': ['QC_USER_ID', 'QC_API_TOKEN'], 'automatic_retries': 0,
        'redirects': False, 'proxies': False, 'maximum_response_bytes': MAX_BYTES,
        'selection': 'latest_created_public_true_then_highest_integer_id',
        'selection_is_execution_pin': False, 'public_fields': list(PUBLIC_FIELDS),
        'raw_provenance': 'protected_owner_only_after_credential_echo_discard_and_strict_schema',
        'forbidden_persisted_fields': ['credential', 'user_id', 'authentication_header', 'signature'],
        'outcome_looks': 0, 'qc_compile_or_launch_attempts': 0,
        'projects_nodes_history_upload_compile_jobs_backtests': False,
        'public_evidence': [
            'https://www.quantconnect.com/docs/v2/cloud-platform/api-reference/lean-version',
            'https://www.quantconnect.com/docs/v2/cloud-platform/api-reference/authentication']}
    result['protocol_sha256'] = hash_payload(result)
    return result


def _parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'catalog_response_refused')
            result[key] = value
        return result
    def invalid(_):
        raise MetadataRefusal('catalog_response_refused')
    try:
        require(type(raw) is bytes and len(raw) <= MAX_BYTES, 'catalog_response_refused')
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=invalid)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise MetadataRefusal('catalog_response_refused') from None


def select_public_metadata(value):
    require(type(value) is dict and set(value) == {'versions', 'success', 'errors'}
            and value['success'] is True and value['errors'] == []
            and type(value['errors']) is list and type(value['versions']) is list
            and len(value['versions']) <= 10_000, 'catalog_response_refused')
    public = []
    seen = set()
    for row in value['versions']:
        require(type(row) is dict and set(row) == VERSION_FIELDS
                and type(row['id']) is int and 0 <= row['id'] <= 2**53 - 1
                and row['id'] not in seen and type(row['public']) is bool
                and _sha(row['leanHash']) and _sha(row['leanCloudHash'])
                and type(row['description']) is str and len(row['description']) <= 20_000,
                'catalog_response_refused')
        created = clock(row['created'])
        for field in ('name', 'ref'):
            require(type(row[field]) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/\-]{0,199}', row[field]) is not None,
                    'catalog_response_refused')
        seen.add(row['id'])
        if row['public']:
            public.append((created, row['id'], {k: row[k] for k in PUBLIC_FIELDS}))
    require(bool(public), 'public_version_unavailable')
    selected = max(public, key=lambda entry: (entry[0], entry[1]))[2]
    return {'schema': 'si-public-qc-engine-catalog-observation-v1', 'selected': selected,
            'protocol_sha256': metadata_protocol()['protocol_sha256'],
            'public_version_count': len(public), 'runtime_or_wrapper_proof': False,
            'execution_pin_or_permission': False, 'actual_outcome_looks': 0, 'qc_launch_attempts': 0}


def named_credentials():
    # Deliberately no keychain/file fallback, environment dump, account query
    # or /authenticate probe that would add a second request.
    user, token = os.environ.get('QC_USER_ID'), os.environ.get('QC_API_TOKEN')
    require(type(user) is str and re.fullmatch('[1-9][0-9]{0,19}', user) is not None
            and type(token) is str and 16 <= len(token) <= 512
            and all(32 < ord(c) < 127 for c in token), 'named_credentials_unavailable')
    return user, token


def authenticated_request(credentials, timestamp):
    require(type(credentials) is tuple and len(credentials) == 2
            and type(timestamp) is int and timestamp > 0, 'named_credentials_unavailable')
    user, token = credentials
    require(type(user) is str and re.fullmatch('[1-9][0-9]{0,19}', user) is not None
            and type(token) is str and 16 <= len(token) <= 512
            and all(32 < ord(c) < 127 for c in token), 'named_credentials_unavailable')
    # Mandated ephemeral authentication signature, not a credential fingerprint.
    stamp = str(timestamp)
    digest = hashlib.sha256((token + ':' + stamp).encode()).hexdigest()
    authentication = base64.b64encode((user + ':' + digest).encode()).decode('ascii')
    request = urllib.request.Request(ENDPOINT, data=BODY, method='POST', headers={
        'Authorization': 'Basic ' + authentication, 'Timestamp': stamp,
        'Content-Type': 'application/json', 'Accept': 'application/json'})
    # Never serialize/repr request/markers. Python cannot promise memory erasure.
    return request, (user, token, digest, authentication, 'Basic ' + authentication)


def _echo(raw, parsed, markers):
    user, *secret_markers = markers
    texts = []
    try:
        texts.append(raw.decode('utf-8'))
    except UnicodeError:
        return True  # Malformed response never persisted.
    def walk(value):
        if type(value) is str:
            texts.append(value)
        elif type(value) is int and str(value) == user:
            raise MetadataRefusal('credential_echo_discarded')
        elif type(value) is dict:
            for key, v in value.items():
                texts.append(key); walk(v)
        elif type(value) is list:
            for v in value:
                walk(v)
    walk(parsed)
    for text in texts:
        if re.search(r'(?<![0-9])' + re.escape(user) + r'(?![0-9])', text):
            return True
        for marker in secret_markers:
            encoded = (marker, urllib.parse.quote(marker, safe=''),
                       base64.b64encode(marker.encode()).decode('ascii'))
            if any(item in text for item in encoded):
                return True
    return False


def wire_read(request):
    # Immutable destination, no foreign host, no proxy, no redirect, no retry.
    require(type(request) is urllib.request.Request and request.full_url == ENDPOINT
            and request.get_method() == 'POST' and request.data == BODY, 'wire_request_refused')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=30) as response:
            require(response.status == 200 and response.geturl() == ENDPOINT, 'wire_request_refused')
            raw = response.read(MAX_BYTES + 1)
            require(len(raw) <= MAX_BYTES, 'wire_request_refused')
            return raw
    except Exception:
        # Never print or retain HTTP error bodies, headers, URLs or exceptions.
        raise MetadataRefusal('wire_request_refused') from None


class ProtectedStore:
    def __init__(self, directory):
        _require_capture_platform()
        self.path = Path(directory).absolute()
        try:
            require(self.path.resolve() == self.path, 'protected_storage_refused')
            parent = self.path.parent.lstat()
            require(stat.S_ISDIR(parent.st_mode) and parent.st_uid == os.getuid()
                    and stat.S_IMODE(parent.st_mode) == 0o700, 'protected_storage_refused')
            fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.fd = fd
            self.check()
        except Exception:
            if hasattr(self, 'fd'):
                os.close(self.fd)
            raise MetadataRefusal('protected_storage_refused') from None

    def check(self):
        info = os.fstat(self.fd)
        named = self.path.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o700
                and (info.st_dev, info.st_ino) == (named.st_dev, named.st_ino)
                and self.path.resolve() == self.path, 'protected_storage_refused')

    def write(self, name, raw):
        self.check()
        require(type(name) is str and re.fullmatch('[a-z0-9][a-z0-9.-]{0,100}', name) is not None
                and type(raw) is bytes, 'protected_storage_refused')
        try:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
            with os.fdopen(fd, 'wb') as handle:
                info = os.fstat(handle.fileno())
                require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                        and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1,
                        'protected_storage_refused')
                handle.write(raw); handle.flush(); os.fsync(handle.fileno())
                final = os.fstat(handle.fileno())
                named = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
                require(final.st_nlink == named.st_nlink == 1
                        and (final.st_dev, final.st_ino) == (named.st_dev, named.st_ino),
                        'protected_storage_refused')
            os.fsync(self.fd)
            self.check()
        except FileExistsError:
            raise MetadataRefusal('request_budget_consumed' if name == CLAIM else 'protected_storage_refused') from None
        except Exception:
            raise MetadataRefusal('protected_storage_refused') from None

    def json(self, name, value):
        self.write(name, (canonical_json(value) + '\n').encode())

    def close(self):
        os.close(self.fd)


def capture_one(directory, *, frozen, guard, credential_reader, transport, timestamp):
    """Injected seams permit fabricated offline contracts, not alternate routes.

    Actual wrapper binds fixed root/parent, frozen code, known credentials and
    fixed urllib wire. It does not automatically freeze itself or reopen budget.
    """
    require(type(frozen) is dict and set(frozen) == {
            'protocol', 'source_sha256', 'decision_id', 'registered_head', 'registered_remote'}
            and frozen['protocol'] == metadata_protocol()
            and _sha(frozen['registered_head']) and _sha(frozen['registered_remote'])
            and type(frozen['source_sha256']) is str and re.fullmatch('[0-9a-f]{64}', frozen['source_sha256']) is not None
            and type(frozen['decision_id']) is str and re.fullmatch('[A-Z0-9-]{4,100}', frozen['decision_id']) is not None,
            'protocol_refused')
    store = ProtectedStore(directory)
    def scope_guard():
        try:
            guard()
        except Exception:
            raise MetadataRefusal('scope_changed') from None
    try:
        scope_guard()
        store.json(CLAIM, {'schema': 'si-qc-engine-catalog-spent-request-v1',
            'maximum_requests': 1, 'claimed_requests': 1, 'resumption_or_restart_allowed': False,
            'protocol_sha256': metadata_protocol()['protocol_sha256'],
            'source_sha256': frozen['source_sha256'], 'decision_id': frozen['decision_id'],
            'frozen_registration': frozen})
        body_observed, raw_write_started, raw_persisted = False, False, False
        try:
            credentials = credential_reader()  # Claim is already durable/spent.
            request, markers = authenticated_request(credentials, timestamp)
            scope_guard()
            raw = transport(request)
            body_observed = type(raw) is bytes
            require(type(raw) is bytes and len(raw) <= MAX_BYTES, 'wire_request_refused')
            value = _parse(raw)
            require(not _echo(raw, value, markers), 'credential_echo_discarded')
            result = select_public_metadata(value)
            scope_guard()
            # Exact wire bytes may contain nonpublic branch metadata: protected
            # private provenance only, never public output/Git/chat.
            raw_write_started = True
            store.write('response.raw.json', raw)
            raw_persisted = True
            result['raw_response_sha256'] = hash_bytes(raw)
            result['body_observed'] = True
            store.json('public-observation.json', result)
            return result
        except Exception as error:
            reason = error.code if type(error) is MetadataRefusal else 'wire_request_refused'
            store.json('refused.json', {'schema': 'si-qc-engine-catalog-refusal-v1',
                'reason': reason, 'claimed_requests': 1,
                'body_observed': body_observed, 'raw_response_write_started': raw_write_started,
                'raw_response_persisted': raw_persisted,
                'actual_outcome_looks': 0, 'qc_launch_attempts': 0})
            raise MetadataRefusal(reason) from None
    finally:
        store.close()


def run_metadata_observation(*, expected_head, expected_remote, frozen, timestamp=None):
    """Root-only prospective action; not invoked by import or tests."""
    require(type(frozen) is dict and frozen.get('registered_head') == expected_head
            and frozen.get('registered_remote') == expected_remote
            and _sha(expected_head) and _sha(expected_remote), 'protocol_refused')
    require(hash_bytes(Path(__file__).read_bytes()) == frozen.get('source_sha256'), 'protocol_refused')
    def guard():
        _guard_lane(ROOT, expected_head)
        _guard_remote(ROOT, expected_remote)
        require(hash_bytes(Path(__file__).read_bytes()) == frozen['source_sha256'], 'protocol_refused')
    guard()
    directory = ROOT / PARENT
    require(directory.parent.resolve() == directory.parent, 'protected_storage_refused')
    if not directory.exists():
        directory.mkdir(mode=0o700)  # Fixed scope: never a new timestamped budget.
    return capture_one(directory, frozen=frozen, guard=guard, credential_reader=named_credentials,
        transport=wire_read, timestamp=int(time.time()) if timestamp is None else timestamp)
