"""Fresh input boundary tests: synthetic in-root files, no retained DATA or QC.

A tiny synthetic compact authority seam is explicitly substituted only in the
end-to-end wrapper fixture. The actual sealed plain transport mint/require and
all new native descriptor/byte/stream guards execute; no genuine production
package or old operator is invoked.
"""
import ast
import copy
import dataclasses
import inspect
import json
import os
from pathlib import Path
import stat
import time
from types import SimpleNamespace as NS

import pytest
from scripts import arv2_r338_quarantine_input as m


def refused(code,call):
    with pytest.raises(m.Refused) as caught:call()
    assert m.finite(caught.value)==code


def binding(index):
    token='BBG'+str(index).zfill(9)
    return m.figi.build_preliminary_qc_figi_binding(security_id='sharadar-composite-figi-'+token,
        issuer_id='synthetic-issuer-'+str(index),composite_figi=token,listing_id='synthetic-listing-'+str(index),
        diagnostic_current_ticker='SYNTH'+str(index),diagnostic_exchange_mic='XNYS',
        candidate_first_session='2020-12-31',candidate_last_session='2026-10-13',
        source_snapshot_available_at='2026-10-01T00:00:00.000000Z',source_row_sha256=m.sha(str(index).encode()),
        identity_evidence_sha256=m.sha(('evidence'+str(index)).encode()),security_master_admission_sha256=m.ADMISSION_SHA256,
        admitted_mapping_inventory_sha256='b'*64,admitted_mapping_count=7)


def source_fixture():
    axis=m.october._sessions()
    sessions=tuple({'schema':m.evaluator.SESSION_SCHEMA,'session_index':i,'session':day} for i,day in enumerate(axis))
    bindings=tuple(binding(i) for i in range(7))
    memberships=tuple(m.evaluator.build_membership_record(security_id=row['security_id'],
        first_session_index=0,last_session_index_exclusive=len(axis),sector_id='synthetic-sector') for row in bindings)
    contributions=({'SYNTHETIC_PRIVATE_UNUSED_CONTRIBUTION':'not reparsed by new wrapper'},)
    lineage=b'{"synthetic_october_lineage":true}'
    lineage_sha=m.sha(lineage)
    source_lineage={name:lineage_sha for name in m.evaluator._SOURCE_LINEAGE_FIELDS}
    source_lineage['security_master_admission_sha256']=m.ADMISSION_SHA256
    manifest=m.evaluator.build_preliminary_rating_manifest(benchmark_security_id='arv2-benchmark-SPY',
        session_axis_records=sessions,membership_records=memberships,contribution_records=contributions,
        source_lineage_sha256s=source_lineage)
    rows={'evaluator_manifest':(manifest,),'session_axis':sessions,'memberships':memberships,
        'contributions':contributions,'runtime_symbol_bindings':bindings}
    pairs=[]
    for role in m.ROLES:
        raw=m.canonical(manifest)+b'\n' if role=='evaluator_manifest' else m.compact._gzip_records(rows[role])
        name='evaluator-manifest.json' if role=='evaluator_manifest' else role+'-0000-jsonl.gz'
        item=m.compact.PreliminaryUploadObject(m.compact.UPLOAD_OBJECT_SCHEMA,role,0,
            'arv2/preliminary-synthetic/'+name,name,len(raw),m.sha(raw),len(rows[role]),
            'identity' if role=='evaluator_manifest' else 'gzip',False)
        pairs.append((item,raw))
    record=m.compact._transport_seed(package_id=None,package_sha256=None,evaluator_manifest=manifest,
        objects=[item for item,_ in pairs],source_disposition_sha256=lineage_sha,
        runtime_symbol_binding_count=len(bindings),runtime_symbol_bindings_sha256=m._stream(bindings),
        contribution_census={'accepted':1})
    package_sha=m.sha(m.canonical(record));package_id='arv2-preliminary-qc-package-'+package_sha[:24]
    record.update(package_sha256=package_sha,package_id=package_id)
    raw=m.canonical(record)+b'\n'
    item=m.compact.PreliminaryUploadObject(m.compact.UPLOAD_OBJECT_SCHEMA,'activation_manifest',0,
        'arv2/preliminary-synthetic/transport-manifest.json','transport-manifest.json',len(raw),m.sha(raw),1,'identity',True)
    pairs.append((item,raw))
    package=NS(package_sha256=package_sha,package_id=package_id,source_disposition_sha256=lineage_sha,
        upload_objects=tuple(item for item,_ in pairs),total_upload_byte_count=sum(len(raw) for _,raw in pairs))
    return NS(axis=axis,rows=rows,manifest=manifest,lineage=lineage,lineage_sha=lineage_sha,pairs=tuple(pairs),package=package)


