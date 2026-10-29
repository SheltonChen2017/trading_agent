"""Pure source-bound five-project rebind of the preserved financial candidates.

Only exact project/config literals change in the generated native files. Every
financial function remains AST-identical to the independently pinned templates.
The registry is validated by the creation adapter and bound to its public source
and receipt digests. This proves framing, never native origin or effect authority.
No files, credentials, Object Store payloads, accounts or native APIs are opened.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re

from . import comparison_20261028_bundle as off
from . import comparison_20261028_multi_bundle as multi
from . import comparison_20261029_projects as projects

PREFIX='research/target_price_revisions_qc/'
OFF_PATH=PREFIX+'comparison_20261028_bundle.py'
MULTI_PATH=PREFIX+'comparison_20261028_multi_bundle.py'
PROJECTS_PATH=PREFIX+'comparison_20261029_projects.py'
# Independently checked after the creation adapter's source-stable validation.
PROJECTS_SHA256='57e9807fa7cb59d271347cc364f5fe5d94a34e99d99c516e8b8e2ea930dc5ca1'
PINS={**multi.PINS,MULTI_PATH:'7015c94867da28d31426627275ec607e9f8fb3d8f6cb38d97cbd6aa5511b7e28',
    PROJECTS_PATH:PROJECTS_SHA256}
SOURCE_PATHS=tuple(PINS)
ARM_KEYS={'cap_off':'OFF','cap_tilt_50':'TPR050','cap_tilt_100':'TPR100',
    'cap_tilt_200':'TPR200LONG','pure_tpr':'PURE'}
NAMES={key:'TPR-CMP28-R107-20261029A-'+key for key in ARM_KEYS.values()}
ROUND='TPR-CMP28-R107-20261029A'
OLD_PROJECTS=frozenset((37650980,37650453))
PACKET_BYTES=280105389
PACKET_SHA256='6a8f4915df539f5aee731832138e038caf6dd579b591ebe745e37b5d283e4708'
PACKET_KEY='tpr-cmp28/inputs/37650980/TPR-SIX-UNIVERSE-FIVE-ARM-20261028-v1/upload-003/'+PACKET_SHA256+'.json'
INVENTORY_SHA256='29d831c1f0fe103f0744b90e9f6e9d9f14a56a48592bf7acee849fdd5508c0f2'


class ProjectBundleRefusal(ValueError):
    """Body-free unproved source, registry or literal-rebind refusal."""


def _fail():
    raise ProjectBundleRefusal('source-bound private-project candidate refused') from None


def _sha(raw):return hashlib.sha256(raw).hexdigest()


def _wire(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')


def _hash(value):
    if type(value) is not str or re.fullmatch('[a-f0-9]{64}',value) is None:_fail()
    return value


def _assignment(raw,name,expected,value):
    """One declared literal only; never general text replacement or exec."""
    tree=ast.parse(raw);nodes=[node for node in tree.body if isinstance(node,ast.Assign)
        and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id==name]
    if len(nodes)!=1 or ast.dump(nodes[0].value)!=ast.dump(ast.parse(expected,mode='eval').body):_fail()
    text=raw.decode('utf-8')
    return off._span_replace(text,nodes[0].value,value).encode('utf-8')


def _functions(raw):
    return {(type(node).__name__,node.name,ast.dump(node,include_attributes=False))
        for node in ast.walk(ast.parse(raw)) if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))}


def _packet(value):
    expected={'key':PACKET_KEY,'sha256':PACKET_SHA256,'bytes':PACKET_BYTES,
        'encoding':'utf-8-json','source_inventory_sha256':INVENTORY_SHA256}
    if type(value) is not dict or value!=expected or _wire(value)!=_wire(expected):_fail()
    return expected


def build_project_candidate(*,public_sources,project_binding_raw,expected_project_binding_sha256,
        arm,operation_id,attempt,prior_attempts_looks_sha256,signal_packet=None):
    """Return flat source bytes/report only; no registration or permission minted.

    The caller separately claims any private registry read. Registry source and
    metadata receipts remain provenance; each later effect needs fresh actual
    project/source/runtime checks. The immutable shared signal key is read only
    inside a genuinely bound native signal job, never by this builder.
    """
    try:
        if (type(public_sources) is not dict or set(public_sources)!=set(SOURCE_PATHS)
                or type(arm) is not str or arm not in ARM_KEYS
                or type(project_binding_raw) is not bytes or not 0<len(project_binding_raw)<=65536
                or type(attempt) is not int or not 1<=attempt<=2**31-1
                or type(operation_id) is not str or len(operation_id)>160
                or re.fullmatch(r'TPR-CMP28-[A-Za-z0-9][A-Za-z0-9_.-]*',operation_id) is None):_fail()
        for path,digest in PINS.items():
            _hash(digest);raw=public_sources[path]
            if type(raw) is not bytes or not 0<len(raw)<=131072 or _sha(raw)!=digest:_fail()
        if (off.PINS!=multi.BASE_PINS or {PREFIX+name:value for name,value in off.PINS.items()}
                !={name:PINS[name] for name in off.SOURCE_PATHS}
                or dict(projects.RESERVED_NAMES)!=NAMES):_fail()
        prior=_hash(prior_attempts_looks_sha256);binding_hash=_hash(expected_project_binding_sha256)
        if _sha(project_binding_raw)!=binding_hash:_fail()
        binding=projects.validate_bindings(project_binding_raw,expected_sha256=binding_hash)
        if (binding['adapter_source_sha256']!=PINS[PROJECTS_PATH] or binding['round_id']!=ROUND
                or set(binding['projects'])!=set(NAMES)):_fail()
        # All five bindings must be retained, never an arbitrary selected ID.
        seen=set()
        for key,expected_name in NAMES.items():
            row=binding['projects'][key];project=row['project_id']
            if (type(project) is not int or not 1<=project<=2**31-1 or project in OLD_PROJECTS or project in seen
                    or row['name']!=expected_name or row['organization_id']!=binding['organization_id']
                    or row['owner_id']!=binding['owner_id'] or row['language']!='Py'
                    or type(row['nonowner_collaborator_count']) is not int or row['nonowner_collaborator_count']!=0):_fail()
            seen.add(project)
        chosen=binding['projects'][ARM_KEYS[arm]];project=chosen['project_id']
        if arm=='cap_off':
            if signal_packet is not None:_fail()
            # This is a pure historical-template render, never an old-project
            # operation. Final files/config below are bound only to the new ID.
            files,base_report=off.build_off_candidate(public_sources={path:public_sources[path] for path in off.SOURCE_PATHS},
                operation_id=operation_id,attempt=attempt,prior_attempts_looks_sha256=prior)
        else:
            packet=_packet(signal_packet)
            files,base_report=multi.build_multi_candidate(public_sources={path:public_sources[path] for path in multi.SOURCE_PATHS},
                arm=arm,operation_id=operation_id,attempt=attempt,prior_attempts_looks_sha256=prior,
                signal_packet=packet,project_id=37650980)
        original=dict(files);base=json.loads(base_report)
        node=ast.parse(files['comparison_20261028_config.py']).body[0]
        if (not isinstance(node,ast.Assign) or len(node.targets)!=1
                or not isinstance(node.targets[0],ast.Name) or node.targets[0].id!='CONFIG_JSON'):_fail()
        config=json.loads(ast.literal_eval(node.value))
        if config['project_id']!=37650980 or config['arm']!=arm:_fail()
        templates={path:_sha(raw) for path,raw in sorted(public_sources.items())}
        closure=_sha(_wire({'schema':'tpr-cmp28-public-template-closure-v1','source_hashes':templates}))
        config.update(project_id=project,source_template_closure_sha256=closure)
        config_raw=_wire(config);config_hash=_sha(config_raw)
        driver='comparison_20261028_algorithm.py'
        files[driver]=_assignment(files[driver],'PROJECT','37650980',str(project))
        if arm=='cap_off':
            files[driver]=_assignment(files[driver],'EXPECTED_CONFIG_SHA256',repr(base['config_sha256']),repr(config_hash))
        else:
            name='comparison_20261028_multi_algorithm.py'
            files[name]=_assignment(files[name],'PROJECTS','frozenset((37650980,37650453))','frozenset(('+str(project)+',))')
            files[name]=_assignment(files[name],'EXPECTED_CONFIG_SHA256',repr(base['config_sha256']),repr(config_hash))
        files['comparison_20261028_config.py']=('CONFIG_JSON = '+repr(config_raw.decode('ascii'))+'\n').encode('ascii')
        changed={name for name in files if files[name]!=original[name]}
        expected={driver,'comparison_20261028_config.py'}|({'comparison_20261028_multi_algorithm.py'} if arm!='cap_off' else set())
        if changed!=expected:_fail()
        for name,raw in files.items():
            if not 0<len(raw)<=60000 or _functions(raw)!=_functions(original[name]):_fail()
            compile(ast.parse(raw),name,'exec')
        hashes={name:_sha(raw) for name,raw in sorted(files.items())}
        report={'schema':'tpr-cmp28-isolated-project-bundle-v1','round_id':ROUND,'study_id':config['study_id'],
            'candidate_id':config['candidate_id'],'arm':arm,'project_id':project,'project_name':chosen['name'],
            'operation_id':operation_id,'attempt':attempt,'prior_attempts_looks_sha256':prior,
            'project_binding_sha256':binding_hash,'project_binding_bytes':len(project_binding_raw),
            'project_binding_git_head':binding['git_head'],'owner_instruction_sha256':binding['owner_instruction_sha256'],
            'organization_id_sha256':_sha(binding['organization_id'].encode('utf-8')),
            'owner_id_sha256':_sha(str(binding['owner_id']).encode('utf-8')),
            'project_create_receipt_sha256':chosen['create_receipt_sha256'],
            'project_read_receipt_sha256':chosen['read_receipt_sha256'],
            'project_collaboration_receipt_sha256':chosen['collaboration_receipt_sha256'],
            'project_privacy_basis':binding['privacy_basis'],
            'explicit_privacy_flag_observed':binding['explicit_privacy_flag_observed'],
            'config_sha256':config_hash,'policy_sha256':config['policy_sha256'],'calendar_sha256':config['calendar_sha256'],
            'source_template_closure_sha256':closure,'template_source_hashes':templates,
            'rendered_source_closure_sha256':_sha(_wire(hashes)),'cloud_source_hashes':hashes,
            'cloud_source_bytes':{name:len(raw) for name,raw in sorted(files.items())},'file_count':len(files),
            'main_class':base['main_class'],'changed_project_binding_files':sorted(changed),
            'financial_function_bodies_unchanged':True,'project_local_source_readback_required':True,
            'preserve_actual_fresh_project_extras':True,'legacy_notebooks_copied':False,'legacy_extras_required':False,
            'shared_signal_key_organization_bound':arm!='cap_off','signal_packet_descriptor_sha256':
                _sha(_wire(config['signal_packet'])) if arm!='cap_off' else None,
            'new_native_job_access_claim_required':True,'retired_project_write_authorized':False,
            'project_metadata_native_origin_attested':False,'independent_native_origin_attested':False,
            'native_permission':False,'reservation_sha256':None,'new_attempts':0,'new_observed_looks':0,
            'prior_attempts_reset':False,'strategy_economics_changed':False,'mark_policy_changed':False,
            'source_inputs_admitted':False,'canonical_admission':False,'strategy_accepted':False,'accepted_performance':None}
        return files,_wire(report)+b'\n'
    except ProjectBundleRefusal:raise
    except (Exception,):_fail()
