"""Pure EODHD list schema with Unicode display fields and strict identifiers.

All checked rows remain private caller data, in their original order, including
duplicates, unknown types and unavailable ISINs. Display text is never an alias
or identity predicate. No normalization, I/O, contact or admission exists here.
"""
from decimal import Decimal
import hashlib
import json
import re
import unicodedata

from scripts import run_arv2_r298_eodhd_history_diagnostic as frozen

SCHEMA='arv2-r298-EODHD-symbol-list-schema-v1'
FIELDS=frozenset(('Code','Name','Country','Exchange','Currency','Type','Isin'))
MAX_RAW_BYTES,MAX_ROWS=32*1024*1024,100000
MAX_DISPLAY_CHARS,MAX_DISPLAY_UTF8=512,4096
IDENTIFIER_BOUNDS={'Code':64,'Currency':16,'Type':64,'Exchange':64}
MAX_ISIN_CHARS=32
FALSE_FLAGS={**frozen.FALSE_FLAGS,'permanent_security_master_proven':False,
    'metadata_display_used_for_identity':False,'independent_identity_review_completed':False}
FINITE=frozenset(('bytes','json','rows','fields','identifier','display','Isin','summary'))


class Refused(ValueError):pass


def require(value,code):
    if not value:raise Refused(code)


def finite(error):
    args=BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args)==1 and type(args[0]) is str and args[0] in FINITE else 'summary'


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')


def sha(raw):return hashlib.sha256(raw).hexdigest()


def pin(raw):return {'byte_count':len(raw),'sha256':sha(raw)}


def profile_record():
    return {'schema':SCHEMA,'fields':sorted(FIELDS),'maximum_raw_bytes':MAX_RAW_BYTES,'maximum_rows':MAX_ROWS,
        'identifier_bounds':IDENTIFIER_BOUNDS,'identifiers':'nonempty_printable_ASCII_no_normalization_no_route_grammar_authority',
        'Isin':'None_or_exact_ASCII_alphanumeric_string_0_to32_no_validity_or_identity_inference',
        'display_fields':['Name','Country'],'maximum_display_characters':MAX_DISPLAY_CHARS,
        'maximum_display_UTF8_bytes':MAX_DISPLAY_UTF8,'Unicode_category_C_refused':True,
        'display_empty_strings_permitted_without_identity_use':True,'Unicode_normalization_or_replacement':False,
        'all_rows_preserved_in_original_order':True,'deduplication_or_class_or_venue_filtering':False,
        'unknown_ASCII_types_and_unavailable_ISINs_preserved':True,
        'specific_SPY_predicates':['Code=SPY','Type=ETF','Currency=USD','Isin=US78462F1030'],
        'specific_SPY_history_field':'close','specific_SPY_expected_dates':list(frozen.DATES),
        'current_vendor_observation_not_permanent_or_historical_identity':True,
        'no_I_O_operational_entrypoint_or_contact':True,**FALSE_FLAGS}


def _display(value):
    require(type(value) is str and len(value)<=MAX_DISPLAY_CHARS,'display')
    require(all(not unicodedata.category(char).startswith('C') for char in value),'display')
    try:encoded=value.encode('utf-8')
    except UnicodeError:raise Refused('display') from None
    require(len(encoded)<=MAX_DISPLAY_UTF8,'display')


def checked_symbol_rows(raw):
    """Return every exact checked row; caller must keep returned values private."""
    require(type(raw) is bytes and 0<len(raw)<=MAX_RAW_BYTES,'bytes')
    def pairs(items):
        row={}
        for key,value in items:require(key not in row,'json');row[key]=value
        return row
    def number(text):
        require(len(text)<=64,'json')
        try:return Decimal(text)
        except ArithmeticError:raise Refused('json') from None
    try:
        rows=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_float=number,parse_int=number,
            parse_constant=lambda _:(_ for _ in ()).throw(Refused('json')))
    except (ValueError,UnicodeError,RecursionError):raise Refused('json') from None
    require(type(rows) is list and len(rows)<=MAX_ROWS,'rows')
    for row in rows:
        require(type(row) is dict and set(row)==FIELDS,'fields')
        for key,maximum in IDENTIFIER_BOUNDS.items():
            value=row[key]
            require(type(value) is str and 0<len(value)<=maximum and all(32<=ord(char)<=126 for char in value),'identifier')
        for key in ('Name','Country'):_display(row[key])
        isin=row['Isin'];require(isin is None or type(isin) is str and len(isin)<=MAX_ISIN_CHARS
            and re.fullmatch('[A-Za-z0-9]*',isin) is not None,'Isin')
    return tuple(rows)


def authenticate_retained_spy(metadata_raw,history_raw):
    """Qualified supplied-data observation only, never source/strategy admission.

    Frozen AU analysis is used only for its unchanged RAW-history predicates.
    Its ASCII display-name predicate is not called on supplied metadata.
    """
    require(type(metadata_raw) is bytes and 0<len(metadata_raw)<=frozen.MAX_BODY
        and type(history_raw) is bytes and 0<len(history_raw)<=frozen.MAX_BODY,'bytes')
    old=frozen.analyse(b'[]',history_raw)
    result={'schema':SCHEMA+'-SPY-observation','body_pins':[pin(metadata_raw),pin(history_raw)],
        'metadata_schema_valid':False,'metadata_row_count':None,'identity_matched':False,'identity_status':'unresolved',
        'metadata_row_sha256':None,**{key:old[key] for key in ('history_schema_valid','history_row_count',
            'positive_RAW_close_count','expected_date_coverage','observed_dates_sha256','RAW_close_series_sha256','date_window_sha256')},
        **FALSE_FLAGS}
    try:
        rows=checked_symbol_rows(metadata_raw)
        require(len(rows)==1,'rows');row=rows[0]
        matched=(row['Code']=='SPY' and row['Type']=='ETF' and row['Currency']=='USD' and row['Isin']=='US78462F1030')
        result.update(metadata_schema_valid=True,metadata_row_count=1,identity_matched=matched,
            identity_status='matched_current_vendor_fund' if matched else 'unresolved',metadata_row_sha256=sha(canonical(row)))
    except Refused:pass
    validate_spy_summary(result);return result


def validate_spy_summary(value):
    extra=set(FALSE_FLAGS)-set(frozen.FALSE_FLAGS)
    require(type(value) is dict and value.get('schema')==SCHEMA+'-SPY-observation'
        and all(value.get(key) is False for key in extra),'summary')
    projected={key:child for key,child in value.items() if key not in extra}
    projected['schema']=frozen.SCHEMA+'-authentication'
    try:frozen.validate_authentication(projected)
    except BaseException:raise Refused('summary') from None
    return value
