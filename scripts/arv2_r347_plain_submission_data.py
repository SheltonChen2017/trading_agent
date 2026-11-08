"""Fresh eight-leaf R346 DATA consumption for a separately frozen A4 caller.

Import and construction perform no filesystem operation. Only the six plain
payloads, source proposal and report are held; claim.json is unbound and never
opened or enumerated. Every external byte pin passes before any private JSON
is parsed. Immutable output is DATA, not processing, admission or launch
authority, and does not reset the three attempts recorded at preparation.
"""
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import time

from scripts import arv2_relocation_security as security
from scripts import prepare_arv2_r346_legacy_plain as preparation
from research.analyst_revisions_v2_qc import newrule_plain_input_runtime as plain

ROOT=Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
DIRECTORY=ROOT/'artifacts/analyst_revisions_v2/legacy_six_plain/R346-20261107-A'
FACT_PIN={'byte_count':43136,'sha256':'c7b22ba9e82558e23097d3d0802f864a87f6ae56d1ef9d415045f4d9cb68b4cd'}
SCHEMA='arv2-r347-fresh-plain-submission-DATA-v1'
OBJECT_NAMES=('evaluator-manifest.json','session_axis-0000.jsonl','memberships-0000.jsonl',
    'contributions-0000.jsonl','runtime_symbol_bindings-0000.jsonl','transport-manifest.json')
NAMES=(*OBJECT_NAMES,'source-proposal.json','report.json')
MAX_PROPOSAL,MAX_REPORT,MAX_OBJECT,MAX_TOTAL,MAX_SECONDS=8*1024*1024,64*1024,32*1024*1024,53*1024*1024,180
FIELDS=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns','st_flags')
FINITE=frozenset(('fact','output','scope','state','deadline','path','metadata','security','pin','report',
    'proposal','profile','sources','objects','parent','close','unknown'))


class Refused(ValueError):
    pass


def require(value,code):
    if not value:raise Refused(code)


def finite(error):
    args=BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args)==1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def canonical(value):
    try:return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
    except (TypeError,ValueError,UnicodeError,RecursionError):raise Refused('output') from None


