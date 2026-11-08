"""Synthetic quarantine economics/catalog regressions; no actual data or QC."""
import ast
import copy
import dataclasses
import hashlib
import inspect
import json
import sys
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from research.analyst_revisions_v2_qc import newrule_five_case_quarantine_targets as m
from research.analyst_revisions_v2_qc import newrule_comparison_targets as old

D = Decimal
PIN = 'a' * 64
ERRORS = (old.NewruleError, m.policy.NewruleError)


def books(*, shared=False, score=True):
    return tuple(old.Book(universe, f'ETF-{universe}', tuple(old.Member(
        f'SID-{i}' if shared else f'SID-{universe}-{i}', f'LABEL-{i}', f'LABEL-{i}',
        D('0.1'), f'ID-{i}' if shared else f'ID-{universe}-{i}', f'NAME-{i}',
        D(10000-i), D(i+1) if score else None) for i in range(10)))
        for universe in old.UNIVERSES)


def replace(value, book_index=0, row_index=0, **changes):
    book = value[book_index]
    members = list(book.members)
    members[row_index] = dataclasses.replace(members[row_index], **changes)
    result = list(value)
    result[book_index] = dataclasses.replace(book, members=tuple(members))
    return tuple(result)


def synthetic_binding(index):
    figi = 'BBG' + str(index).zfill(9)
    return m.figi.build_preliminary_qc_figi_binding(
        security_id='sharadar-composite-figi-'+figi, issuer_id=f'synthetic-issuer-{index}',
        composite_figi=figi, listing_id=f'synthetic-listing-{index}',
        diagnostic_current_ticker=f'SYNTH{index}', diagnostic_exchange_mic='XNYS',
        candidate_first_session='2020-12-31', candidate_last_session='2026-10-13',
        source_snapshot_available_at='2026-10-01T00:00:00.000000Z',
        source_row_sha256=m.digest({'source':index}),
        identity_evidence_sha256=m.digest({'evidence':index}),
        security_master_admission_sha256=m.ADMISSION_SHA256,
        admitted_mapping_inventory_sha256='b'*64, admitted_mapping_count=7)


@pytest.fixture
def policy(monkeypatch):
    rows = tuple(synthetic_binding(i) for i in range(7))
    stream = hashlib.sha256(b''.join(m.canonical(row)+b'\n' for row in rows)).hexdigest()
    for module in (m,m.policy):
        monkeypatch.setattr(module, 'ORIGINAL_BINDING_COUNT', len(rows))
        monkeypatch.setattr(module, 'ORIGINAL_BINDING_STREAM_SHA256', stream)
        monkeypatch.setattr(module, 'QUARANTINED_WHOLE_BINDING_SHA256S',
            tuple(m.digest(row) for row in rows[:5]))
    catalog = m.make_quarantine_catalog(rows)
    return rows, catalog, m.digest(catalog)


def build(policy, value=None, *, count=6, arm=0):
    _, catalog, pin = policy
    return m.build_target(books() if value is None else value, universe_count=count,
        ar_percent=arm, source_snapshot_sha256=PIN, quarantine_catalog=catalog,
        expected_quarantine_catalog_sha256=pin)


def baseline(value, *, count=6, arm=0):
    return old.build_target(value, universe_count=count, ar_percent=arm,
        source_snapshot_sha256=PIN)


def weights(target):
    return {sid: weight for sid, _, weight in target.weights}


def selected_books(policy, *, shared=False):
    value = books(shared=shared)
    for i, row in enumerate(policy[0][:5]):
        for book_index in range(8) if shared else [i]:
            value = replace(value, book_index=book_index, row_index=i,
                economic_id=row['security_id'])
    return value


def total(target):
    with localcontext() as context:
        context.prec = 96
        return sum((weight for _, _, weight in target.weights), D(0))


@pytest.mark.parametrize('count',[6,8])
@pytest.mark.parametrize('arm',[0,100,200])
@pytest.mark.parametrize('shared',[False,True])
@pytest.mark.parametrize('score',[False,True])
def test_all_unselected_quarantine_weights_exactly_match_frozen_baseline(policy,count,arm,shared,score):
    value = books(shared=shared,score=score)
    result = build(policy,value,count=count,arm=arm)
    expected = baseline(value,count=count,arm=arm)
    assert result.weights == expected.weights
    assert result.input_books_sha256 == expected.input_books_sha256
    assert total(result) == D('.98')
    record = result.record()
    assert record['evidence_epoch'] == m.RESEARCH_EPOCH_ID
    assert all(record[key] is False for key in m.FALSE_FLAGS)
    assert record['quarantine_ledger']['transferred_to_own_etf_weight'] == '0'
    assert result.target_sha256 != expected.target_sha256


