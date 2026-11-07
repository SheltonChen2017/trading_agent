"""Prospective bounded QC error observations, preserving the frozen TLS client.

The subclass changes only the response boundary. It retains validated finite
response evidence and lossy redacted error text before a failure is discarded.
It never retains raw bodies, context, headers, source or exceptions. The caller
still owns endpoint/action scope, native isolation, claim and parent deadline.
This cannot reconstruct any earlier attempt's discarded response or prove cause.
"""
import base64
import json
import re
import time

from scripts import observe_arv2_r345_qc_availability as base
from scripts import arv2_r298_qc_response_evidence as evidence
from scripts import arv2_r298_qc_error_text as error_text

SCHEMA = 'arv2-r345-qc-error-transport-v3'
MAX_FAILURE_BODY = 64 * 1024
MAX_DIAGNOSTIC = 24 * 1024
Refused, FINITE, credentials = base.Refused, base.FINITE, base.credentials


def validate_diagnostic(value):
    base.require(type(value) is dict and set(value) == {'schema', 'endpoint', 'response', 'error_text'}
        and value['schema'] == SCHEMA and type(value['endpoint']) is str
        and re.fullmatch('[a-z]+(?:/[a-z]+){0,4}', value['endpoint']), 'response')
    try:
        evidence.validate_evidence(value['response'])
        error_text.validate_error_text(value['error_text'])
    except (evidence.EvidenceError, error_text.ErrorTextError):
        raise Refused('response') from None
    for key in ('http_status', 'body_byte_count', 'body_sha256'):
        base.require(value['response'][key] == value['error_text'][key], 'response')
    raw = base.canonical(value)
    base.require(0 < len(raw) <= MAX_DIAGNOSTIC, 'bound')
    return json.loads(raw)


def project_diagnostic(status, raw, endpoint, *, sensitive_values, source_text):
    """Pure supplied-buffer projection; provenance and context are external."""
    result = {'schema': SCHEMA, 'endpoint': endpoint,
        'response': evidence.project_response(status, raw),
        'error_text': error_text.project_error_text(status, raw,
            sensitive_values=sensitive_values, source_text=source_text)}
    return validate_diagnostic(result)


def profile_record():
    return {'schema': SCHEMA, 'host': base.HOST, 'port': base.PORT,
        'CA': {'byte_count': base.CA_SIZE, 'sha256': base.CA_SHA256},
        'request_seconds': base.HTTP_SECONDS, 'max_success_body': base.MAX_BODY,
        'max_non200_JSON_body': MAX_FAILURE_BODY, 'max_diagnostic': MAX_DIAGNOSTIC,
        'evidence_profile_sha256': evidence.PROFILE_SHA256,
        'error_text_profile_sha256': error_text.PROFILE_SHA256,
        'failed_body_policy': 'only_identity_encoded_bounded_JSON_non200_body_no_download_rows_or_raw_retention',
        'context': 'actual_token_user_timestamp_digest_basic_header_organization_key_name_codeSourceId_and_uploaded_source',
        'operational_scope_external': True, 'cause_authenticated': False,
        'universal_secret_detection': False, 'retry_authority': False}


