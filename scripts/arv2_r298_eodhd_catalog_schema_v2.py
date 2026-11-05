"""Pure full-catalog representation; display payloads are opaque private data.

Name/Country are never identity, routing, display or log outputs. Exact JSON
strings, including escaped controls and surrogate codepoints, remain private
and unchanged. All rows are preserved; representation is not route eligibility.
"""
from decimal import Decimal
import hashlib
import json
import re

SCHEMA='arv2-r298-EODHD-private-catalog-representation-v2'
FIELDS=('Code','Name','Country','Exchange','Currency','Type','Isin')
MAX_RAW_BYTES,MAX_ROWS=32*1024*1024,100000
MAX_DISPLAY_CHARS,MAX_DISPLAY_JSON_BYTES=4096,16384
LABEL_BOUNDS={'Currency':16,'Type':64,'Exchange':64}
FALSE_FLAGS={'route_eligibility_proven':False,'identity_crosswalk_admitted':False,'price_input_admitted':False,
    'permanent_security_master_proven':False,'point_in_time_proven':False,'formal_forward_ready':False,
    'paper_or_live_ready':False,'display_used_for_identity_or_routing':False,'display_payload_exposed':False,
    'licensed_rows_disclosed':False,'operation_granted':False}
FINITE=frozenset(('bytes','json','rows','fields','Code','label','Isin','display_bound','summary'))


class Refused(ValueError):pass


def require(value,code):
    if not value:raise Refused(code)


def finite(error):
    args=BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args)==1 and type(args[0]) is str and args[0] in FINITE else 'summary'


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')


def sha(raw):return hashlib.sha256(raw).hexdigest()


def profile_record():
    return {'schema':SCHEMA,'fields':list(FIELDS),'maximum_raw_bytes':MAX_RAW_BYTES,'maximum_rows':MAX_ROWS,
        'Code':'nonempty_printable_ASCII_max64_no_normalization_no_request_grammar_authority',
        'nullable_ASCII_label_bounds':LABEL_BOUNDS,'label_empty_strings_preserved':True,
        'Isin':'None_or_printable_ASCII_max32_empty_and_malformed_placeholders_preserved_no_identifier_acceptance',
        'display_fields':['Name','Country'],'display_types':['string','null'],
        'maximum_display_characters':MAX_DISPLAY_CHARS,'maximum_display_serialized_UTF8_JSON_bytes':MAX_DISPLAY_JSON_BYTES,
        'display_serialization':'ensure_ascii_true_includes_JSON_quotes_safe_for_surrogate_codepoints',
        'opaque_display_control_format_unassigned_surrogate_payloads_preserved':True,
        'display_normalization_repair_replacement_or_presence_gate':False,
        'all_rows_original_order_duplicates_and_nulls_preserved':True,'class_or_venue_filter_or_price_selection':False,
        'strict_route_preparation_independent_from_catalog_representation':True,
        'observe_raw_outputs_only_counts_types_and_digests':True,'no_I_O_or_operational_entrypoint':True,**FALSE_FLAGS}


def _ascii(value,maximum,*,nonempty):
    return (type(value) is str and (not nonempty or len(value)>0) and len(value)<=maximum
        and all(32<=ord(char)<=126 for char in value))


def _display(value):
    require(value is None or type(value) is str,'display_bound')
    if value is None:return
    require(len(value)<=MAX_DISPLAY_CHARS,'display_bound')
    require(len(canonical(value))<=MAX_DISPLAY_JSON_BYTES,'display_bound')


def checked_symbol_rows(raw):
    """All checked rows are private, exact and non-admitted caller data."""
    require(type(raw) is bytes and 0<len(raw)<=MAX_RAW_BYTES,'bytes')
    def pairs(items):
        value={}
        for key,child in items:require(key not in value,'json');value[key]=child
        return value
    def number(text):
        require(len(text)<=64,'json')
        try:return Decimal(text)
        except ArithmeticError:raise Refused('json') from None
    try:
        rows=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_int=number,parse_float=number,
            parse_constant=lambda _:(_ for _ in ()).throw(Refused('json')))
    except (ValueError,UnicodeError,RecursionError):raise Refused('json') from None
    require(type(rows) is list and len(rows)<=MAX_ROWS,'rows')
    for row in rows:
        require(type(row) is dict and set(row)==set(FIELDS),'fields')
        require(_ascii(row['Code'],64,nonempty=True),'Code')
        for key,maximum in LABEL_BOUNDS.items():require(row[key] is None or _ascii(row[key],maximum,nonempty=False),'label')
        isin=row['Isin'];require(isin is None or _ascii(isin,32,nonempty=False),'Isin')
        for key in ('Name','Country'):_display(row[key])
    return tuple(rows)


def observe_raw(raw):
    """Closed counts/hashes only; no values or raw display payload leave here."""
    rows=checked_symbol_rows(raw);counts={field:{'null':0,'empty_string':0,'nonempty_string':0} for field in FIELDS}
    digest=hashlib.sha256()
    for row in rows:
        digest.update(canonical(row)+bytes([10]))
        for field in FIELDS:
            value=row[field];counts[field]['null' if value is None else 'empty_string' if value=='' else 'nonempty_string']+=1
    result={'schema':SCHEMA+'-observation','raw_pin':{'byte_count':len(raw),'sha256':sha(raw)},'row_count':len(rows),
        'ordered_private_records_sha256':digest.hexdigest(),'field_availability_types':counts,**FALSE_FLAGS}
    validate_observation(result);return result


def validate_observation(value):
    require(type(value) is dict and set(value)=={'schema','raw_pin','row_count','ordered_private_records_sha256',
        'field_availability_types',*FALSE_FLAGS} and value['schema']==SCHEMA+'-observation'
        and type(value['raw_pin']) is dict and set(value['raw_pin'])=={'byte_count','sha256'}
        and type(value['raw_pin']['byte_count']) is int and 0<value['raw_pin']['byte_count']<=MAX_RAW_BYTES
        and type(value['row_count']) is int and 0<=value['row_count']<=MAX_ROWS
        and type(value['field_availability_types']) is dict and set(value['field_availability_types'])==set(FIELDS)
        and all(value[key] is False for key in FALSE_FLAGS),'summary')
    for digest in (value['raw_pin']['sha256'],value['ordered_private_records_sha256']):
        require(type(digest) is str and re.fullmatch('[0-9a-f]{64}',digest) is not None,'summary')
    for field,counts in value['field_availability_types'].items():
        require(type(counts) is dict and set(counts)=={'null','empty_string','nonempty_string'}
            and all(type(count) is int and count>=0 for count in counts.values())
            and sum(counts.values())==value['row_count'],'summary')
        if field=='Code':require(counts['nonempty_string']==value['row_count'],'summary')
    return value
