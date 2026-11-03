"""Pure original-catalog ownership diagnosis; no I/O or identity admission.

Physical rows, table scopes and exact identity tuples remain distinct.  A
cross-table match is an observation, never permission to replace a binding.
"""
from collections import Counter, defaultdict
import csv
from datetime import date
import hashlib
import io
import json
import math
from pathlib import PurePosixPath
import re
import stat
import time
import zipfile

SCHEMA='arv2-r336-original-cross-table-identity-v1'
MANIFEST_PIN={'byte_count':5998,'sha256':'94251ffdf0529b118ff331b98c4a144d97bc734380d7e7333f94045e4aa6f09b'}
ARCHIVE_PIN={'byte_count':4937076,'sha256':'a7b129f159631ee50f1eefd2be8d4215c1c7818880570c0ad0a79c76c25e51bf'}
MEMBER_PIN={'byte_count':24939614,'sha256':'562577ea331805c4d50229b783e37216c9422c09d921b17dc950cf267ecf7697'}
HEADER_PIN={'byte_count':291,'sha256':'c9186ed191f4e51d5142287016dc99e3f80ecebed49aa63c3fa1ecf09e5d26f7'}
COLUMNS_SHA='1162197271c19a530482df5e6accf7e1fe22b14e14b668c29b978b4daae5d824'
ROW_STREAM_SHA='e22569077935c73678c1d389535f98d9bb9d07fd3c6765d2a9161f86d591d54b'
ROW_COUNT,FIELD_COUNT,MAX_PRIVATE=74150,28,16*1024*1024
TABLES=('fundamentals','stocks','funds','other')
TABLE_SCOPE={'SF1':'fundamentals','fundamentals':'fundamentals','SEP':'stocks','stocks':'stocks','SFP':'funds','funds':'funds'}
WHOLes=('f352b4d726b30dc4c0d9ac2b607d4c003dc8ebc4de2fc7442b97b6d8c3f1b986',
 'b0147c90e6741dc9b7697b82cc1d1dc459a0de4445d54c540cdfa7e9319fdce8',
 'c15d10303e03ea8eb0ce007bed1db63bfc626337dcda2bd94798ef09a5c058f7',
 '1e241c9aca6d79eef7020990ffa7bca14b8059a72e67bb42a767690ded624331',
 'b44a76e5db7cedcfc5ddfa6671b6cb28feb306d434d8d3cda3710fb7e3fd61c9')
GEOMETRY=((718,150),(417,87),(417,87),(432,90),(302,63))
REQUIRED=('table','ticker','permaticker','figi','cusips','exchange','category','currency','firstpricedate','lastpricedate','isdelisted','sector','industry')
CURRENT_FIELDS=('table','ticker','permaticker','exchange','isdelisted','category','cusips','figi','currency','firstpricedate','lastpricedate','lastupdated')
IDENTITY_FIELDS=('permaticker','figi','cusips')
LINKS=('original_permaticker','original_FIGI','original_complete_CUSIP','original_poison_CUSIP',
 'candidate_permaticker','candidate_FIGI','candidate_complete_CUSIP','candidate_poison_CUSIP')
PREDICATES=('same_permaticker','same_FIGI','same_ticker','same_currency','same_exchange','same_category',
 'original_CUSIP_subset','CUSIP_overlap','same_source_row','current_candidate_exact_metadata_projection')
FLAGS={key:False for key in ('provider_contact','QC_contact','Safari_access','USB_read','credential_access',
 'old_control_read','old_operation_replayed','original_identifiers_rewritten','alias_created','global_collision_cleared',
 'original_wrong_instrument_proven','later_mapping_drift_proven','historical_identity_proven','point_in_time_proven',
 'price_input_admitted','price_coverage_proven','source_assignment_changed','formal_forward_ready','paper_or_live_ready',
 'current_full_catalog_freshly_authenticated','historical_metadata_preservation_proven','licensed_rows_disclosed')}
FINITE=frozenset(('input','archive_pin','manifest','member','header','csv','row','row_stream','binding','cases','demand',
 'original_proof','catalog_bound','output','deadline','period','unknown'))

