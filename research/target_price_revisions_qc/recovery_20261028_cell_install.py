"""Pure lexical replacement of one fresh, unexecuted owned placeholder cell.

No files, native tools, private stores or credentials are read here. The caller
must claim fresh private processing BEFORE supplying real retained archive
bytes, and a separate exact source-only update BEFORE writing the returned
notebook. This helper never uploads, executes, authenticates or grants effects.
"""
from __future__ import annotations

import hashlib
import json
import math
import re

PROJECT = 37650980
PLACEHOLDER = '# TPR-EXT26-RECOVERY-20261028-CELL002-PLACEHOLDER\n'
MAX_ARCHIVE = 1024 * 1024
MAX_CELL_SOURCE = 65536
MAX_FILES = 17
_HASH = re.compile(r'[0-9a-f]{64}')
_NAME = re.compile(r'[A-Za-z][A-Za-z0-9_.-]{0,79}')
_IDENTITY = re.compile(r'[A-Za-z0-9_.-]{1,200}')
_WHITESPACE = re.compile(r'[ \t\r\n]*')


class CellInstallRefusal(ValueError):
    """Fixed body-free refusal; never include supplied source/metadata."""


def _fail():
    raise CellInstallRefusal('fresh owned-cell source installation refused') from None


def _sha(raw): return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',',':'), ensure_ascii=True, allow_nan=False).encode()


def _pairs(items):
    result = {}
    for name, value in items:
        if name in result: _fail()
        result[name] = value
    return result


def _integer(text):
    if len(text) > 128: _fail()
    return int(text)


def _float(text):
    if len(text) > 128: _fail()
    value = float(text)
    if not math.isfinite(value): _fail()
    return value


def _constant(_text): _fail()


_DECODER = json.JSONDecoder(object_pairs_hook=_pairs, parse_int=_integer,
    parse_float=_float, parse_constant=_constant)


def _decode(text):
    if type(text) is not str or not 0 < len(text.encode('utf-8')) <= MAX_ARCHIVE: _fail()
    value, end = _DECODER.raw_decode(text, _WHITESPACE.match(text,0).end())
    if _WHITESPACE.match(text,end).end() != len(text): _fail()
    pending, nodes = [(value,0)], 0
    while pending:
        item, depth = pending.pop(); nodes += 1
        if nodes > 30000 or depth > 32: _fail()
        if type(item) is dict:
            if any(type(key) is not str or len(key) > 200 for key in item): _fail()
            pending.extend((child,depth+1) for child in item.values())
        elif type(item) is list:
            pending.extend((child,depth+1) for child in item)
    return value


def _skip(text, at): return _WHITESPACE.match(text,at).end()


def _members(text, start):
    """JSONDecoder token positions inside this exact object, not text search."""
    at = _skip(text,start)
    if text[at] != '{': _fail()
    at = _skip(text,at+1); result = {}
    if text[at] == '}': return result
    while True:
        key, at = _DECODER.raw_decode(text,at)
        if type(key) is not str or key in result: _fail()
        at = _skip(text,at)
        if text[at] != ':': _fail()
        begin = _skip(text,at+1)
        value, end = _DECODER.raw_decode(text,begin)
        result[key] = (value,begin,end)
        at = _skip(text,end)
        if text[at] == '}': return result
        if text[at] != ',': _fail()
        at = _skip(text,at+1)


def _elements(text, start):
    at = _skip(text,start)
    if text[at] != '[': _fail()
    at = _skip(text,at+1); result = []
    if text[at] == ']': return result
    while True:
        value, end = _DECODER.raw_decode(text,at)
        result.append((value,at,end))
        at = _skip(text,end)
        if text[at] == ']': return result
        if text[at] != ',': _fail()
        at = _skip(text,at+1)


def _source(value):
    if type(value) is str: text = value
    elif type(value) is list and all(type(part) is str for part in value): text = ''.join(value)
    else: _fail()
    if len(text.encode('utf-8')) > MAX_ARCHIVE: _fail()
    return text


def _notebook(text):
    value = _decode(text)
    if (type(value) is not dict or set(value) != {'cells','metadata','nbformat','nbformat_minor'}
            or type(value['cells']) is not list or not 1 <= len(value['cells']) <= 4096
            or type(value['metadata']) is not dict or type(value['nbformat']) is not int
            or value['nbformat'] != 4 or type(value['nbformat_minor']) is not int
            or not 0 <= value['nbformat_minor'] <= 99): _fail()
    rows, ids = [], set()
    for index, cell in enumerate(value['cells']):
        if type(cell) is not dict or not {'cell_type','metadata','source'} <= set(cell): _fail()
        if cell['cell_type'] not in {'code','markdown','raw'} or type(cell['metadata']) is not dict: _fail()
        identity = cell.get('id')
        if identity is not None:
            if (type(identity) is not str or re.fullmatch(r'[A-Za-z0-9_-]{1,64}',identity) is None
                    or identity in ids): _fail()
            ids.add(identity)
        source = _source(cell['source'])
        rows.append({'index':index, 'cell_id':identity, 'cell_type':cell['cell_type'],
            'source_bytes':len(source.encode()), 'source_sha256':_sha(source.encode())})
    return value, rows


