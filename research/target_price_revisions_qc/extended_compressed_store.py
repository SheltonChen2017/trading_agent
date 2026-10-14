"""Lossless bounded cloud storage adapters; no source, signal or cost changes.

Logical JSON keys/hashes remain those of the original plaintext bytes. Physical
objects contain gzip bytes. Audit encoding and both hash domains are recorded
in an exact own-job storage sidecar, not disguised as plaintext cloud custody.
Only native ObjectStore operations are used; no external export or network API
exists in this module. Imports do no I/O.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
import zlib

STUDY = 'TPR-CAP-TILT-EXT26-20261010-v1'
FREEZE_SHA256 = '90bdec5520b29bd932a3ec730f7c4c40c544ea7582731ad6680ef34ea8cf4067'
CANDIDATES = ('TPR-CAP-TILT-EXT26-ON-BASE-v1', 'TPR-CAP-TILT-EXT26-OFF-BASE-v1')
MAX_INPUT, MAX_INPUT_TOTAL = 32 * 1024 * 1024, 512 * 1024 * 1024
MAX_CHUNK, MAX_JOURNAL, MAX_METADATA = 512 * 1024, 256 * 1024 * 1024, 2 * 1024 * 1024
GZIP_OVERHEAD = 65536
MAP_KEYS = frozenset(('schema study_id freeze_sha256 preparation_sha256 bundle_sha256 processing_operation_id '
    'processing_plan_sha256 encoding gzip_level gzip_mtime payloads').split())
ROW_KEYS = frozenset(('plain_name logical_key plain_sha256 plain_bytes stored_name stored_key gzip_sha256 gzip_bytes').split())


def _fail(): raise ValueError('bounded lossless storage refused')
def sha256(raw): return hashlib.sha256(raw).hexdigest()


def _hash(value):
    if type(value) is not str or re.fullmatch(r'[a-f0-9]{64}', value) is None: _fail()
    return value


def _positive(value, maximum):
    if type(value) is not int or not 1 <= value <= maximum: _fail()
    return value


def _keys(value, keys):
    if type(value) is not dict or set(value) != set(keys): _fail()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('utf-8')


def _json(raw, maximum):
    if type(raw) is str: raw = raw.encode('utf-8')
    if type(raw) is not bytes or not 0 < len(raw) <= maximum: _fail()
    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result: _fail()
            result[key] = value
        return result
    def refuse(*_args): _fail()
    try: return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_float=refuse, parse_constant=refuse)
    except (UnicodeError, json.JSONDecodeError, RecursionError): _fail()


def _bytes(value, maximum):
    if type(value) is bytes:
        result = value
    elif type(value) in (bytearray, memoryview):
        if (value.nbytes if type(value) is memoryview else len(value)) > maximum: _fail()
        result = bytes(value)
    else:
        # QC returns System.Byte[]. Do not admit arbitrary iterables/coercions.
        try:
            from System import Array, Byte
            if type(value) is not Array[Byte] or not 0 < value.Length <= maximum: _fail()
            result = bytes(value)
        except (ImportError, AttributeError, TypeError, OverflowError): _fail()
    if not 0 < len(result) <= maximum: _fail()
    return result


def encode_gzip(raw, *, maximum=MAX_INPUT):
    if type(raw) is not bytes or not 0 < len(raw) <= maximum: _fail()
    stream = io.BytesIO()
    with gzip.GzipFile(fileobj=stream, mode='wb', filename='', compresslevel=9, mtime=0) as archive:
        archive.write(raw)
    encoded = stream.getvalue()
    if len(encoded) > maximum + GZIP_OVERHEAD: _fail()
    if decode_gzip(encoded, plain_bytes=len(raw), plain_sha256=sha256(raw), maximum=maximum) != raw: _fail()
    return encoded


def decode_gzip(encoded, *, plain_bytes, plain_sha256, maximum=MAX_INPUT,
                gzip_bytes=None, gzip_sha256=None):
    """Single-member gzip only, explicit EOF, exact hashes and pre-output bound."""
    _positive(plain_bytes, maximum); _hash(plain_sha256)
    encoded = _bytes(encoded, maximum + GZIP_OVERHEAD)
    if gzip_bytes is not None and len(encoded) != _positive(gzip_bytes, maximum + GZIP_OVERHEAD): _fail()
    if gzip_sha256 is not None and sha256(encoded) != _hash(gzip_sha256): _fail()
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        raw = decoder.decompress(encoded, plain_bytes + 1)
        if (len(raw) != plain_bytes or decoder.unconsumed_tail or not decoder.eof or decoder.unused_data
                or decoder.flush(1)): _fail()
    except zlib.error: _fail()
    if sha256(raw) != plain_sha256: _fail()
    return raw


def validate_mapping(mapping_json, *, expected_mapping_sha256=None):
    raw = mapping_json.encode('utf-8') if type(mapping_json) is str else mapping_json
    if expected_mapping_sha256 is not None and sha256(raw) != _hash(expected_mapping_sha256): _fail()
    body = _json(raw, 128 * 1024); _keys(body, MAP_KEYS)
    if (body['schema'] != 'tpr-ext26-gzip-input-map-v1' or body['study_id'] != STUDY
            or body['freeze_sha256'] != FREEZE_SHA256 or body['encoding'] != 'gzip'
            or type(body['gzip_level']) is not int or body['gzip_level'] != 9
            or type(body['gzip_mtime']) is not int or body['gzip_mtime'] != 0
            or type(body['processing_operation_id']) is not str
            or re.fullmatch(r'TPR-EXT26-COMPRESS-[A-Za-z0-9-]{1,48}', body['processing_operation_id']) is None): _fail()
    for name in ('preparation_sha256', 'bundle_sha256', 'processing_plan_sha256'): _hash(body[name])
    prefix = 'tpr-ext26/inputs/' + STUDY + '/' + body['preparation_sha256'] + '/'
    rows = body['payloads']
    if type(rows) is not list or len(rows) != 72: _fail()
    logical, stored, names, original_total, compressed_total = {}, set(), set(), 0, 0
    for row in rows:
        _keys(row, ROW_KEYS)
        plain, compressed = _hash(row['plain_sha256']), _hash(row['gzip_sha256'])
        original_total += _positive(row['plain_bytes'], MAX_INPUT)
        compressed_total += _positive(row['gzip_bytes'], MAX_INPUT + GZIP_OVERHEAD)
        if (row['plain_name'] != plain + '.json' or row['stored_name'] != 'gzip.' + compressed + '.json'
                or row['logical_key'] != prefix + plain + '.json'
                or row['stored_key'] != prefix + 'gzip.' + compressed + '.json'
                or row['logical_key'] in logical or row['stored_key'] in stored or row['stored_name'] in names): _fail()
        logical[row['logical_key']] = dict(row); stored.add(row['stored_key']); names.add(row['stored_name'])
    if original_total > MAX_INPUT_TOTAL or compressed_total > 256 * 1024 * 1024: _fail()
    return body, logical


class CompressedInputStore:
    """Exact logical-key read proxy. No uncompressed-key or missing-data fallback."""
    def __init__(self, native_store, mapping_json, *, expected_mapping_sha256=None):
        self.native = native_store
        self.mapping, self.by_key = validate_mapping(mapping_json, expected_mapping_sha256=expected_mapping_sha256)
        raw = mapping_json.encode('utf-8') if type(mapping_json) is str else mapping_json
        self.mapping_sha256, self.read_count = sha256(raw), 0

    def _row(self, key):
        if type(key) is not str or key not in self.by_key: _fail()
        return self.by_key[key]

    def contains_key(self, key):
        result = self.native.contains_key(self._row(key)['stored_key'])
        if type(result) is not bool: _fail()
        return result

    def read(self, key):
        row = self._row(key)
        if self.native.contains_key(row['stored_key']) is not True: _fail()
        raw = decode_gzip(self.native.read_bytes(row['stored_key']), plain_bytes=row['plain_bytes'],
            plain_sha256=row['plain_sha256'], gzip_bytes=row['gzip_bytes'], gzip_sha256=row['gzip_sha256'])
        try: text = raw.decode('utf-8')
        except UnicodeError: _fail()
        if text.encode('utf-8') != raw: _fail()
        self.read_count += 1
        return text


class CompressedAuditStore:
    """Only own native job journal keys; raw hashes retained plus gzip sidecar.