class Refused(ValueError): pass
def require(value,code):
    if not value: raise Refused(code)
def canonical(value): return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
def original_json_bytes(value):
    """Original capture/composer encoding, including its terminating LF."""
    return (json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n').encode('utf-8')
def sha(raw): return hashlib.sha256(raw).hexdigest()
def pin(raw): return {'byte_count':len(raw),'sha256':sha(raw)}
def finite(error):
    args=BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args)==1 and type(args[0]) is str and args[0] in FINITE else 'unknown'
def budget(deadline):
    require(type(deadline) in (int,float) and math.isfinite(deadline),'deadline')
    require(0<deadline-time.monotonic()<=300,'deadline')
def loads(raw):
    def pairs(items):
        result={}
        for key,value in items: require(key not in result,'input');result[key]=value
        return result
    def constant(_): raise Refused('input')
    try:return json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)
    except (ValueError,UnicodeError,RecursionError):raise Refused('input') from None
def row_bytes(row):
    require(type(row) is dict and len(row)==FIELD_COUNT and all(type(k) is str and 0<len(k)<=128 for k in row)
        and all(type(v) is str and len(v)<=8192 for v in row.values()),'row')
    raw=(json.dumps(row,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n').encode('utf-8')
    require(len(raw)<=65536,'row');return raw

def _syntax(value):
    """Return private tokens and a finite analysis; no substring extraction."""
    result = {'grammar': 'unknown', 'reason': 'field_type', 'lexical_token_count': None,
        'duplicate_token_count': None, 'new_parse_count': 0, 'accepted': False}
    if type(value) is not str: return (), result
    if not value:
        result.update(grammar='missing', reason='missing'); return (), result
    if len(value) > MAX_FIELD_BYTES:
        result['reason'] = 'field_bound'; return (), result
    if not value.isascii():
        result['reason'] = 'non_ascii'; return (), result
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        result['reason'] = 'control'; return (), result
    text = value.strip(' ')
    if not text:
        result.update(grammar='missing', reason='missing'); return (), result
    if ',' in text:
        grammar, parts = 'comma', tuple(part.strip(' ') for part in text.split(','))
    elif ' ' in text:
        grammar, parts = 'ascii_space', tuple(part for part in text.split(' ') if part)
    else:
        grammar, parts = 'single', (text,)
    result['grammar'] = grammar
    if any(not part for part in parts):
        result['reason'] = 'empty_token'; return (), result
    if any(re.fullmatch('[A-Za-z0-9]{9}', part) is None for part in parts):
        result['reason'] = 'token_shape'; return (), result
    tokens = tuple(part.upper() for part in parts)
    result.update(lexical_token_count=len(tokens), duplicate_token_count=len(tokens) - len(set(tokens)))
    if len(tokens) > MAX_TOKENS:
        result['reason'] = 'token_count'; return (), result
    if result['duplicate_token_count']:
        result['reason'] = 'duplicate'; return (), result
    result.update(reason='accepted', new_parse_count=len(tokens), accepted=True)
    return tuple(sorted(tokens)), result

MAX_FIELD_BYTES,MAX_TOKENS=2048,64
POISON=re.compile(r'(?<![A-Za-z0-9])[A-Z0-9]{9}(?![A-Za-z0-9])')
def vocabulary(value):
    require(type(value) is str,'row')
    tokens,analysis=_syntax(value)
    poison=() if analysis['accepted'] else tuple(sorted(set(POISON.findall(value.upper()))))
    return tokens,poison,analysis['reason']

def profile_record():
    return {'schema':SCHEMA,'purpose':'original_cross_table_ownership_not_binding_correction',
      'manifest_pin':MANIFEST_PIN,'archive_pin':ARCHIVE_PIN,'member_pin':MEMBER_PIN,'header_pin':HEADER_PIN,
      'ordered_columns_sha256':COLUMNS_SHA,'ordered_source_row_digests_sha256':ROW_STREAM_SHA,
      'original_row_count':ROW_COUNT,'field_count':FIELD_COUNT,'maximum_private_bytes':MAX_PRIVATE,
      'table_scope':TABLE_SCOPE,'physical_rows':'retained_separately_never_duplicate_exemption',
      'identity_tuple':['permaticker','figi','complete_CUSIP_tuple'],'matching':'exact_identifiers_no_names_or_ticker_alias_inference',
      'CUSIP_parser':'exact_AST_copy_of_pinned_syntax_v1_complete_token_parser_poison_refusal_only',
      'current_scope':'six_retained_candidate_rows_not_full_current_catalog','selected_binding_count':5,
      'original_hash':'UTF8_sorted_compact_JSON_ensure_ascii_false_WITH_LF',**FLAGS}

def decode_catalog(manifest_raw,marker_raw,archive_raw,*,deadline):
    budget(deadline)
    require(type(manifest_raw) is bytes and pin(manifest_raw)==MANIFEST_PIN and type(archive_raw) is bytes
      and pin(archive_raw)==ARCHIVE_PIN and marker_raw==(MANIFEST_PIN['sha256']+'\n').encode('ascii'),'archive_pin')
    manifest=loads(manifest_raw)
    try:
        require(type(manifest) is dict and type(manifest['archives']) is list and len(manifest['archives'])==3,'manifest')
        archive=manifest['archives'][0];member,=archive['members']
        require(archive['dataset']=='tickers' and archive['archive_file']=='01-tickers-years-full.zip'
          and archive['archive_byte_count']==ARCHIVE_PIN['byte_count'] and archive['archive_sha256']==ARCHIVE_PIN['sha256']
          and member['uncompressed_byte_count']==MEMBER_PIN['byte_count'] and member['content_sha256']==MEMBER_PIN['sha256']
          and member['row_count']==ROW_COUNT,'manifest')
        with zipfile.ZipFile(io.BytesIO(archive_raw)) as zipped:
            info,=zipped.infolist();path=PurePosixPath(info.filename);mode=info.external_attr>>16
            require(path.as_posix()==info.filename and not path.is_absolute() and all(part not in ('','.','..') for part in path.parts)
              and '\\' not in info.filename and not info.is_dir() and not info.flag_bits&1
              and (not stat.S_IFMT(mode) or stat.S_ISREG(mode)) and info.filename==member['name']
              and info.file_size==MEMBER_PIN['byte_count'] and info.compress_size==member['compressed_byte_count']
              and info.CRC==member['crc32'] and info.file_size<=max(1,info.compress_size)*250,'member')
            with zipped.open(info) as handle:payload=handle.read(MEMBER_PIN['byte_count']+1)
        require(pin(payload)==MEMBER_PIN,'member')
        first,separator,_=payload.partition(b'\n');require(separator==b'\n' and pin(first+separator)==HEADER_PIN,'header')
        reader=csv.reader(io.StringIO(payload.decode('utf-8-sig'),newline=''),strict=True);columns=next(reader)
        require(len(columns)==FIELD_COUNT==len(set(columns)) and all(key in columns for key in REQUIRED)
          and columns==member['columns'] and sha(canonical(columns))==COLUMNS_SHA,'header')
        rows=[];digests=[]
        for values in reader:
            budget(deadline);require(len(rows)<ROW_COUNT and len(values)==FIELD_COUNT,'csv')
            row=dict(zip(columns,values,strict=True));raw=row_bytes(row)
            require(all(row[name] for name in ('table','ticker','permaticker')),'row')
            rows.append(row);digests.append(sha(raw))
        require(len(rows)==ROW_COUNT and sha(original_json_bytes(digests))==ROW_STREAM_SHA,'row_stream')
        return rows
    except Refused:raise
    except (KeyError,TypeError,ValueError,UnicodeError,csv.Error,zipfile.BadZipFile,RuntimeError,EOFError,OSError):
        raise Refused('csv') from None

def _legacy_tokens(value):
    if not value:return ()
    parts=tuple(part.strip().upper() for part in value.split(','))
    return tuple(sorted(parts)) if all(re.fullmatch('[0-9A-Z]{9}',part) for part in parts) and len(parts)==len(set(parts)) else ()

def _component(prefix,value):
    require(type(value) is str and value and value==value.strip(),'original_proof')
    return prefix+'-'+value if re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]{0,127}',value) else prefix+'-'+sha(
      (json.dumps({'kind':prefix,'value':value},sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode())[:24]

def original_proof(binding,original):
    raw=row_bytes(original);require(sha(raw)==binding['source_row_sha256'] and original['table']=='SF1','original_proof')
    require(original['category'].casefold() in ('domestic common stock','domestic common stock primary class','domestic common stock secondary class')
      and all(original[key] and original[key]==original[key].strip() for key in ('ticker','permaticker','figi','sector','industry','exchange')),'original_proof')
    mic={'AMEX':'XASE','NASDAQ':'XNAS','NYSE':'XNYS','NYSE AMERICAN':'XASE','NYSE MKT':'XASE','NYSEAMERICAN':'XASE','NYSEMKT':'XASE'}.get(original['exchange'].upper())
    require(mic is not None and re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]{0,31}',original['ticker']),'original_proof')
    first,last=original['firstpricedate'],original['lastpricedate'] or None
    try:require(date.fromisoformat(first).isoformat()==first and (last is None or date.fromisoformat(last).isoformat()==last and first<=last),'original_proof')
    except ValueError:raise Refused('original_proof') from None
    evidence={'permaticker':original['permaticker'],'composite_figi':original['figi'],'source_table':original['table'],
      'ticker':original['ticker'],'cusips':list(_legacy_tokens(original['cusips'])),'exchange':original['exchange'],'exchange_mic':mic,
      'firstpricedate':first,'lastpricedate':last,'source_row_sha256':sha(raw),
      'availability_semantics':'capture_time_current_snapshot_active_and_delisted_not_point_in_time'}
    evidence_sha=sha((json.dumps(evidence,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode('utf-8'))
    expected={'security_id':_component('sharadar-composite-figi',original['figi']),
      'issuer_id':_component('sharadar-permaticker',original['permaticker']),'composite_figi':original['figi'],
      'listing_id':'sharadar-listing-'+evidence_sha[:24],'diagnostic_current_ticker':original['ticker'],
      'diagnostic_exchange_mic':mic,'identity_evidence_sha256':evidence_sha}
    require(all(binding.get(key)==value for key,value in expected.items()),'original_proof')

def compare(row,original,candidates):
    tokens,_,_=vocabulary(row['cusips']);old,_,_=vocabulary(original['cusips'])
    return {'same_permaticker':row['permaticker']==original['permaticker'],'same_FIGI':row['figi']==original['figi'],
      'same_ticker':row['ticker']==original['ticker'],'same_currency':row['currency']==original['currency'],
      'same_exchange':row['exchange']==original['exchange'],'same_category':row['category']==original['category'],
      'original_CUSIP_subset':bool(old) and set(old)<=set(tokens),'CUSIP_overlap':bool(set(old)&set(tokens)),
      'same_source_row':row==original,'current_candidate_exact_metadata_projection':any(
       all(row.get(key)==candidate[key] for key in CURRENT_FIELDS) for candidate in candidates)}

def inspect(rows,identity,*,deadline):
    """Caller authenticates all four DATA pins before this supplied-object API."""
    require(type(rows) is list and len(rows)<=ROW_COUNT and rows and type(identity) is dict
      and identity.get('schema')=='arv2-r327-W5-identity-necessary-demand-i-v1-private'
      and type(identity.get('cases')) is list and len(identity['cases'])==5,'input')
    records=[];indexes={key:defaultdict(set) for key in ('permaticker','figi','tokens','poison')};by_digest=defaultdict(list)
    for ordinal,row in enumerate(rows):
        budget(deadline);raw=row_bytes(row);require(all(key in row for key in REQUIRED),'row')
        tokens,poison,state=vocabulary(row['cusips']);scope=TABLE_SCOPE.get(row['table'],'other')
        records.append({'row':row,'scope':scope,'tokens':tokens,'poison':poison,'state':state})
        by_digest[sha(raw)].append(ordinal)
        for field in ('permaticker','figi'):
            if row[field]:indexes[field][row[field]].add(ordinal)
        for token in tokens:indexes['tokens'][token].add(ordinal)
        for token in poison:indexes['poison'][token].add(ordinal)
    public=[];private=[];current_total=0
    for ordinal,case in enumerate(identity['cases']):
        budget(deadline);require(type(case) is dict and case.get('case_ordinal')==ordinal and type(case.get('case_ordinal')) is int,'cases')
        item=case['original_case']['aa_stock'];binding=item['binding'];original=item['original_row'];candidates=item['current_candidate_rows']
        require(sha(canonical(binding))==WHOLes[ordinal]==case['whole_binding_sha256'],'binding')
        original_proof(binding,original);matches=by_digest.get(binding['source_row_sha256'],[])
        require(matches and all(rows[index]==original for index in matches),'original_proof')
        require(type(candidates) is list and len(candidates)==(2 if ordinal==0 else 1)
          and all(type(row) is dict and set(row)==set(CURRENT_FIELDS) and all(type(v) is str and len(v)<=8192 for v in row.values()) for row in candidates),'cases')
        current_total+=len(candidates);old,old_poison,_=vocabulary(original['cusips']);links={key:set() for key in LINKS}
        for row,prefix in ((original,'original'),*((row,'candidate') for row in candidates)):
            links[prefix+'_permaticker'].update(indexes['permaticker'].get(row['permaticker'],()))
            links[prefix+'_FIGI'].update(indexes['figi'].get(row['figi'],()))
            complete,poison,_=vocabulary(row['cusips'])
            for token in complete:
                links[prefix+'_complete_CUSIP'].update(indexes['tokens'].get(token,()))
                links[prefix+'_poison_CUSIP'].update(indexes['poison'].get(token,()))
            # Refusal-only tokens from malformed claims can detect overlap but
            # NEVER become accepted complete vocabulary or a matching locator.
            for token in poison:
                links[prefix+'_poison_CUSIP'].update(indexes['tokens'].get(token,()))
                links[prefix+'_poison_CUSIP'].update(indexes['poison'].get(token,()))
        owners=set().union(*links.values());require(len(owners)<=ROW_COUNT,'catalog_bound');private_rows=[];scope_summary=[]
        for scope in TABLES:
            selected=[index for index in sorted(owners) if records[index]['scope']==scope]
            tuples={(records[index]['row']['permaticker'],records[index]['row']['figi'],records[index]['tokens']) for index in selected}
            predicates={key:{'true':0,'false':0} for key in PREDICATES}
            for index in selected:
                flags=compare(records[index]['row'],original,candidates)
                for key,state in flags.items():predicates[key]['true' if state else 'false']+=1
                private_rows.append({'row_ordinal':index,'scope':scope,'row':dict(rows[index]),'CUSIP_state':records[index]['state'],
                  'complete_CUSIPs':list(records[index]['tokens']),'poison_CUSIPs':list(records[index]['poison']),
                  'links':{key:index in ownerset for key,ownerset in links.items()},'predicates':flags})
            permas={records[index]['row']['permaticker'] for index in selected};figis={records[index]['row']['figi'] for index in selected}
            candidate_matrices=[]
            for candidate_ordinal,candidate in enumerate(candidates):
                candidate_tokens,_,_=vocabulary(candidate['cusips']);counts=Counter()
                for index in selected:
                    record=records[index];row=record['row'];same_perma=row['permaticker']==candidate['permaticker']
                    same_figi=bool(candidate['figi']) and row['figi']==candidate['figi']
                    same_tokens=bool(candidate_tokens) and candidate_tokens==record['tokens'] and record['state']=='accepted'
                    counts['same_permaticker']+=same_perma;counts['same_nonempty_FIGI']+=same_figi
                    counts['same_complete_CUSIP_tuple']+=same_tokens
                    counts['same_permaticker_FIGI_CUSIP_tuple']+=same_perma and same_figi and same_tokens
                candidate_matrices.append({'candidate_ordinal':candidate_ordinal,**{key:counts[key] for key in
                  ('same_permaticker','same_nonempty_FIGI','same_complete_CUSIP_tuple','same_permaticker_FIGI_CUSIP_tuple')}})
            scope_summary.append({'table_scope':scope,'physical_row_count':len(selected),'unique_identity_tuple_count':len(tuples),
              'unique_permaticker_count':len(permas),'unique_nonempty_FIGI_count':len(figis-{''}),
              'missing_FIGI_row_count':sum(not records[index]['row']['figi'] for index in selected),
              'unique_complete_CUSIP_tuple_count':len({records[index]['tokens'] for index in selected}),
              'permaticker_consensus':len(permas)==1,'nonnull_FIGI_consensus':len(figis)==1 and '' not in figis,
              'complete_CUSIP_tuple_consensus':len(selected)>0 and len({records[index]['tokens'] for index in selected})==1
                and all(records[index]['state']=='accepted' for index in selected),
              'poison_owner_count':sum(bool(records[index]['poison']) for index in selected),
              'malformed_or_missing_vocabulary_row_count':sum(records[index]['state']!='accepted' for index in selected),
              'link_counts':{key:sum(index in ownerset for index in selected) for key,ownerset in links.items()},
              'predicate_counts':predicates,'current_candidate_matrices':candidate_matrices})
        public.append({'case_ordinal':ordinal,'original_SF1_row_reproduced':True,'current_candidate_count':len(candidates),
          'original_SF1_physical_match_count':len(matches),
          'related_original_physical_row_count':len(owners),'table_scopes':scope_summary,'identity_admitted':False})
        private.append({'case_ordinal':ordinal,'whole_binding_sha256':WHOLes[ordinal],'binding':binding,'original_row':original,
          'current_candidate_rows':candidates,'original_catalog_owners':private_rows,'original_required_demand':case['demand'],**FLAGS})
    require(current_total==6,'cases')
    distinct=len(by_digest)
    summary={'schema':SCHEMA,'original_catalog_row_count':len(rows),'original_distinct_full_row_count':distinct,
      'original_repeated_full_row_count':len(rows)-distinct,'selected_case_count':5,'current_candidate_count':6,'cases':public,**FLAGS}
    detail={'schema':SCHEMA+'-private','cases':private,'inspection':summary,**FLAGS}
    require(len(canonical(detail))<=MAX_PRIVATE,'output');validate_summary(summary);return summary,detail

def validate_summary(value):
    require(type(value) is dict and set(value)=={'schema','original_catalog_row_count','original_distinct_full_row_count',
      'original_repeated_full_row_count','selected_case_count','current_candidate_count','cases',*FLAGS}
      and value['schema']==SCHEMA and type(value['original_catalog_row_count']) is int and 0<value['original_catalog_row_count']<=ROW_COUNT
      and type(value['selected_case_count']) is int and value['selected_case_count']==5 and type(value['current_candidate_count']) is int
      and value['current_candidate_count']==6 and all(value[key] is False for key in FLAGS)
      and type(value['cases']) is list and len(value['cases'])==5,'output')
    require(type(value['original_distinct_full_row_count']) is int and 0<value['original_distinct_full_row_count']<=value['original_catalog_row_count']
      and type(value['original_repeated_full_row_count']) is int
      and value['original_repeated_full_row_count']==value['original_catalog_row_count']-value['original_distinct_full_row_count'],'output')
    for ordinal,case in enumerate(value['cases']):
        require(type(case) is dict and set(case)=={'case_ordinal','original_SF1_row_reproduced','original_SF1_physical_match_count',
          'current_candidate_count','related_original_physical_row_count','table_scopes','identity_admitted'}
          and type(case['case_ordinal']) is int and case['case_ordinal']==ordinal and case['original_SF1_row_reproduced'] is True
          and type(case['current_candidate_count']) is int and case['current_candidate_count']==(2 if ordinal==0 else 1)
          and case['identity_admitted'] is False and type(case['related_original_physical_row_count']) is int
          and type(case['original_SF1_physical_match_count']) is int and 1<=case['original_SF1_physical_match_count']<=case['related_original_physical_row_count']
          and 1<=case['related_original_physical_row_count']<=value['original_catalog_row_count']
          and type(case['table_scopes']) is list and len(case['table_scopes'])==4,'output')
        for scope,item in zip(TABLES,case['table_scopes'],strict=True):
            keys={'table_scope','physical_row_count','unique_identity_tuple_count','unique_permaticker_count','unique_nonempty_FIGI_count',
              'unique_complete_CUSIP_tuple_count','permaticker_consensus','nonnull_FIGI_consensus','complete_CUSIP_tuple_consensus',
              'missing_FIGI_row_count','poison_owner_count','malformed_or_missing_vocabulary_row_count','link_counts','predicate_counts','current_candidate_matrices'}
            require(type(item) is dict and set(item)==keys and item['table_scope']==scope,'output');n=item['physical_row_count']
            require(type(n) is int and 0<=n<=value['original_catalog_row_count'],'output')
            for key in ('unique_identity_tuple_count','unique_permaticker_count','unique_nonempty_FIGI_count','unique_complete_CUSIP_tuple_count',
                        'missing_FIGI_row_count','poison_owner_count','malformed_or_missing_vocabulary_row_count'):
                require(type(item[key]) is int and 0<=item[key]<=n,'output')
            require(item['permaticker_consensus'] is (item['unique_permaticker_count']==1)
              and item['nonnull_FIGI_consensus'] is (item['unique_nonempty_FIGI_count']==1 and item['missing_FIGI_row_count']==0)
              and item['complete_CUSIP_tuple_consensus'] is (n>0 and item['unique_complete_CUSIP_tuple_count']==1 and item['malformed_or_missing_vocabulary_row_count']==0)
              and item['poison_owner_count']<=item['malformed_or_missing_vocabulary_row_count']
              and item['unique_identity_tuple_count']>=max(item[key] for key in ('unique_permaticker_count','unique_nonempty_FIGI_count','unique_complete_CUSIP_tuple_count')),'output')
            require(type(item['link_counts']) is dict and set(item['link_counts'])==set(LINKS)
              and all(type(count) is int and 0<=count<=n for count in item['link_counts'].values()),'output')
            require(type(item['predicate_counts']) is dict and set(item['predicate_counts'])==set(PREDICATES),'output')
            for counts in item['predicate_counts'].values():require(type(counts) is dict and set(counts)=={'true','false'}
              and all(type(count) is int and 0<=count<=n for count in counts.values()) and sum(counts.values())==n,'output')
            require(item['predicate_counts']['same_FIGI']['true']==item['link_counts']['original_FIGI']
              and item['predicate_counts']['same_permaticker']['true']==item['link_counts']['original_permaticker']
              and n<=sum(item['link_counts'].values())
              and item['predicate_counts']['original_CUSIP_subset']['true']<=item['predicate_counts']['CUSIP_overlap']['true'],'output')
            require(type(item['current_candidate_matrices']) is list and len(item['current_candidate_matrices'])==case['current_candidate_count'],'output')
            for index,matrix in enumerate(item['current_candidate_matrices']):
                keys={'candidate_ordinal','same_permaticker','same_nonempty_FIGI','same_complete_CUSIP_tuple','same_permaticker_FIGI_CUSIP_tuple'}
                require(type(matrix) is dict and set(matrix)==keys and type(matrix['candidate_ordinal']) is int and matrix['candidate_ordinal']==index
                  and all(type(matrix[key]) is int and 0<=matrix[key]<=n for key in keys-{'candidate_ordinal'})
                  and matrix['same_permaticker_FIGI_CUSIP_tuple']<=min(matrix[key] for key in keys-{'candidate_ordinal','same_permaticker_FIGI_CUSIP_tuple'}),'output')
            for matrix_key,link_key in (('same_permaticker','candidate_permaticker'),('same_nonempty_FIGI','candidate_FIGI')):
                values=[row[matrix_key] for row in item['current_candidate_matrices']]
                require(max(values)<=item['link_counts'][link_key]<=min(n,sum(values)),'output')
            require(all(row['same_complete_CUSIP_tuple']<=item['link_counts']['candidate_complete_CUSIP']
              for row in item['current_candidate_matrices']),'output')
        require(sum(item['physical_row_count'] for item in case['table_scopes'])==case['related_original_physical_row_count'],'output')
        require(sum(item['predicate_counts']['same_source_row']['true'] for item in case['table_scopes'])==case['original_SF1_physical_match_count']
          and case['table_scopes'][0]['predicate_counts']['same_source_row']['true']==case['original_SF1_physical_match_count'],'output')
    return value

EXPECTED_DEMAND=dict(zip(WHOLes,(("2023-12-01",718,150),("2025-02-14",417,87),("2025-02-14",417,87),("2025-01-24",432,90),("2025-08-01",302,63)),strict=True))
PERIOD_SHA256='88113155d49f74e00a89ba743aaa314d718cfd0d29b017ac501058460fe5d11a'


def _sessions(values, *, count=None):
    require(type(values) is list and (count is None or len(values) == count)
        and all(type(value) is str and len(value) == 10 for value in values), 'period')
    try: require(all(date.fromisoformat(value).isoformat() == value for value in values), 'period')
    except ValueError: raise Refused('period') from None
    require(values == sorted(set(values)), 'period'); return tuple(values)

def demands(record, expected_summary):
    require(type(record) is dict and set(record) == {'schema', 'source_fingerprint', 'period', 'stock_demand',
        'fund_demand', 'cases', 'metadata_receipt'} and record['schema'] == 'arv2-r327-W5-identity-necessary-demand-i-v1-private'
        and record['source_fingerprint'] == expected_summary['source_fingerprint'], 'input')
    period = record['period']; seed = dict(period); declared = seed.pop('period_sha256')
    require(declared == PERIOD_SHA256 == sha(canonical(seed)), 'period')
    axis = _sessions(period['reference_and_valuation_price_sessions'], count=1243)
    decisions = _sessions(period['decision_sessions'], count=259)
    require(axis[0] == '2021-10-29' and axis[-1] == '2026-10-13'
        and sha(canonical(list(axis))) == period['reference_and_valuation_price_sessions_sha256'], 'period')
    require(type(record['stock_demand']) is list and len(record['stock_demand']) == 6151
        and type(record['fund_demand']) is list and len(record['fund_demand']) == 8
        and type(record['cases']) is list and len(record['cases']) == 5, 'demand')
    positions = {session: index for index, session in enumerate(axis)}; result = []; seen = set()
    for case in record['cases']:
        item = case['original_case']['aa_stock']; row = item['binding']; demand = case['demand']
        whole = sha(canonical(row)); seen.add(whole)
        require(type(case['case_ordinal']) is int and 0 <= case['case_ordinal'] < 5
            and whole == case['whole_binding_sha256'] == demand['whole_binding_sha256'] and whole in EXPECTED_DEMAND
            and demand == record['stock_demand'][item['binding_ordinal']] and demand['potential'] is True
            and demand['source_role'] == 'pending_native_original_identity_source'
            and demand['membership_or_binding_end_used_as_price_end'] is False, 'demand')
        first, required_count, ref_count = EXPECTED_DEMAND[whole]
        required = tuple(session for session in axis if first <= session <= axis[-1])
        eligible = tuple(session for session in decisions if demand['first_eligible_decision'] <= session <= demand['last_eligible_decision'])
        require(demand['required_price_first'] == first and demand['required_price_last'] == axis[-1]
            and len(required) == required_count and len(eligible) == ref_count == demand['eligible_decision_count']
            and sha(canonical(list(eligible))) == demand['eligible_decisions_sha256']
            and all(session in positions and positions[session] > 0 for session in eligible), 'demand')
        references = tuple(axis[positions[session] - 1] for session in eligible)
        ticker = row['diagnostic_current_ticker']
        require(type(ticker) is str and re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,19}', ticker)
            and not ticker.endswith('-DELISTED') and '..' not in ticker, 'demand')
        result.append({'case_ordinal': case['case_ordinal'], 'whole_binding_sha256': whole,
            'ticker': ticker, 'required': required, 'references': references})
    require(seen == set(EXPECTED_DEMAND) and sorted(row['case_ordinal'] for row in result) == list(range(5)), 'demand')
    return result, axis