@pytest.mark.parametrize('count',[6,8])
@pytest.mark.parametrize('arm',[0,100,200])
@pytest.mark.parametrize('shared',[False,True])
def test_exact_post_tilt_weight_goes_only_to_own_etf_no_name_promotion(policy,count,arm,shared):
    value = selected_books(policy,shared=shared)
    result = build(policy,value,count=count,arm=arm)
    before = baseline(value,count=count,arm=arm)
    denied = set(m.denied_security_ids(policy[1],expected_sha256=policy[2]))
    assert not denied.intersection(weights(result))
    assert total(result) == D('.98')
    old_stocks = {sid:weight for sid,kind,weight in before.weights if kind=='stock'}
    new_stocks = {sid:weight for sid,kind,weight in result.weights if kind=='stock'}
    assert new_stocks == {sid:weight for sid,weight in old_stocks.items() if sid not in denied}
    with localcontext() as context:
        context.prec=96
        assert sum((weight for sid,weight in old_stocks.items() if sid in denied),D(0)) == D(
            result.record()['quarantine_ledger']['transferred_to_own_etf_weight'])
        for index,(universe,rows) in enumerate(result.post_tilt_sleeve_weights):
            transfer=sum((weight for sid,weight in rows if sid in denied),D(0))
            etf=value[index].own_etf_id
            assert weights(result).get(etf,D(0)) == weights(before).get(etf,D(0))+transfer
            diagnostic=result.record()['sleeves'][index]
            assert D(diagnostic['quarantined_post_tilt_weight'])==transfer
            assert D(diagnostic['own_etf_weight'])==weights(result).get(etf,D(0))
            assert D(diagnostic['surviving_stock_weight'])+D(diagnostic['own_etf_weight'])==old.sleeve_budgets(count)[index]
    assert all(0<weight<=old.STOCK_CAP for weight in new_stocks.values())
    # The pre-quarantine final sleeve aggregate is the entire frozen stock result,
    # not baseline equal slots, even in AR200 and shared-cap cells.
    reconstructed={}
    with localcontext() as context:
        context.prec=96
        for _,rows in result.post_tilt_sleeve_weights:
            for sid,weight in rows: reconstructed[sid]=reconstructed.get(sid,D(0))+weight
    assert reconstructed==old_stocks


def test_transfer_uses_final_tilt_not_equal_slot(policy):
    value=selected_books(policy)
    tilted=build(policy,value,arm=200)
    plain=build(policy,value,arm=0)
    first=tilted.record()['sleeves'][0]
    assert D(first['quarantined_post_tilt_weight'])!=D(plain.record()['sleeves'][0]['quarantined_post_tilt_weight'])
    assert D(first['quarantined_post_tilt_weight'])==D('1e-30')


def test_no_promotion_of_eleventh_name(policy):
    value=selected_books(policy)
    book=value[0]
    added=old.Member('SID-extra','EXTRA','EXTRA',D('.01'),'ID-extra','EXTRA',D(1),D(99))
    members=tuple(dataclasses.replace(row,reported_weight=D('.099')) for row in book.members)+(added,)
    value=(dataclasses.replace(book,members=members),)+value[1:]
    result=build(policy,value,arm=200)
    assert 'ID-extra' not in weights(result)
    assert result.record()['sleeves'][0]['selected_count']==10


def test_xle_exception_and_all_original_refusals_preserved(policy):
    value=selected_books(policy)
    value=tuple(dataclasses.replace(book,members=tuple(dataclasses.replace(row,score=None)
        for row in book.members)) for book in value)
    result=build(policy,value,arm=100)
    diagnostics=result.record()['sleeves']
    assert all('positive_score_count_below_five' in row['refusals'] for row in diagnostics[:5])
    assert diagnostics[5]['refusals']==[]
    assert result.weights==baseline(value,arm=100).weights


def test_unselected_bad_row_and_seventh_eighth_book_not_dropped(policy):
    value=replace(books(),book_index=7,row_index=9,reported_weight=D('-1'))
    with pytest.raises(old.NewruleError,match='negative_reported_weight'):
        build(policy,value,count=6)


@pytest.mark.parametrize('field,value',[
    ('economic_id','ETF-SPY'),('reported_weight',D('NaN')),('market_cap',D('Infinity')),
    ('score',D('NaN'))])
def test_full_validation_precedes_quarantine(policy,field,value):
    input_books=replace(selected_books(policy),**{field:value})
    with pytest.raises(old.NewruleError): build(policy,input_books)