The old index uses logical keys. The physical objects are logical+'.gz'; their
encoded hashes/sizes are explicit in storage.json.gz. Its contents are hash/key
metadata, not source rows. All readback is inside cloud; no export is implied.
"""
    def __init__(self, native_store, binding):
        _keys(binding, ('candidate_id', 'config_sha256', 'freeze_sha256', 'input_hashes', 'attempt', 'project_id', 'job_id'))
        if (binding['candidate_id'] not in CANDIDATES or binding['freeze_sha256'] != FREEZE_SHA256
                or type(binding['input_hashes']) is not dict or not binding['input_hashes']
                or type(binding['attempt']) is not int or not 1 <= binding['attempt'] <= 3
                or type(binding['project_id']) is not int or binding['project_id'] <= 0
                or type(binding['job_id']) is not str or re.fullmatch(r'[A-Za-z0-9_.-]{1,200}', binding['job_id']) is None): _fail()
        _hash(binding['config_sha256'])
        for value in binding['input_hashes'].values(): _hash(value)
        self.native, self.binding = native_store, dict(binding)
        self.prefix = (f"tpr-ext26/evidence/{binding['candidate_id']}/{binding['config_sha256']}/attempt-{binding['attempt']}/"
                       f"{binding['project_id']}/{binding['job_id']}/")
        self.descriptors, self.raw_bytes, self.gzip_bytes, self.closed = {}, 0, 0, False

    def _key(self, key):
        if type(key) is not str or not key.startswith(self.prefix): _fail()
        suffix = key[len(self.prefix):]
        if suffix != 'index.json':
            match = re.fullmatch(r'chunks([0-9]{5})\.json', suffix)
            if match is None or int(match.group(1)) >= 1024: _fail()
        return key + '.gz'

    def contains_key(self, key):
        physical = self._key(key)
        plain, zipped = self.native.contains_key(key), self.native.contains_key(physical)
        if type(plain) is not bool or type(zipped) is not bool: _fail()
        return plain or zipped

    def read(self, key):
        self._key(key)
        if key not in self.descriptors: _fail()
        row = self.descriptors[key]
        raw = decode_gzip(self.native.read_bytes(row['stored_key']), plain_bytes=row['plain_bytes'], plain_sha256=row['plain_sha256'],
            gzip_bytes=row['gzip_bytes'], gzip_sha256=row['gzip_sha256'], maximum=MAX_CHUNK)
        try: return raw.decode('utf-8')
        except UnicodeError: _fail()

    @property
    def storage_declaration(self):
        return {'schema': 'tpr-ext26-gzip-audit-storage-v1', 'encoding': 'gzip', 'gzip_level': 9, 'gzip_mtime': 0,
            'prefix': self.prefix, 'binding': dict(self.binding), 'logical_bytes': self.raw_bytes,
            'stored_bytes': self.gzip_bytes, 'objects': [dict(self.descriptors[key]) for key in sorted(self.descriptors)],
            'cloud_only_readback': True, 'external_export': False, 'raw_journal_records_dropped': False}

    def _sidecar(self):
        raw = canonical(self.storage_declaration)
        if len(raw) > MAX_METADATA: _fail()
        encoded = encode_gzip(raw, maximum=MAX_METADATA)
        key = self.prefix + 'storage.json.gz'
        if self.native.contains_key(key) is not False: _fail()
        if self.native.save_bytes(key, encoded) is not True: _fail()
        if decode_gzip(self.native.read_bytes(key), plain_bytes=len(raw), plain_sha256=sha256(raw),
            gzip_bytes=len(encoded), gzip_sha256=sha256(encoded), maximum=MAX_METADATA) != raw: _fail()

    def _index(self, raw):
        index = _json(raw, MAX_CHUNK)
        _keys(index, {'schema', *self.binding, 'prefix', 'record_count', 'record_kind_counts', 'chunks', 'canonical_admission'})
        if (index['schema'] != 'tpr-ext26-private-evidence-index-v1' or index['prefix'] != self.prefix
                or index['canonical_admission'] is not False
                or any(index[key] != value for key, value in self.binding.items())
                or type(index['chunks']) is not list or len(index['chunks']) != len(self.descriptors)
                or type(index['record_kind_counts']) is not dict): _fail()
        count = 0
        for number, row in enumerate(index['chunks']):
            _keys(row, ('key', 'sha256', 'bytes', 'record_count'))
            key = self.prefix + f'chunks{number:05d}.json'
            descriptor = self.descriptors[key]
            if row['key'] != key or row['sha256'] != descriptor['plain_sha256'] or row['bytes'] != descriptor['plain_bytes']: _fail()
            count += _positive(row['record_count'], 1000000)
        if _positive(index['record_count'], 1000000) != count: _fail()
        total = 0
        for key, value in index['record_kind_counts'].items():
            if type(key) is not str or re.fullmatch(r'[A-Z_]{1,64}', key) is None or type(value) is not int or not 0 <= value <= 1000000: _fail()
            total += value
        if total != count: _fail()

    def save(self, key, text):
        physical = self._key(key)
        if self.closed or type(text) is not str or key in self.descriptors or self.contains_key(key): _fail()
        raw = text.encode('utf-8')
        if not 0 < len(raw) <= MAX_CHUNK or len(self.descriptors) >= 1025 or self.raw_bytes + len(raw) > MAX_JOURNAL + MAX_CHUNK: _fail()
        encoded = encode_gzip(raw, maximum=MAX_CHUNK)
        if self.gzip_bytes + len(encoded) > MAX_JOURNAL: _fail()
        if key == self.prefix + 'index.json':
            if not self.descriptors or set(self.descriptors) != {self.prefix + f'chunks{index:05d}.json' for index in range(len(self.descriptors))}: _fail()
            self._index(raw)
        if self.native.save_bytes(physical, encoded) is not True: _fail()
        row = {'logical_key': key, 'stored_key': physical, 'plain_sha256': sha256(raw), 'plain_bytes': len(raw),
            'gzip_sha256': sha256(encoded), 'gzip_bytes': len(encoded)}
        self.descriptors[key] = row; self.raw_bytes += len(raw); self.gzip_bytes += len(encoded)
        if self.read(key) != text: _fail()
        if key == self.prefix + 'index.json': self._sidecar(); self.closed = True
        return True