@pytest.fixture
def case(tmp_path,monkeypatch):
    source=source_fixture();root=tmp_path/'synthetic-root';root.mkdir(mode=0o755);root.chmod(0o755)
    inputs=root/'artifacts'/'analyst_revisions_v2'/'synthetic-package'
    package=inputs/source.package.package_id;lineage=inputs/('arv2-october-lineage-'+source.lineage_sha)/'lineage.json'
    for leaf in (package/'transport-manifest.json',lineage):
        here=root
        for part in leaf.parent.relative_to(root).parts:
            here/=part;here.mkdir(mode=0o700,exist_ok=True);here.chmod(0o700)
    for item,raw in source.pairs:
        leaf=package/item.relative_path;leaf.write_bytes(raw);leaf.chmod(0o600)
    lineage.write_bytes(source.lineage);lineage.chmod(0o600)
    for name,value in {'ROOT':root,'INPUT_ROOT':inputs,'PACKAGE':package,'LINEAGE':lineage,
        'PACKAGE_SHA256':source.package.package_sha256,'LINEAGE_SHA256':source.lineage_sha,
        'SOURCE_ACTIVATION':m.pin(source.pairs[-1][1]),'SOURCE_TOTAL_BYTES':source.package.total_upload_byte_count,
        'BINDING_COUNT':7,'BINDING_STREAM_SHA256':m._stream(source.rows['runtime_symbol_bindings']),
        'MAPPING_SHA256':'b'*64,'MANIFEST_SHA256':source.manifest['manifest_sha256'],
        'MEMBERSHIP_STREAM_SHA256':m._stream(source.rows['memberships'])}.items():monkeypatch.setattr(m,name,value)
    monkeypatch.chdir(root)
    events=[];fingerprint=lambda value:(value.package_sha256,value.source_disposition_sha256,value.upload_objects,value.total_upload_byte_count)
    initial=fingerprint(source.package)
    def require_package(value):
        assert value is source.package
        assert fingerprint(value)==initial
        events.append('compact-require');return value
    def iterate(value):
        assert value is source.package;events.append('compact-iterate')
        yield from source.pairs
        events.append('compact-exhausted')
    # These are explicit synthetic source-authority seams. The real pure plain
    # transport conversion, sealed mint and process authority guard are kept.
    monkeypatch.setattr(m.compact,'require_accepted_risk_preliminary_package',require_package)
    monkeypatch.setattr(m.compact,'_package_fingerprint',fingerprint)
    monkeypatch.setattr(m.transport,'_REQUIRE_SOURCE',require_package)
    monkeypatch.setattr(m.transport,'_ITER_SOURCE',iterate)
    plain=m.transport.build_plain_transport(source.package,expected_package_sha256=source.package.package_sha256,
        expected_lineage_sha256=source.lineage_sha)
    for name,value in {'PLAIN_PACKAGE_SHA256':plain.package_sha256,
        'PLAIN_ACTIVATION':{'byte_count':plain.activation_manifest_byte_count,'sha256':plain.activation_manifest_sha256},
        'PARENT_PROOF_SHA256':plain.parent_proof_sha256,
        'UPLOAD_INVENTORY_SHA256':m.sha(m.canonical([item.to_record() for item in plain.upload_objects]))}.items():monkeypatch.setattr(m,name,value)
    wrapped=NS(package=source.package,lineage_sha256=source.lineage_sha,lineage_bytes=source.lineage)
    reads=[];original=m._InputGuard._read
    def read(self,row):reads.append(row['path']);return original(self,row)
    monkeypatch.setattr(m._InputGuard,'_read',read)
    def load(path,**kwargs):
        assert path==package and kwargs=={'expected_package_sha256':source.package.package_sha256,
            'lineage_path':lineage,'expected_lineage_sha256':source.lineage_sha}
        assert set(reads)>={package/item.relative_path for item,_ in source.pairs}|{lineage}
        events.append('october-load');return wrapped
    def require_october(value):
        assert value is wrapped and value.package is source.package
        events.append('october-require');return value
    monkeypatch.setattr(m.october,'load_october_order_input_package',load)
    monkeypatch.setattr(m.october,'require_october_order_input_package',require_october)
    events.clear()
    return NS(root=root,source=source,package=package,lineage=lineage,events=events,reads=reads,wrapped=wrapped)


def fresh():return m.GenuineInput(deadline=time.monotonic()+300)


def test_constructor_and_public_paths_do_not_allocate_read_or_mint(monkeypatch):
    def no(*args,**kwargs):pytest.fail('inert boundary crossed')
    monkeypatch.setattr(os,'open',no);monkeypatch.setattr(os,'pread',no)
    monkeypatch.setattr(m.october,'load_october_order_input_package',no)
    value=fresh();paths=m.input_paths();profile=m.profile_record()
    assert value._guard is None and paths['package_payload_inventory'].startswith('claim_bound')
    assert profile['normal_return_required_before_use'] is True
    assert all(profile[k] is False for k in m.FALSE_FLAGS)


