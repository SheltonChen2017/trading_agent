"""Exactly four inert AK metadata tests; no source book or operation."""
import ast
import builtins
import copy
import hashlib
import inspect
import os
from pathlib import Path
import socket
import subprocess

from scripts import arv2_r298_ak_source_binding as m
from scripts import arv2_r298_ae_source_binding as ae
from research.analyst_revisions_v2_qc import newrule_native_price_source_diagnostic as native
from research.analyst_revisions_v2_qc import newrule_native_price_book_publication as publication


def test_AK_actual_parser_UI_job_and_book_metadata_form_one_exact_source_join():
    fact,summary,receipt=m.observed_fact(),m.expected_source_summary(),m.expected_publication_receipt()
    assert fact['metadata_parser_actual_exit']==0 and fact['project_id']==38522505
    assert fact['backtest_id']=='d366867e9ca3a657baea9beb9b660b41'
    assert fact['source_projection_sha256']=='65cebf606f2867b58ae203b186f3ce7ec0701fc2f3c5f576f13adef46ca5624a'
    assert fact['source_profile_sha256']=='3e985a9d6951adf53aa058fb4116f26b4c90bd7a881e9c32c9945306363279f1'
    assert fact['original_UI_input_pin']=={'byte_count':6053,
        'sha256':'ec3627673a9c54b497ea42376abd2eb3d2ea4e6b0158ecba3e599a07ecaf90f5'}
    assert fact['source_summary_sha256']==m._digest(summary)==receipt['source_summary_sha256']
    assert fact['scope_sha256']==receipt['scope_sha256']
    assert fact['source_specification_sha256']==summary['specification_sha256']==receipt['source_specification_sha256']
    assert summary['private_book_sha256']==receipt['book_sha256']=='b149c9c659ef53084782e25ee18ffc4133bebb063180958651cafc69725c7299'
    assert summary['private_book_byte_count']==receipt['book_byte_count']==1313871
    assert summary['valid_cell_count']==sum(row['valid_cell_count'] for row in summary['per_selected'])==2711
    assert summary['unpriced_cell_count']==sum(row['absent_cell_count'] for row in summary['per_selected'])==4549
    assert summary['required_cell_count']==2711+4549==5*1452


def test_AK_metadata_validates_but_never_grants_source_master_PIT_or_trading_admission():
    fact,summary,receipt=m.observed_fact(),m.expected_source_summary(),m.expected_publication_receipt()
    assert native.validate_summary(summary)==summary
    scope=publication.make_scope(38522505,fact['source_specification_sha256'],'R326-20261027-AH')
    assert publication.validate_receipt(receipt,frozen_scope=scope,
        expected_specification=ae.expected_specification(),expected_summary=summary)==receipt
    assert fact['observed_UI_algorithm_completed'] is True and fact['technical_publication_authenticated'] is True
    assert fact['REST_terminal_or_compile_id_observed'] is False
    for key in ('price_coverage_proven','source_priority_admitted','permanent_security_master_proven',
        'point_in_time_proven','strategy_result_accepted','paper_or_live_ready'):
        assert fact[key] is False
    assert all(summary[key] is False for key in native.FALSE_FLAGS)
    assert all(receipt[key] is False for key in publication.FALSE_FLAGS)
    assert receipt['save_returned_true'] is receipt['readback_equal'] is True
    assert receipt['independent_remote_durability_proven'] is False


def test_AK_accessors_return_fresh_independent_nested_metadata_copies():
    before=m.profile_record()
    fact,summary,receipt=m.observed_fact(),m.expected_source_summary(),m.expected_publication_receipt()
    fact['original_UI_input_pin']['sha256']='f'*64
    summary['per_selected'][0]['whole_binding_sha256']='f'*64
    receipt['book_sha256']='f'*64
    assert m.profile_record()==before
    assert m.observed_fact()['original_UI_input_pin']['sha256']!='f'*64
    assert m.expected_source_summary()['per_selected'][0]['whole_binding_sha256']!='f'*64
    assert m.expected_publication_receipt()['book_sha256']!='f'*64
    assert before['native_book_content_exported'] is before['fresh_read_or_operation_granted'] is False


def test_AK_public_source_pin_and_accessor_no_IO_boundary(monkeypatch):
    raw=Path(m.__file__).read_bytes()
    assert hashlib.sha256(raw).hexdigest()=='2eab16f58809f2af9eb10b1507a04796c3630c555cb0689acf61b2cdea4737ce'
    tree=ast.parse(raw)
    assert not any(isinstance(node,(ast.Import,ast.ImportFrom)) and any(
        alias.name in ('socket','subprocess','requests','os','pathlib') for alias in node.names)
        for node in ast.walk(tree))
    def deny(*args,**kwargs):raise AssertionError('inert anchor attempted DATA/QC/host I/O')
    with monkeypatch.context() as patch:
        for obj,name in ((builtins,'open'),(os,'open'),(Path,'read_bytes'),(Path,'read_text'),
                (socket,'create_connection'),(subprocess,'Popen'),
                (native.NativePriceSourceDiagnostic,'prepare'),(publication.SpecificSourceBookNamespace,'publish')):
            patch.setattr(obj,name,deny)
        assert m.profile_record()['source_summary_sha256']=='88bac1c6d26fa32b92bae1f770f273d8858aae7588b3c1e1a83c8957327aeb7e'
        assert len(m.expected_source_summary()['per_selected'])==5
        assert m.observed_fact()['metadata_parser_actual_exit']==0
        assert m.expected_publication_receipt()['publication_API_checks_complete'] is True
