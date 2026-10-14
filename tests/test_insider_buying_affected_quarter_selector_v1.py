"""Invented complete metadata-only quarter stream; no actual artifact reads."""
from __future__ import annotations

import csv
from dataclasses import replace
import io
import json
import zipfile

import pytest

from research import insider_buying_affected_quarter_selector_v1 as module


def fixture(tmp_path, *, changes=None):
    changes=changes or {};profile=module.build_retained_82q_schema_profile_candidate()
    images=[];manifest_rows=[]
    for period in module._periods():
        year,quarter=int(period[:4]),int(period[-1])
        date=f'01-{("JAN","APR","JUL","OCT")[quarter-1]}-{year}'
        sink=io.BytesIO()
        with zipfile.ZipFile(sink,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            for table in module.headers.ALLOWED_SEC_TABLES:
                names=profile.variant_for(table,year,quarter).headers
                raw=('\t'.join(names)+'\n').encode()
                if table=='SUBMISSION.tsv':
                    output=io.StringIO(newline='');writer=csv.writer(output,delimiter='\t',lineterminator='\n')
                    for index,form in enumerate(module.FORMS,start=1):
                        row=dict.fromkeys(names,'');row.update(ACCESSION_NUMBER=f'0000000001-{year%100:02d}-{index:06d}',
                            DOCUMENT_TYPE=form,FILING_DATE=date,ISSUERCIK='0000000001',ISSUERNAME='INVENTED PRIVATE ISSUER',
                            ISSUERTRADINGSYMBOL='INVENTED')
                        if period=='2006Q1' and form=='3':row['ACCESSION_NUMBER']='0000000001-05-000001'
                        if period=='2020Q4' and form=='4':row['ISSUERCIK']='1234'
                        row.update(changes.get((period,form),{}));writer.writerow([row[name] for name in names])
                    raw+=output.getvalue().encode()
                elif table=='NONDERIV_TRANS.tsv':
                    # Opaque integrity bytes; selector must not parse/project.
                    raw+=b'PRIVATE FINANCIAL FIELD SENTINEL NOT A NUMBER\n'
                archive.writestr(table,raw)
        raw=sink.getvalue();images.append(module.QuarterArchive(period,raw))
        filename=f'{period.lower()}_form345.zip';(tmp_path/filename).write_bytes(raw)
        manifest_rows.append([period,filename,module.census._expected_url(period),str(len(raw)),module._sha(raw),
            '2026-09-24T22:52:19.7647157Z',module.census._TIMESTAMP_BASIS,module.census._CAPTURE_COMMIT,module.census._SOURCE_INDEX_URL])
    output=io.StringIO(newline='');writer=csv.writer(output,quoting=csv.QUOTE_ALL,lineterminator='\r\n')
    writer.writerow(module.census._MANIFEST_HEADER);writer.writerows(manifest_rows)
    manifest=output.getvalue().encode();(tmp_path/module.census._MANIFEST_NAME).write_bytes(manifest)
    observed=module.census._census_zip_corpus(tmp_path,expected_manifest_sha256=module._sha(manifest),scope='synthetic_test_census')
    header=module.headers._preflight_ib1b_82q_headers(tmp_path,observed,profile)
    return {'intake_manifest_raw':manifest,'expected_manifest_sha256':module._sha(manifest),
        'quarter_inputs':iter(images),'expected_census_sha256':observed.sha256,
        'expected_header_preflight_sha256':header.sha256,'fixture_only':True},images


@pytest.fixture
def supplied(tmp_path):return fixture(tmp_path)


def test_all_six_forms_and_all_82_quarters_accounted_without_row_identity_or_financial_export(supplied):
    args,images=supplied;result=module.select_affected_quarters(**args);body=result.to_payload()
    assert body['counts']['quarters_scanned']==len(body['quarters'])==82
    assert body['counts']['submission_rows']==492 and body['counts']['form4_or_4a_rows']==164
    assert body['counts']['short_cik_rows']==body['counts']['short_cik_form4_or_4a_rows']==1
    assert body['counts']['accession_year_mismatch_rows']==1 and body['counts']['accession_year_mismatch_form4_or_4a_rows']==0
    assert body['affected_periods']==['2006Q1','2020Q4']
    assert body['source_form_counts']==dict.fromkeys(module.FORMS,82)
    assert body['whole_population_promotion_sha256'] is None
    assert all(value is False or type(value)is int and value==0 for value in body['authority'].values())
    assert b'INVENTED PRIVATE ISSUER' not in result.canonical_bytes()
    assert b'PRIVATE FINANCIAL FIELD SENTINEL' not in result.canonical_bytes()
    assert b'0000000001-05-000001' not in result.canonical_bytes()
    assert all(set(row)<=set(body['quarters'][0]) for row in body['quarters'])


def test_context_form_alone_selects_quarter_without_modifying_source_cik_or_bytes(tmp_path):
    args,images=fixture(tmp_path,changes={('2010Q1','5/A'):{'ISSUERCIK':'99'}})
    before=[module._sha(item.raw_bytes) for item in images]
    body=module.select_affected_quarters(**args).to_payload()
    assert '2010Q1' in body['affected_periods']
    assert body['counts']['short_cik_rows']==2 and body['counts']['short_cik_form4_or_4a_rows']==1
    assert before==[module._sha(item.raw_bytes) for item in images]


@pytest.mark.parametrize('kind',['manifest_hash','census_hash','header_hash','fixture_type','actual_mode','list_stream',
    'drop_quarter','extra_quarter','reorder','mutable_bytes','wrong_period','changed_zip'])
def test_external_anchors_types_complete_order_and_actual_fixture_boundary_are_binding(supplied,kind):
    args,images=supplied
    if kind in {'manifest_hash','census_hash','header_hash'}:
        key={'manifest_hash':'expected_manifest_sha256','census_hash':'expected_census_sha256','header_hash':'expected_header_preflight_sha256'}[kind]
        args[key]='f'*64
    elif kind=='fixture_type':args['fixture_only']=1
    elif kind=='actual_mode':args['fixture_only']=False
    elif kind=='list_stream':args['quarter_inputs']=images
    else:
        items=list(images)
        if kind=='drop_quarter':items.pop()
        elif kind=='extra_quarter':items.append(images[-1])
        elif kind=='reorder':items[0],items[1]=items[1],items[0]
        elif kind=='mutable_bytes':items[0]=module.QuarterArchive(items[0].period,bytearray(items[0].raw_bytes))
        elif kind=='wrong_period':items[0]=module.QuarterArchive('2006Q2',items[0].raw_bytes)
        else:items[0]=module.QuarterArchive(items[0].period,items[0].raw_bytes+b'changed')
        args['quarter_inputs']=iter(items)
    with pytest.raises(module.AffectedQuarterSelectorError):module.select_affected_quarters(**args)


@pytest.mark.parametrize('changes,reason',[
    ({('2006Q1','4'):{'ISSUERCIK':'0'}},'source_cik_lexical_shape_refused'),
    ({('2006Q1','4'):{'ISSUERCIK':'１２３'}},'source_cik_lexical_shape_refused'),
    ({('2006Q1','4'):{'ISSUERCIK':'12345678901'}},'source_cik_lexical_shape_refused'),
    ({('2006Q1','4'):{'FILING_DATE':'01-APR-2006'}},'source_filing_date_outside_quarter'),
    ({('2006Q1','4'):{'FILING_DATE':'2006-01-01'}},'source_filing_date_dialects_mixed'),
    ({('2006Q1','4'):{'FILING_DATE':'31-FEB-2006'}},'source_submission_decode_refused')])
def test_malformed_cik_and_source_dates_refuse_instead_of_becoming_silent_counts(tmp_path,changes,reason):
    args,_=fixture(tmp_path,changes=changes)
    with pytest.raises(module.AffectedQuarterSelectorError,match=reason):module.select_affected_quarters(**args)


def test_factory_seal_payload_copy_and_reconstruction_cannot_change_authority(supplied):
    args,_=supplied;result=module.select_affected_quarters(**args)
    body=result.to_payload();body['authority']['backtesting_ready']=True
    assert result.to_payload()['authority']['backtesting_ready'] is False
    with pytest.raises(module.AffectedQuarterSelectorError):replace(result).to_payload()
    object.__setattr__(result,'_bytes',module._raw(body))
    with pytest.raises(module.AffectedQuarterSelectorError):result.to_payload()


def test_pure_selector_has_no_file_process_credential_or_provider_interaction(supplied,monkeypatch):
    import os,subprocess
    args,_=supplied
    def refused(*args,**kwargs):pytest.fail('pure selector attempted external interaction')
    monkeypatch.setattr(os,'open',refused);monkeypatch.setattr(subprocess,'run',refused)
    assert module.select_affected_quarters(**args).to_payload()['counts']['quarters_scanned']==82


def test_aggregate_output_budget_refuses_without_truncating(supplied,monkeypatch):
    args,_=supplied;monkeypatch.setattr(module,'MAX_RESULT_BYTES',1)
    with pytest.raises(module.AffectedQuarterSelectorError,match='selector_output_bound_refused'):
        module.select_affected_quarters(**args)


@pytest.mark.parametrize('fault',['affected_list','bool_count','unselected_period','source_hash','source_clock',
    'positive_authority','coherent_stats','privacy_field'])
def test_readback_rederives_every_aggregate_and_quarter_identity_from_external_inputs(supplied,fault):
    args,images=supplied;body=module.select_affected_quarters(**args).to_payload()
    if fault=='affected_list':body['affected_periods']=['2006Q2','2020Q4']
    elif fault=='bool_count':body['counts']['overlap_anomaly_quarters']=False
    elif fault=='unselected_period':body['quarters'][1]['period']='2006Q1'
    elif fault=='source_hash':body['quarters'][1]['submission_member_sha256']='f'*64
    elif fault=='source_clock':body['quarters'][1]['local_filesystem_observation_unverified']='2006-01-01T00:00:00.0000000Z'
    elif fault=='positive_authority':body['authority']['backtesting_ready']=True
    elif fault=='privacy_field':body['quarters'][1]['issuer_cik']='PRIVATE CIK MUST NOT ENTER RESULT'
    else:
        body['quarters'][0]['accession_year_mismatch_rows']=0
        body['quarters'][1]['accession_year_mismatch_rows']=1
        body['affected_periods']=['2006Q2','2020Q4'];body['accession_year_mismatch_periods']=['2006Q2']
        body['quarters'][0]['selected_affected']=False;body['quarters'][1]['selected_affected']=True
    body['quarters_sha256']=module._sha(module._raw(body['quarters']))
    args['quarter_inputs']=iter(images)
    with pytest.raises(module.AffectedQuarterSelectorError,match='input_derived_selector_payload_differs'):
        module.validate_affected_selection_payload(body,**args)