class API(base.API):
    def __init__(self, secret, store, deadline):
        self.last_diagnostic = None
        super().__init__(secret, store, deadline)

    def _diagnose(self, status, raw, endpoint, payload, timestamp, digest, auth):
        sensitive = [self.secret['QC_API_TOKEN'], self.secret['QC_USER_ID'], timestamp,
            digest, auth, 'Basic ' + auth]
        for name in ('organizationId', 'key', 'name', 'codeSourceId'):
            value = payload.get(name)
            if type(value) is str and value:
                sensitive.append(value)
        if type(payload.get('projectId')) is int:
            sensitive.append(str(payload['projectId']))
        source = payload.get('content') if type(payload.get('content')) is str else None
        self.last_diagnostic = project_diagnostic(status, raw, endpoint,
            sensitive_values=tuple(sensitive), source_text=source)
        # Save before any later journal failure. Only this validated projection
        # reaches the sink; source/context/raw response stay in local memory.
        self.store.journal('api-error-diagnostic', self.last_diagnostic)

    def _exchange(self, endpoint, payload):
        """Same fixed-host TLS/CA/FD bounds; new pre-discard error projection."""
        self.last_http_status, self.last_diagnostic = None, None
        self.store.intent(endpoint, payload.get('projectId'))
        self._ca_verify()
        timestamp = str(int(time.time()))
        digest = base.sha((self.secret['QC_API_TOKEN'] + ':' + timestamp).encode('ascii'))
        auth = base64.b64encode((self.secret['QC_USER_ID'] + ':' + digest).encode('ascii')).decode('ascii')
        body = base.canonical(payload)
        headers = {'Host': base.HOST, 'Authorization': 'Basic ' + auth, 'Timestamp': timestamp,
            'Content-Type': 'application/json', 'Content-Length': str(len(body)),
            'Accept-Encoding': 'identity', 'Connection': 'close'}
        tcp = secured = connection = None
        try:
            with base.alarm(min(base.HTTP_SECONDS, base.remaining(self.deadline))):
                tcp = base.socket.socket(self.family, base.socket.SOCK_STREAM, base.socket.IPPROTO_TCP)
                tcp.settimeout(min(base.HTTP_SECONDS, base.remaining(self.deadline))); tcp.connect(self.address)
                secured = self.context.wrap_socket(tcp, server_hostname=base.HOST)
                base.require(secured.version() in ('TLSv1.2', 'TLSv1.3'), 'transport')
                connection = base.http.client.HTTPConnection(base.HOST, base.PORT,
                    timeout=min(base.HTTP_SECONDS, base.remaining(self.deadline)))
                connection.auto_open = 0; connection.sock = secured
                base.require(connection.debuglevel == base.http.client.HTTPConnection.debuglevel == 0, 'transport')
                self.store.attempt(endpoint, payload.get('projectId'))
                connection.request('POST', '/api/v2/' + endpoint, body=body, headers=headers)
                response = connection.getresponse()
                base.require(type(response.status) is int and 100 <= response.status <= 599, 'http_status')
                self.last_http_status = response.status
                self.statuses.append({'endpoint': endpoint, 'http_status': response.status})
                base.require(response.getheader('Content-Encoding', 'identity').lower() == 'identity', 'response')
                maximum = base.MAX_BODY if response.status == 200 else MAX_FAILURE_BODY
                if response.status != 200:
                    content_type = response.getheader('Content-Type', '').split(';', 1)[0].strip().lower()
                    base.require(content_type == 'application/json', 'http_status')
                length = response.getheader('Content-Length')
                base.require(length is None or length.isdecimal() and 0 < int(length) <= maximum, 'bound')
                raw = response.read(maximum + 1)
                base.require(0 < len(raw) <= maximum and (length is None or len(raw) == int(length)), 'bound')
                self.responses.append({'endpoint': endpoint, **base.pin(raw)})
                if response.status != 200:
                    self._diagnose(response.status, raw, endpoint, payload, timestamp, digest, auth)
                    raise Refused('http_status')
                try:
                    value = base.parse(raw)
                except Refused:
                    self._diagnose(response.status, raw, endpoint, payload, timestamp, digest, auth)
                    raise
                if not (type(value) is dict and value.get('success') is True
                        and ('errors' not in value or type(value['errors']) is list and not value['errors'])):
                    self._diagnose(response.status, raw, endpoint, payload, timestamp, digest, auth)
                    raise Refused('response')
                self._ca_verify()
                return value
        except Refused:
            raise
        except BaseException:
            raise Refused('transport') from None
        finally:
            if connection is not None:
                connection.close()
            else:
                for stream in (secured, tcp):
                    if stream is not None: stream.close()