def pin(raw):
    return {'byte_count':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def loads(raw,maximum,*,lf=False):
    require(type(raw) is bytes and 0<len(raw)<=maximum,'output')
    def pairs(items):
        value={}
        for key,item in items:
            require(key not in value,'output');value[key]=item
        return value
    try:
        value=json.loads(raw.decode('ascii'),object_pairs_hook=pairs,
            parse_constant=lambda _:(_ for _ in ()).throw(Refused('output')))
        require(canonical(value)+(b'\n' if lf else b'')==raw,'output');return value
    except Refused:raise
    except (ValueError,UnicodeError,RecursionError):raise Refused('output') from None


def budget(deadline):
    require(type(deadline) in (int,float) and math.isfinite(deadline)
        and 0<deadline-time.monotonic()<=MAX_SECONDS,'deadline')


def parse_fact(raw):
    """Pure exact public-fact check, not private filesystem authentication."""
    require(type(raw) is bytes and pin(raw)==FACT_PIN,'fact')
    fact=loads(raw,MAX_REPORT,lf=True)
    require(type(fact) is dict and set(fact)=={'schema','binding','observation','original_result'}
        and fact['schema']=='arv2-r346-local-preparation-result-fact-v1'
        and type(fact['observation']) is dict,'fact')
    observation=fact['observation']
    require(type(observation.get('child_actual_exit')) is int and observation['child_actual_exit']==0
        and type(observation.get('collector_actual_exit')) is int and observation['collector_actual_exit']==0
        and observation.get('original_stdout_validated') is True and observation.get('stderr_bytes')==0,'fact')
    try:
        checked=preparation.validate_original_stdout(canonical(fact['original_result'])+b'\n',
            actual_exit=observation['child_actual_exit'],expected_binding=fact['binding'])
    except preparation.Refused:raise Refused('fact') from None
    require(checked['original_stdout_validated'] is True
        and pin(canonical(fact['original_result'])+b'\n')==observation.get('child_stdout_pin'),'fact')
    return fact


def expected_files(fact):
    """Only eight externally pinned leaves; the preparation claim is excluded."""
    result={row['relative_path']:{key:row[key] for key in ('byte_count','sha256')}
        for row in fact['original_result']['report']['summary']['object_files']}
    result['source-proposal.json']=dict(fact['original_result']['report']['source_proposal_pin'])
    result['report.json']=dict(fact['original_result']['report_pin'])
    require(set(result)==set(NAMES),'fact')
    return result


@dataclass(frozen=True,slots=True)
class Candidate:
    candidate_id:str
    ar_percent:int
    profile_json:bytes=field(repr=False)
    sources:tuple=field(repr=False)
    bridge_record_json:bytes=field(repr=False)
    def cell_record(self):
        profile=loads(self.profile_json,MAX_REPORT)
        return {'candidate_id':self.candidate_id,'ar_percent':self.ar_percent,
            'profile_pin':pin(self.profile_json),
            'sources':[{'project_path':name,**pin(raw)} for name,raw in self.sources],
            'original_profile_sha256':profile['original_profile_sha256'],'profile':profile,
            'source_pairs':[[name,raw.decode('ascii')] for name,raw in self.sources]}


@dataclass(frozen=True,slots=True)
class Upload:
    descriptor_json:bytes=field(repr=False)
    object_store_key:str
    activation_manifest:bool
    payload:bytes=field(repr=False)


@dataclass(frozen=True,slots=True)
class Submission:
    candidate:Candidate
    uploads:tuple=field(repr=False)
    source_identity_json:bytes=field(repr=False)
    attempt_state_at_preparation_json:bytes=field(repr=False)
    @property
    def candidates(self):return (self.candidate,)


def validate_supplied(files,*,fact):
    """Pure supplied-buffer consistency; standalone inputs grant no authority.

    The operational context always obtains fact from parse_fact's fixed public
    pin and authenticates all eight physical leaves before calling this seam.
    No source/transport/GenuineInput capability is minted here.
    """
    expected=expected_files(fact)
    require(type(files) is dict and set(files)==set(NAMES)
        and all(type(raw) is bytes and pin(raw)==expected[name] for name,raw in files.items()),'pin')
    original=fact['original_result']['report'];summary=original['summary']
    require(files['report.json']==canonical(original),'report')
    proposal=loads(files['source-proposal.json'],MAX_PROPOSAL)
    keys={'schema','binding','parent_B_data_pin','source_inventory_pin','parent_source_vector_pin','parent_proof',
        'actual_plain_package_sha256','actual_plain_activation','objects','cells','current_attempt_state',*preparation.FLAGS}
    require(type(proposal) is dict and set(proposal)==keys and proposal['schema']==preparation.SCHEMA+'-source-proposal'
        and canonical(proposal['binding'])==canonical(fact['binding'])
        and proposal['parent_B_data_pin']==preparation.DATA_PIN
        and all(proposal[key] is False for key in preparation.FLAGS)
        and all(canonical(proposal[key])==canonical(summary[key]) for key in
            ('source_inventory_pin','parent_source_vector_pin','actual_plain_package_sha256','current_attempt_state'))
        and canonical(proposal['actual_plain_activation'])==canonical(summary['actual_activation']),'proposal')
    manifest=loads(files['transport-manifest.json'],MAX_REPORT,lf=True)
    activation=summary['actual_activation']
    try:
        transport,descriptors=plain._validate_transport(manifest,activation['object_store_key'],activation['byte_count'])
    except plain.AcceptedRiskOrderLevelInputRuntimeError:raise Refused('objects') from None
    require(transport['package_sha256']==summary['actual_plain_package_sha256']
        and transport['parent_proof_sha256']==summary['parent_proof_sha256']
        and canonical(proposal['parent_proof'])==canonical(transport['parent_proof'])
        and transport['parent_proof']['source_inventory_sha256']==summary['source_inventory_pin']['sha256']
        and transport['parent_proof']['source_package_sha256']=='411c2734da61c7d4172c4cb3d33c4ffdde650f40336a5e807d26e50cc7de0bad'
        and transport['parent_proof']['source_lineage_sha256']=='e4518e06a68a18a3151fe36e5926699624fc68b97c31a8e06917d44103831fd9','parent')
    require(type(proposal['objects']) is list and len(proposal['objects'])==6
        and canonical(proposal['objects'][:-1])==canonical(list(descriptors))
        and canonical(proposal['objects'][-1])==canonical(activation),'objects')
    uploads=[]
    for index,(name,descriptor) in enumerate(zip(OBJECT_NAMES,proposal['objects'],strict=True)):
        raw=files[name]
        require(descriptor['relative_path']==name and descriptor['compression']=='identity'
            and descriptor['byte_count']==len(raw) and descriptor['content_sha256']==pin(raw)['sha256']
            and descriptor['activation_manifest'] is (index==5),'objects')
        if index==0:
            evaluator=loads(raw,MAX_OBJECT,lf=True)
            require(type(evaluator) is dict and evaluator.get('manifest_id')==transport['evaluator_manifest_id']
                and evaluator.get('manifest_sha256')==transport['evaluator_manifest_sha256'],'objects')
        elif index<5:
            require(raw.endswith(b'\n') and type(descriptor['record_count']) is int
                and raw.count(b'\n')==descriptor['record_count'],'objects')
        uploads.append(Upload(canonical(descriptor),descriptor['object_store_key'],index==5,raw))
    require(type(proposal['cells']) is list and len(proposal['cells'])==len(summary['cells'])==7,'sources')
    selected=None
    for percent,cell,public in zip((80,100,120,140,160,180,200),proposal['cells'],summary['cells'],strict=True):
        require(type(cell) is dict and set(cell)=={'candidate_id','ar_percent','profile','source_pairs','bridge_record'}
            and cell['candidate_id']==public['candidate_id']==f'R343-AR{percent:03d}'
            and type(cell['ar_percent']) is int and cell['ar_percent']==percent
            and canonical(cell['bridge_record'])==canonical(public),'sources')
        profile_raw=canonical(cell['profile']);profile=cell['profile']
        require(type(profile) is dict and pin(profile_raw)==public['unchanged_profile_pin']
            and profile.get('candidate_id')==cell['candidate_id']
            and profile.get('research_epoch_id')=='R343-legacy-six-QCOM-restored-through-2026Oct13-v1'
            and profile.get('source_package_sha256')==public['ancestral_source_package_sha256']
            and profile.get('source_lineage_sha256')==public['source_lineage_sha256']
            and type(profile.get('original_profile_sha256')) is str
            and re.fullmatch('[0-9a-f]{64}',profile['original_profile_sha256']),'profile')
        seed=dict(profile);declared=seed.pop('profile_sha256',None)
        require(type(declared) is str and pin(canonical(seed))['sha256']==declared,'profile')
        require(type(cell['source_pairs']) is list and len(cell['source_pairs'])==len(public['source_files'])==18,'sources')
        sources=[]
        for pair,row in zip(cell['source_pairs'],public['source_files'],strict=True):
            require(type(pair) is list and len(pair)==2 and pair[0]==row['project_path']
                and type(pair[1]) is str and pair[1].isascii()
                and pin(pair[1].encode('ascii'))=={key:row[key] for key in ('byte_count','sha256')},'sources')
            sources.append((pair[0],pair[1].encode('ascii')))
        if percent==100:selected=Candidate(cell['candidate_id'],percent,profile_raw,tuple(sources),canonical(public))
    require(type(selected) is Candidate,'sources')
    identity={'schema':SCHEMA,'actual_plain_package_sha256':summary['actual_plain_package_sha256'],
        'source_lineage_sha256':transport['parent_proof']['source_lineage_sha256'],
        'ancestral_source_package_sha256':transport['parent_proof']['source_package_sha256'],
        'parent_proof_sha256':summary['parent_proof_sha256'],'actual_activation':activation,
        'source_proposal_pin':fact['original_result']['report']['source_proposal_pin'],
        'current_QC_admission_granted':False,'attempt_budget_reset':False,'paper_or_live_ready':False}
    return Submission(selected,tuple(uploads),canonical(identity),canonical(summary['current_attempt_state']))


def metadata(info):
    values=tuple(getattr(info,key,None) for key in FIELDS)
    require(all(type(value) is int and value>=0 for value in values),'metadata');return values


class FreshPlainSubmission:
    """Current endpoint byte/security checks of eight DATA leaves only."""
    def __init__(self,*,fact_bytes,deadline):
        self.fact=parse_fact(fact_bytes);self.expected=expected_files(self.fact)
        self.deadline,self.rows,self.cache,self.value=deadline,[],{},None
        self.entered=False
    def _hold(self,path,parent,name,expected=None):
        budget(self.deadline);before=metadata(os.stat(name,dir_fd=parent,follow_symlinks=False))
        require(stat.S_ISREG(before[2]) if expected is not None else stat.S_ISDIR(before[2]),'path')
        checked=path==ROOT or ROOT in path.parents
        if checked:
            require(before[3]==os.getuid() and stat.S_IMODE(before[2])==(0o600 if expected is not None else 0o755 if path==ROOT else 0o700)
                and not before[9]&~(getattr(stat,'UF_TRACKED',0)|getattr(stat,'UF_HIDDEN',0)),'metadata')
        if expected is not None:require(before[5]==1 and before[6]==expected['byte_count'],'pin')
        fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0)
            |(os.O_NONBLOCK if expected is not None else os.O_DIRECTORY),dir_fd=parent)
        row=[path,fd,parent,name,before,None,expected];self.rows.append(row)
        require(metadata(os.fstat(fd))==before,'metadata')
        if checked:row[5]=security.snapshot(fd)
        require(metadata(os.fstat(fd))==before==metadata(os.stat(name,dir_fd=parent,follow_symlinks=False)),'metadata')
        return row
    def _directory(self,path):
        current=Path('/');row=self.cache[current]
        for part in path.parts[1:]:
            current/=part
            if current not in self.cache:self.cache[current]=self._hold(current,row[1],part)
            row=self.cache[current]
        return row
    def _read(self,row):
        expected=row[6];size=expected['byte_count'];raw=bytearray();offset=0
        while offset<size:
            budget(self.deadline);chunk=os.pread(row[1],min(65536,size-offset),offset)
            require(chunk,'pin');raw.extend(chunk);offset+=len(chunk)
        require(pin(raw)==expected and not os.pread(row[1],1,offset),'pin')
        return bytes(raw)
    def __enter__(self):
        require(Path.cwd()==ROOT and ROOT.resolve()==ROOT and DIRECTORY==ROOT/
            'artifacts/analyst_revisions_v2/legacy_six_plain/R346-20261107-A','scope')
        require(not self.entered and not self.rows,'state');self.entered=True
        require(sum(item['byte_count'] for item in self.expected.values())<=MAX_TOTAL,'pin')
        try:
            fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            root=[Path('/'),fd,fd,'.',metadata(os.fstat(fd)),None,None]
            self.rows.append(root);self.cache[Path('/')]=root
            parent=self._directory(DIRECTORY)
            raws={}
            for name in NAMES:
                row=self._hold(DIRECTORY/name,parent[1],name,self.expected[name]);raws[name]=self._read(row)
            # All eight out-of-band hashes are complete before private parsing.
            self.value=validate_supplied(raws,fact=self.fact)
            self.verify();return self
        except BaseException:
            self.close();raise
    def verify(self):
        require(self.entered and self.rows and type(self.value) is Submission,'state')
        for path,fd,parent,name,before,native,expected in self.rows:
            budget(self.deadline)
            require(metadata(os.fstat(fd))==before==metadata(os.stat(name,dir_fd=parent,follow_symlinks=False)),'metadata')
            if native is not None:require(security.snapshot(fd)==native,'security')
            if expected is not None:self._read([path,fd,parent,name,before,native,expected])
            require(metadata(os.fstat(fd))==before,'metadata')
    def close(self):
        failed=False
        for row in reversed(self.rows):
            try:os.close(row[1])
            except OSError:failed=True
        self.rows.clear();self.cache.clear()
        require(not failed,'close')
    def __exit__(self,*args):
        try:self.verify()
        finally:self.close()