def test_catalog_builders_agree_defensive_copy_and_exact_original_ids(policy):
    rows,catalog,pin=policy
    assert m.make_quarantine_catalog_from_bindings(rows[:5])==catalog
    assert m.validate_quarantine_catalog(catalog,expected_sha256=pin)==catalog
    copy_catalog=m.validate_quarantine_catalog(catalog,expected_sha256=pin)
    copy_catalog['quarantined_bindings'][0]['security_id']='MUTATED'
    assert catalog['quarantined_bindings'][0]['security_id']==rows[0]['security_id']
    assert m.denied_security_ids(catalog,expected_sha256=pin)==tuple(row['security_id'] for row in rows[:5])


@pytest.mark.parametrize('change',['reorder','duplicate','extra','missing','forged_id','wrong_whole','bool_flag','wrong_epoch','extra_key','wrong_stream','bool_count'])
def test_catalog_refuses_changed_original_bindings_or_policy(policy,change):
    rows,catalog,pin=policy
    candidate=copy.deepcopy(catalog)
    selected=candidate['quarantined_bindings']
    if change=='reorder': selected.reverse()
    elif change=='duplicate': selected[-1]=selected[0]
    elif change=='extra': selected.append(selected[0])
    elif change=='missing': selected.pop()
    elif change=='forged_id': selected[0]['security_id']='FORGED'
    elif change=='wrong_whole': selected[-1]=rows[5]
    elif change=='bool_flag': candidate['point_in_time_proven']=0
    elif change=='wrong_epoch': candidate['evidence_epoch']='OTHER'
    elif change=='extra_key': candidate['authorization']=True
    elif change=='wrong_stream': candidate['original_binding_stream_sha256']='f'*64
    elif change=='bool_count': candidate['original_binding_count']=True
    with pytest.raises(ERRORS):
        m.validate_quarantine_catalog(candidate,expected_sha256=m.digest(candidate))


@pytest.mark.parametrize('change',['missing','order','duplicate','unselected_mutation'])
def test_full_census_builder_refuses_all_rows_changes(policy,change):
    rows,_,_=policy
    value=copy.deepcopy(list(rows))
    if change=='missing': value.pop()
    elif change=='order': value.reverse()
    elif change=='duplicate': value[-1]=value[-2]
    else:
        value[-1]['diagnostic_current_ticker']='CHANGED'
        seed=dict(value[-1]);seed.pop('row_sha256')
        value[-1]['row_sha256']=m.digest(seed)
    with pytest.raises(old.NewruleError): m.make_quarantine_catalog(value)


def test_expected_catalog_pin_is_binding_not_authorization_boolean(policy):
    with pytest.raises(ERRORS,match='quarantine_catalog_pin'):
        m.validate_quarantine_catalog(policy[1],expected_sha256='0'*64)
    with pytest.raises(ERRORS,match='digest'):
        m.validate_quarantine_catalog(policy[1],expected_sha256=True)


def test_target_tampering_refuses(policy):
    target=build(policy,selected_books(policy),arm=200)
    forged=dataclasses.replace(target,quarantine_ledger_bytes=b'{}')
    with pytest.raises(old.NewruleError,match='target_binding'):forged.record()
    forged=dataclasses.replace(target,post_tilt_sleeve_weights=())
    with pytest.raises(old.NewruleError,match='target_binding'):forged.record()


def test_old_concrete_member_and_book_types_are_exact_aliases():
    assert m.Member is old.Member and m.Book is old.Book


