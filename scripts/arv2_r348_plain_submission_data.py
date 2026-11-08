"""Fresh all-seven source DATA for a separately frozen R348 caller.

The frozen R347 pure validator authenticates the eight supplied byte pins and
all seven source vectors. This new context owns fresh physical reads and never
calls R347's operational context entry or changes a frozen module global. It
does not read the unbound preparation claim, reset budgets, or grant contact.
"""
from dataclasses import dataclass, field
from datetime import date
import os
from pathlib import Path
import stat

from scripts import arv2_r347_plain_submission_data as previous

SCHEMA='arv2-r348-fresh-all-seven-plain-submission-DATA-v1'
ROOT=Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
DIRECTORY=ROOT/'artifacts/analyst_revisions_v2/legacy_six_plain/R346-20261107-A'
NAMES=tuple(previous.NAMES)
FACT_PIN=dict(previous.FACT_PIN)
PERCENTS=(80,100,120,140,160,180,200)
AXIS_COUNT=3466
AXIS_SHA256='4ac84a2d01e18691a152812851857195ef56dac16b82ceb72bcf7dd068f86585'
Candidate,Upload=previous.Candidate,previous.Upload
Refused,FINITE=previous.Refused,previous.FINITE|frozenset(('axis',))
require,canonical,pin,loads=previous.require,previous.canonical,previous.pin,previous.loads
budget,metadata,security=previous.budget,previous.metadata,previous.security
parse_fact,expected_files=previous.parse_fact,previous.expected_files


@dataclass(frozen=True,slots=True)
class Submission:
    candidates:tuple=field(repr=False)
    uploads:tuple=field(repr=False)
    evaluation_sessions:tuple=field(repr=False)
    source_identity_json:bytes=field(repr=False)
    attempt_state_at_preparation_json:bytes=field(repr=False)


def _evaluation_sessions(raw,manifest,descriptor):
    """Parse the authenticated canonical axis, preserving its actual sessions."""
    evaluator=previous.plain.evaluator
    try:
        require(type(manifest) is dict and manifest.get('schema')==evaluator.MANIFEST_SCHEMA
            and type(manifest.get('session_axis_count')) is int
            and manifest['session_axis_count']==descriptor['record_count']
            and manifest.get('session_axis_sha256')==pin(raw)['sha256'],'axis')
        rows=previous.plain._plain_rows(raw,descriptor['record_count'],'session_axis')
        axis=evaluator._parse_sessions(rows)
    except (previous.plain.AcceptedRiskOrderLevelInputRuntimeError,evaluator.PreliminaryRatingEvaluationError):
        raise Refused('axis') from None
    require(len(axis)==AXIS_COUNT and pin(canonical(axis))['sha256']==AXIS_SHA256,'axis')
    sessions=tuple(day for day in axis if '2021-01-04'<=day<='2026-10-13')
    decisions=[];seen=set()
    for day in sessions:
        week=date.fromisoformat(day).isocalendar()[:2]
        if week not in seen:decisions.append(day);seen.add(week)
    require(len(sessions)==1451 and len(decisions)==302
        and sessions[0]==decisions[0]=='2021-01-04' and sessions[-1]=='2026-10-13'
        and decisions[-1]=='2026-10-12','axis')
    return sessions


def validate_supplied(files,*,fact):
    """Consistency of supplied DATA only; no genuine capability is minted."""
    require(type(files) is dict,'pin')
    buffers=dict(files)
    # Detach the pure supplied-fact seam as well. Operational entry gets this
    # only from the frozen exact public-fact parser, never a caller assertion.
    detached_fact=loads(canonical(fact),previous.MAX_REPORT)
    checked=previous.validate_supplied(buffers,fact=detached_fact)
    manifest=loads(buffers['evaluator-manifest.json'],previous.MAX_OBJECT,lf=True)
    axis_descriptor=loads(checked.uploads[1].descriptor_json,previous.MAX_REPORT)
    sessions=_evaluation_sessions(buffers['session_axis-0000.jsonl'],manifest,axis_descriptor)
    proposal=loads(buffers['source-proposal.json'],previous.MAX_PROPOSAL)
    candidates=[]
    for percent,cell in zip(PERCENTS,proposal['cells'],strict=True):
        # All fields, profiles and source bytes already passed the frozen
        # validator against all seven public source vectors before this step.
        require(cell['candidate_id']==f'R343-AR{percent:03d}'
            and type(cell['ar_percent']) is int and cell['ar_percent']==percent,'sources')
        candidates.append(Candidate(cell['candidate_id'],percent,canonical(cell['profile']),
            tuple((name,text.encode('ascii')) for name,text in cell['source_pairs']),canonical(cell['bridge_record'])))
    require(len(candidates)==7 and candidates[1]==checked.candidate,'sources')
    return Submission(tuple(candidates),checked.uploads,sessions,checked.source_identity_json,
        checked.attempt_state_at_preparation_json)


class FreshAllPlainSubmission:
    """Fresh original-FD/current-native checks of exactly eight DATA leaves."""
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
        require(sum(item['byte_count'] for item in self.expected.values())<=previous.MAX_TOTAL,'pin')
        try:
            fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            root=[Path('/'),fd,fd,'.',metadata(os.fstat(fd)),None,None]
            self.rows.append(root);self.cache[Path('/')]=root
            parent=self._directory(DIRECTORY)
            raws={}
            for name in NAMES:
                row=self._hold(DIRECTORY/name,parent[1],name,self.expected[name]);raws[name]=self._read(row)
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