def prepare_install(archive_raw, *, expected_archive_sha256, expected_archive_bytes,
                    expected_capture_operation, cell_source, expected_cell_sha256,
                    expected_project=PROJECT):
    """Return ``(inert_report, replacement_notebook_text)``; perform no I/O.

    Validate the exact bounded captured archive BEFORE parsing it. Locate one
    actual code cell, and replace ONLY its source JSON token using decoder
    positions. Every other notebook byte, cell and file source is preserved.
    """
    try:
        if (type(archive_raw) is not bytes or type(expected_archive_bytes) is not int
                or not 0 < expected_archive_bytes <= MAX_ARCHIVE or len(archive_raw) != expected_archive_bytes
                or type(expected_archive_sha256) is not str or _HASH.fullmatch(expected_archive_sha256) is None
                or _sha(archive_raw) != expected_archive_sha256
                or type(expected_project) is not int or expected_project != PROJECT
                or type(expected_capture_operation) is not str
                or _IDENTITY.fullmatch(expected_capture_operation) is None
                or type(cell_source) is not str or not 0 < len(cell_source.encode()) <= MAX_CELL_SOURCE
                or PLACEHOLDER in cell_source or '\x00' in cell_source
                or type(expected_cell_sha256) is not str or _HASH.fullmatch(expected_cell_sha256) is None
                or _sha(cell_source.encode()) != expected_cell_sha256): _fail()
        archive = _decode(archive_raw.decode('utf-8'))
        if (type(archive) is not dict or set(archive) != {'schema','operation_id','project_id','request_index','files'}
                or archive['schema'] != 'tpr-ext26-mia-all-source-v1'
                or archive['operation_id'] != expected_capture_operation
                or type(archive['project_id']) is not int or archive['project_id'] != PROJECT
                or type(archive['request_index']) is not int or archive['request_index'] not in (1,2)
                or type(archive['files']) is not dict or not 1 <= len(archive['files']) <= MAX_FILES): _fail()
        files = archive['files']; inventory = {}; notebooks = {}; candidates = []
        for name, text in files.items():
            if type(name) is not str or _NAME.fullmatch(name) is None or type(text) is not str: _fail()
            raw = text.encode('utf-8')
            if len(raw) > MAX_ARCHIVE: _fail()
            inventory[name] = {'bytes':len(raw),'sha256':_sha(raw)}
            if not name.endswith('.ipynb'): continue
            book, rows = _notebook(text); notebooks[name] = (book,rows)
            for index, cell in enumerate(book['cells']):
                source = _source(cell['source'])
                if source == cell_source: _fail()  # Never install a duplicate diagnostic.
                if 'TPR-EXT26-RECOVERY-20261028-CELL002-PLACEHOLDER' in source:
                    if source != PLACEHOLDER: _fail()
                    candidates.append((name,index,cell))
        if len(candidates) != 1: _fail()
        name,index,cell = candidates[0]
        if (cell['cell_type'] != 'code' or not {'cell_type','metadata','source','execution_count','outputs'} <= set(cell)
                or set(cell) - {'cell_type','metadata','source','execution_count','outputs','id'}
                or cell['execution_count'] is not None and (type(cell['execution_count']) is not int or cell['execution_count'] != 0)
                or type(cell['outputs']) is not list or cell['outputs'] != []): _fail()
        text = files[name]
        root_fields = _members(text,0)
        cell_tokens = _elements(text,root_fields['cells'][1])
        if len(cell_tokens) != len(notebooks[name][0]['cells']): _fail()
        actual_cell,start,_ = cell_tokens[index]
        if actual_cell != cell: _fail()
        source_value,begin,end = _members(text,start)['source']
        if source_value != cell['source'] or _source(source_value) != PLACEHOLDER: _fail()
        replacement_value = cell_source if type(source_value) is str else cell_source.splitlines(keepends=True)
        replacement_token = json.dumps(replacement_value,ensure_ascii=False,separators=(',',':'))
        replacement = text[:begin] + replacement_token + text[end:]
        after,after_rows = _notebook(replacement)
        before,old_rows = notebooks[name]
        expected_cell = dict(cell); expected_cell['source'] = replacement_value
        if after['cells'][index] != expected_cell: _fail()
        for number, (old,new) in enumerate(zip(before['cells'],after['cells'])):
            if number != index and old != new: _fail()
        after_inventory = dict(inventory)
        after_inventory[name] = {'bytes':len(replacement.encode()),'sha256':_sha(replacement.encode())}
        old_all = {file:rows for file,(_,rows) in notebooks.items()}
        new_all = dict(old_all); new_all[name] = after_rows
        report = {'schema':'tpr-ext26-owned-cell-install-20261028-v1','project_id':PROJECT,
            'capture_operation_id':expected_capture_operation,'capture_request_index':archive['request_index'],
            'archive_sha256':expected_archive_sha256,'archive_bytes':expected_archive_bytes,
            'notebook_name':name,'cell_index':index,'cell_id':cell.get('id'),
            'old_notebook':inventory[name],'new_notebook':after_inventory[name],
            'old_source_sha256':_sha(PLACEHOLDER.encode()),'new_source_sha256':expected_cell_sha256,
            'source_token_character_span':[begin,end],
            'old_source_token_sha256':_sha(text[begin:end].encode()),
            'new_source_token_sha256':_sha(replacement_token.encode()),
            'all_cell_sources_before':old_all,'all_cell_sources_after':new_all,
            'inventory_before':inventory,'inventory_after':after_inventory,
            'inventory_before_sha256':_sha(_canonical(inventory)),
            'inventory_after_sha256':_sha(_canonical(after_inventory)),
            'only_owned_source_token_changed':True,'other_file_bytes_changed':0,
            'other_cells_unchanged':True,'source_only_update':True,'cell_executed':False,
            'native_context_authenticated':False,'source_custody_authenticated':False,
            'effects_authorized':False,'new_jobs':0,'new_codex_attempts':0,'new_looks':0}
        return report, replacement
    except CellInstallRefusal:
        raise
    except Exception:
        _fail()