def test_full_genuine_wrapper_uses_all_source_bytes_real_plain_authority_and_defensive_properties(case):
    held=fresh()
    with held as value:
        assert value.axis==case.source.axis and len(value.bindings)==7
        assert value.input_binding==m.expected_input_binding()
        assert set(value.selected)==set(m.PARSED_ROLES) and 'contributions' not in value.selected
        assert m.transport.require_plain_transport(value.plain) is value.plain
        first=value.bindings;first[0]['diagnostic_current_ticker']='MUTATED'
        assert value.bindings[0]['diagnostic_current_ticker']!='MUTATED'
        manifest=value.manifest;manifest['membership_row_count']=0
        assert value.manifest['membership_row_count']==7
        assert value.verify(deadline=value.deadline) is True
        receipt=value.receipt();assert m.validate_receipt(receipt)==receipt
        assert receipt['contributions_validated_by_genuine_compact_evaluator'] is True
        assert receipt['contributions_reparsed_by_this_helper'] is False
        assert receipt['source_package_object_count']==6 and receipt['source_guard']['source_leaf_count']==7
        assert case.events.index('october-load')<case.events.index('compact-iterate')<case.events.index('compact-exhausted')
        assert all(row['fd']>=3 for row in value._guard.objects)
    assert not held._active and not held._guard.objects
    refused('state',lambda:held.axis);refused('state',held.__enter__)


@pytest.mark.parametrize('target',['activation','lineage','payload'])
def test_external_hashes_and_all_payload_hashes_precede_genuine_loader(case,target):
    path=(case.package/'transport-manifest.json' if target=='activation' else case.lineage if target=='lineage'
        else case.package/case.source.pairs[2][0].relative_path)
    raw=path.read_bytes();path.write_bytes(b'X'+raw[1:]);path.chmod(0o600)
    with pytest.raises(m.Refused):
        with fresh():pytest.fail('corrupt source reached use')
    assert 'october-load' not in case.events


@pytest.mark.parametrize('fault',['extra_package','extra_lineage','symlink','hardlink','file_mode','dir_mode','fifo'])
def test_manifest_inventory_private_modes_links_and_special_files_are_hard_stops(case,fault):
    leaf=case.package/case.source.pairs[2][0].relative_path
    if fault=='extra_package':(case.package/'unselected.txt').write_bytes(b'extra')
    elif fault=='extra_lineage':(case.lineage.parent/'unselected.txt').write_bytes(b'extra')
    elif fault=='symlink':
        raw=leaf.read_bytes();leaf.unlink();other=case.root/'alternate';other.write_bytes(raw);other.chmod(0o600);leaf.symlink_to(other)
    elif fault=='hardlink':os.link(leaf,case.root/'second-link')
    elif fault=='file_mode':leaf.chmod(0o644)
    elif fault=='dir_mode':case.package.chmod(0o755)
    else:leaf.unlink();os.mkfifo(leaf,0o600)
    with pytest.raises(m.Refused):
        with fresh():pytest.fail('unsafe source reached use')
    assert 'october-load' not in case.events


@pytest.mark.parametrize('field',m.FIELDS)
def test_all_ten_named_and_held_metadata_fields_are_binding_after_genuine_work(case,monkeypatch,field):
    with pytest.raises(m.Refused):
        with fresh() as value:
            original=m._meta;index=m.FIELDS.index(field)
            def changed(info):
                result=list(original(info));result[index]+=1;return tuple(result)
            monkeypatch.setattr(m,'_meta',changed)
            value.verify(deadline=value.deadline)


def test_native_security_drift_fails_even_if_metadata_projection_remains_unchanged(case,monkeypatch):
    original=m.security.snapshot;drift=False
    def snapshot(fd):
        value=original(fd)
        return {'unexpected-synthetic-security':True} if drift else value
    monkeypatch.setattr(m.security,'snapshot',snapshot)
    with pytest.raises(m.Refused,match='security_changed'):
        with fresh() as value:
            drift=True;value.verify(deadline=value.deadline)


def test_normal_return_performs_final_hash_check_and_refuses_changed_named_leaf(case):
    held=fresh()
    with pytest.raises(m.Refused):
        with held:
            leaf=case.package/case.source.pairs[1][0].relative_path
            raw=leaf.read_bytes();leaf.write_bytes(b'X'+raw[1:])
    assert not held._active and not held._guard.objects


