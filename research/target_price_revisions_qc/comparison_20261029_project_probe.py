"""Pure OFF-only isolated-project diagnostic; original parent custody stays old.

Rebinds only three actual-child-project comparisons in the reviewed extended
probe. The old parent witness/config/key/SID validation is unchanged. A single
bounded native Symbol.Value label is retained only inside the private QC log
for a fresh separately scoped Mia/source-routing investigation; no prices,
volumes, full SID, economic result or public identity export is produced.
"""
from __future__ import annotations
import ast
import hashlib
import json

from . import comparison_20261029_extended_mark_probe as prior

MODULE = 'research/target_price_revisions_qc/comparison_20261029_project_probe.py'
PRIOR_MODULE = 'research/target_price_revisions_qc/comparison_20261029_extended_mark_probe.py'
REGISTRY_MODULE = 'research/target_price_revisions_qc/comparison_20261029_projects.py'
REGISTRY_SHA256 = '6dc87f33105de9d80e7a267a6cc737bb4262f47e49c43b65247592927a5788d7'
PRIOR_SHA256 = '0526a563426c86b2c16d1a166591e70e78d0693103057c2765f7e8e08183d867'
SOURCE_ARGUMENTS = {
    'tick_source':'comparison_20261029_mark_tick_probe.py',
    'native_post_gap_source':'comparison_20261028_mark_probe_post_gap_native.py',
    'post_gap_source':'comparison_20261028_mark_probe_post_gap.py',
    'control_source':'comparison_20261028_mark_probe_control.py',
    'base_probe_source':'comparison_20261028_mark_probe.py',
    'helper_source':'comparison_20261028_mark_read.py',
    'producer_source':'comparison_20261028_algorithm.py',
}
PREFIX = 'research/target_price_revisions_qc/'

class ProjectProbeRefusal(ValueError): pass

def _fail():
    raise ProjectProbeRefusal('isolated own-project mark probe refused') from None

def _sha(raw):
    return hashlib.sha256(raw).hexdigest()

def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')

def _replace(source,node,replacement):
    lines=source.splitlines(keepends=True)
    if node.end_lineno is None or node.end_col_offset is None or not source.isascii(): _fail()
    start=sum(map(len,lines[:node.lineno-1]))+node.col_offset
    stop=sum(map(len,lines[:node.end_lineno-1]))+node.end_col_offset
    return source[:start]+replacement+source[stop:]

def _assignment(source,name,value):
    rows=[n for n in ast.parse(source).body if isinstance(n,ast.Assign) and len(n.targets)==1
          and isinstance(n.targets[0],ast.Name) and n.targets[0].id==name]
    if len(rows)!=1:_fail()
    return _replace(source,rows[0].value,value)

def build_project_probe(*,public_sources,project_bindings_raw,expected_project_bindings_sha256,
                        operation_id,git_head):
    """Render exact bounded diagnostic bytes; no claims or native effects here."""
    from . import comparison_20261029_projects as registry
    try:
        bindings=registry.validate_bindings(project_bindings_raw,expected_sha256=expected_project_bindings_sha256)
        if bindings['adapter_source_sha256']!=REGISTRY_SHA256:_fail()
        # API/source binding, not this pure function, authenticates registry origin.
        project=bindings['projects']['OFF']['project_id']
        if (type(public_sources) is not dict or set(public_sources)!=
            {PRIOR_MODULE,REGISTRY_MODULE}|{PREFIX+n for n in SOURCE_ARGUMENTS.values()}
            or type(public_sources[PRIOR_MODULE]) is not bytes
            or _sha(public_sources[PRIOR_MODULE])!=PRIOR_SHA256
            or type(public_sources[REGISTRY_MODULE]) is not bytes
            or _sha(public_sources[REGISTRY_MODULE])!=REGISTRY_SHA256):_fail()
        raw,report_raw=prior.build_extended_mark_probe(
            **{argument:public_sources[PREFIX+name] for argument,name in SOURCE_ARGUMENTS.items()},
            operation_id=operation_id,git_head=git_head)
        source=raw.decode('ascii')
        main=[n for n in ast.parse(source).body if isinstance(n,ast.ClassDef) and n.name=='Main']
        if len(main)!=1:_fail()
        changes=[]
        for n in ast.walk(main[0]):
            if isinstance(n,ast.Compare):
                # Only comparisons of actual self.project_id to old PROJECT.
                if any(isinstance(x,ast.Attribute) and isinstance(x.value,ast.Name)
                       and x.value.id=='self' and x.attr=='project_id' for x in [n.left,*n.comparators]):
                    changes.extend(x for x in [n.left,*n.comparators] if isinstance(x,ast.Name) and x.id=='PROJECT')
        if len(changes)!=3:_fail()
        for node in sorted(changes,key=lambda n:(n.lineno,n.col_offset),reverse=True):
            source=_replace(source,node,str(project))
        marker="            self._report['native_identity_roundtrip']=True"
        if source.count(marker)!=1:_fail()
        label_code="""
            # Exact native identity metadata only; separately scoped private log.
            label=self._effect('private_identity_label',lambda:symbol.value)
            if type(label) is not str or re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',label) is None:
                raise ProbeRefusal('native_identity_framing_unproved')
            self._report['private_target_identity_label']=label
"""
        source=source.replace(marker,marker+label_code,1)
        cfg_node=[n for n in ast.parse(source).body if isinstance(n,ast.Assign) and len(n.targets)==1
                  and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='PROBE_CONFIG_JSON']
        if len(cfg_node)!=1:_fail()
        config=json.loads(ast.literal_eval(cfg_node[0].value))
        if config['binding']['project_id']!=37650980 or config['binding']['job_id']!='12dd4732ba5d9d8f57950beb2a371c79':_fail()
        config.update(child_project_id=project,project_bindings_sha256=expected_project_bindings_sha256,
                      private_identity_label_max_bytes=64,public_identity_export=False)
        config_raw=_canonical(config);digest=_sha(config_raw)
        source=_assignment(source,'PROBE_CONFIG_JSON',repr(config_raw.decode('ascii')))
        source=_assignment(source,'PROBE_CONFIG_SHA256',repr(digest))
        # The parent helper PROJECT remains old37650980; only Main's three
        # actual-child checks differ. Parent _binding_v2/_key are unchanged.
        output=source.encode('ascii')
        if not 0<len(output)<=60000:_fail()
        compile(ast.parse(source),'main.py','exec')
        report=json.loads(report_raw)
        report.update(schema='tpr-cmp28-isolated-project-probe-build-v1',
                      child_project_id=project,parent_project_id=37650980,
                      project_bindings_sha256=expected_project_bindings_sha256,
                      config_sha256=digest,main_sha256=_sha(output),main_bytes=len(output),
                      private_identity_label_max_bytes=64,public_identity_export=False,
                      same_session_correction_proven=False,financial_recovery_proven=False)
        return output,_canonical(report)+b'\n'
    except ProjectProbeRefusal:raise
    except Exception:_fail()