@pytest.mark.parametrize('count',[6,8])
@pytest.mark.parametrize('arm',[0,100,200])
@pytest.mark.parametrize('scores',[
    (D(1),)*10,
    (D(-2),D(-1),D(0),D(1),D(1),D(2),D(3),D(4),D(5),D(6)),
    tuple(D(i//2+1) for i in range(10)),
])
def test_score_ties_zero_negative_and_cross_sleeve_caps_preserve_baseline(policy,count,arm,scores):
    value=books(shared=True)
    value=tuple(dataclasses.replace(book,members=tuple(dataclasses.replace(row,score=scores[i])
        for i,row in enumerate(book.members))) for book in value)
    result=build(policy,value,count=count,arm=arm)
    assert result.weights==baseline(value,count=count,arm=arm).weights


def test_no_post_quarantine_exposure_can_reenter_later_sleeve_shared_cap(policy):
    # Denial runs after every sleeve: its freed cap cannot promote or expand a
    # later sleeve's position, even when the earlier denied contribution was tiny.
    value=selected_books(policy,shared=True)
    result=build(policy,value,count=8,arm=200)
    before=baseline(value,count=8,arm=200)
    denied=set(m.denied_security_ids(policy[1],expected_sha256=policy[2]))
    assert {sid:weight for sid,kind,weight in result.weights if kind=='stock'}=={
        sid:weight for sid,kind,weight in before.weights if kind=='stock' and sid not in denied}


def test_constructor_algorithm_exact_bounded_inverse_to_frozen_baseline():
    source=inspect.getsource(m.build_target)
    source=source.replace('def build_target(books, *, universe_count, ar_percent, source_snapshot_sha256,\n'
        '                 quarantine_catalog, expected_quarantine_catalog_sha256):',
        'def build_target(books, *, universe_count, ar_percent, source_snapshot_sha256):',1)
    preflight='''    try:
        denied = frozenset(denied_security_ids(quarantine_catalog,
            expected_sha256=expected_quarantine_catalog_sha256))
    except policy.NewruleError:
        raise NewruleError("quarantine_catalog") from None
'''
    assert source.count(preflight)==1
    source=source.replace(preflight,'',1)
    source=source.replace('        final_sleeve_rows = [dict(baseline) for baseline, _ in sleeve_rows]\n','',1)
    source=source.replace('            for sleeve_ordinal, (baseline, scores) in enumerate(sleeve_rows):',
        '            for baseline, scores in sleeve_rows:',1)
    source=source.replace('                final_sleeve_rows[sleeve_ordinal] = updated\n','',1)
    # The one additional end-of-construction block is the explicit new policy.
    begin=source.index('        # Preserve complete construction and shared-cap tilt before denying exposure.')
    end=source.index('        require(all(0 < value <= STOCK_CAP for value in stocks.values()), "stock_cap")',begin)
    source=source[:begin]+source[end:]
    baseline_source=inspect.getsource(old.build_target)
    source=source[:source.index('        target = Target(')]+baseline_source[
        baseline_source.index('        payload = canonical(diagnostics)'):]
    assert ast.dump(ast.parse(source),include_attributes=False)==ast.dump(
        ast.parse(baseline_source),include_attributes=False)


def test_core_policy_is_stdlib_only_and_snapshot_proofs_not_freshness_claims():
    tree=ast.parse(inspect.getsource(m.policy))
    imports=[node for node in ast.walk(tree) if isinstance(node,(ast.Import,ast.ImportFrom))]
    assert all(isinstance(node,ast.Import) and all(alias.name in ('hashlib','json')
        for alias in node.names) for node in imports)
    assert m.profile_record()['catalog_stream_commitment']=='original_identity_pin_not_fresh_catalog_authentication_claim'


@pytest.mark.parametrize('bad',[None,True,{},[None]*5,[{'security_id':'SYNTH','bad':float('nan')}]*5])
def test_five_builder_invalid_type_or_nonfinite_json_finite_refusal(bad):
    with pytest.raises(m.policy.NewruleError):m.make_quarantine_catalog_from_bindings(bad)


def test_public_ledger_contains_only_fixed_aggregate_fields(policy):
    result=build(policy,selected_books(policy,shared=True),arm=200)
    ledger=result.record()['quarantine_ledger']
    assert set(ledger)=={'schema','quarantined_binding_count','selected_sleeve_occurrence_count',
        'positive_sleeve_occurrence_count','transferred_unique_stock_count',
        'transferred_to_own_etf_weight','quarantined_target_count','gross_weight','cash_weight',
        'replacement_name_promotions','renormalization_performed',*m.FALSE_FLAGS}
    raw=m.canonical(ledger)
    assert b'sharadar-composite' not in raw and b'ETF-' not in raw
    assert ledger['transferred_unique_stock_count']<=5
    assert ledger['positive_sleeve_occurrence_count']<=ledger['selected_sleeve_occurrence_count']


def test_fixed_five_commitments_match_frozen_original_case_policy():
    source=Path('scripts/arv2_r336_original_identity_ownership.py').read_text()
    tree=ast.parse(source)
    values={node.targets[0].id:ast.literal_eval(node.value) for node in tree.body
        if isinstance(node,ast.Assign) and len(node.targets)==1
        and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='WHOLes'}
    assert m.QUARANTINED_WHOLE_BINDING_SHA256S==values['WHOLes']


def test_original_stream_serialization_is_exact_independent_frozen_helper(policy):
    from research.analyst_revisions_v2_qc import accepted_risk_order_level_input_runtime as inputs
    assert m.ORIGINAL_BINDING_STREAM_SHA256==inputs._stream_hash(policy[0])


def test_no_operational_or_machine_dependency():
    source=inspect.getsource(m)
    tree=ast.parse(source)
    roots={node.names[0].name.split('.')[0] for node in ast.walk(tree) if isinstance(node,ast.Import)}
    assert roots<={'dataclasses','hashlib','json','newrule_comparison_targets',
        'accepted_risk_preliminary_qc_figi','newrule_five_case_quarantine_policy'}
    assert not any(isinstance(node,ast.Call) and isinstance(node.func,ast.Name)
        and node.func.id in {'open','eval','exec','compile','__import__'} for node in ast.walk(tree))
    assert 'assistant.dispatch_fence' not in sys.modules