def test_plain_and_input_semantic_mutation_are_detected_after_initial_proof(case):
    with pytest.raises(m.Refused):
        with fresh() as value:
            object.__setattr__(value.plain,'record_bytes',value.plain.record_bytes+b' ')
            value.verify(deadline=value.deadline)


def test_late_genuine_normal_return_refusal_cannot_publish_a_true_receipt(case,monkeypatch):
    held=fresh()
    with pytest.raises(m.Refused,match='changed'):
        with held as value:
            value.receipt()
            value._input_binding['first_session']='2013-01-03'
    assert not held._active


@pytest.mark.parametrize('kind',['deadline','timeout','process_timeout','foreign'])
def test_genuine_loader_failure_is_finite_and_canonical_deadline_survives_wrappers(case,monkeypatch,kind):
    def load(*args,**kwargs):
        case.events.append('reached-injected-loader')
        if kind=='deadline':raise m.Refused('deadline')
        if kind=='timeout':raise TimeoutError('SYNTHETIC_PRIVATE')
        if kind=='process_timeout':raise m.TimeoutExpired('synthetic',1)
        raise ValueError('SYNTHETIC_PRIVATE')
    monkeypatch.setattr(m.october,'load_october_order_input_package',load)
    with pytest.raises(Exception) as caught:
        with fresh():pass
    # The top-level loader boundary must be finite, not retain a raw error.
    assert m.finite(caught.value)==('deadline' if kind!='foreign' else 'genuine')
    assert 'SYNTHETIC_PRIVATE' not in str(caught.value)
    assert 'reached-injected-loader' in case.events


@pytest.mark.parametrize('issue',['count_bool','native_bool','binding_bool','missing','flag','extra','hash','roles','contribution_claim','role_bool','native_flag_int','false_flag_int'])
def test_receipt_validation_is_closed_typed_and_never_grants_admission(case,issue):
    with fresh() as value:receipt=value.receipt()
    if issue=='count_bool':receipt['source_package_object_count']=True
    elif issue=='native_bool':receipt['source_guard']['source_leaf_count']=True
    elif issue=='binding_bool':receipt['input_binding']['binding_contract']['binding_count']=True
    elif issue=='missing':receipt.pop('source_guard')
    elif issue=='flag':receipt['paper_or_live_ready']=True
    elif issue=='extra':receipt['new_claim']=True
    elif issue=='hash':receipt['input_binding_sha256']='0'*64
    elif issue=='roles':receipt['parsed_roles'].append('contributions')
    elif issue=='role_bool':receipt['role_row_counts']['evaluator_manifest']=True
    elif issue=='native_flag_int':receipt['source_guard']['full_current_native_security_checked']=1
    elif issue=='false_flag_int':receipt['point_in_time_proven']=0
    else:receipt['contributions_reparsed_by_this_helper']=True
    refused('output',lambda:m.validate_receipt(receipt))


def test_source_contains_no_old_operator_import_or_browser_provider_control_entrypoint():
    tree=ast.parse(Path(m.__file__).read_bytes())
    imports=[node.module for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)]
    assert not any(name and ('run_arv2' in name or 'inspect_arv2' in name or 'submission' in name) for name in imports)
    attrs={node.attr for node in ast.walk(tree) if isinstance(node,ast.Attribute)}
    assert not {'post','Popen','create_backtest','compile','load_key','rglob'}&attrs
    imported={alias.name.split('.')[0] for node in ast.walk(tree) if isinstance(node,ast.Import) for alias in node.names}
    assert not {'requests','socket','http','urllib','keychain','quantconnect'}&imported
    assert m.PARSED_ROLES==('evaluator_manifest','session_axis','memberships','runtime_symbol_bindings')


@pytest.mark.parametrize('fault',['path_escape','duplicate_leaf','too_many','duplicate_JSON_key'])
def test_authenticated_manifest_still_cannot_broaden_flat_source_inventory(case,monkeypatch,fault):
    record=copy.deepcopy(m._loads(case.source.pairs[-1][1],m.MAX_LEAF_BYTES,lf=True))
    if fault=='path_escape':record['objects'][0]['relative_path']='../escape'
    elif fault=='duplicate_leaf':record['objects'].append(copy.deepcopy(record['objects'][0]))
    elif fault=='too_many':record['objects']=[copy.deepcopy(record['objects'][0]) for _ in range(m.MAX_FILES)]
    raw=m.canonical(record)+b'\n'
    if fault=='duplicate_JSON_key':raw=b'{"schema":null,'+raw[1:]
    leaf=case.package/'transport-manifest.json';leaf.write_bytes(raw);leaf.chmod(0o600)
    monkeypatch.setattr(m,'SOURCE_ACTIVATION',m.pin(raw))
    with pytest.raises(m.Refused):
        with fresh():pytest.fail('unsafe manifest reached use')
    assert 'october-load' not in case.events
