"""Pure CSV framing diagnostic controls; no retained private wire read."""
import hashlib
import os
import pytest
from research.target_price_revisions_qc import extended_capture_diagnostic as d

HEADER = b"ticker,permaticker,figi,category,exchange,isdelisted\n"


@pytest.fixture(autouse=True)
def actual_io_denied(monkeypatch):
    def deny(*a,**kw):raise AssertionError('actual private/provider access forbidden in fixture')
    monkeypatch.setattr(d.capture,'_private_directory',deny)
    monkeypatch.setattr(d.capture.helper,'_production_credential',deny)
    monkeypatch.setattr(d.capture.http.client,'HTTPSConnection',deny)


def test_schema_sort_mismatch_is_counted_without_exposing_rows():
    result = d.diagnose(HEADER+b"B,2,,Domestic Common Stock,NYSE,N\nA,1,,Domestic Common Stock,NYSE,N\n")
    assert result['row_count']==2 and result['ticker_sort_descents']==1
    # The immutable parser catches its own ValueError-subclass sorting refusal
    # and closes it as structural; the independent descent count distinguishes it.
    assert result['closed_projection_refusal']=='capture CSV structural schema refused'
    assert result['original_projection_accepted'] is False
    assert set(result).isdisjoint({'rows','ticker','permaticker','category','identities'})


def test_complete_small_page_is_not_admission():
    result=d.diagnose(HEADER+b"A,1,,Domestic Common Stock,NYSE,N\n")
    assert result['original_projection_accepted'] is True
    assert result['source_input_admitted'] is result['point_in_time_data'] is False
    assert result['outcome_reads']==result['quantconnect_attempts']==0


def test_response_page_exceedance_is_not_silently_truncated():
    result=d.diagnose(HEADER+b"A,1,,Domestic Common Stock,NYSE,N\n"*10001)
    assert result['row_count']==10001 and result['rows_above_registered_page_limit']==1
    assert result['closed_projection_refusal']=='capture CSV structural schema refused'


def test_missing_required_schema_and_bad_width_are_explicit():
    result=d.diagnose(b"ticker,company\nA,one\nB,two,three\n")
    assert result['required_fields_present'] is False and result['row_width_failures']==1
    assert result['original_projection_accepted'] is False


@pytest.mark.parametrize('payload',[None,b'',b'x'*(4*1024**2+1)])
def test_byte_bound_refuses(payload):
    with pytest.raises(ValueError):d.diagnose(payload)


def test_private_wire_integrity_does_not_mistake_access_time_for_mutation(tmp_path):
    payload=HEADER+b"A,1,,Domestic Common Stock,NYSE,N\n"
    path=tmp_path/'synthetic.csv';path.write_bytes(payload);path.chmod(0o600)
    os.utime(path,(1,2))
    fd=os.open(tmp_path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        assert d._read(fd,path.name,len(payload),hashlib.sha256(payload).hexdigest())==payload
        with pytest.raises(ValueError):d._read(fd,path.name,len(payload),'0'*64)
        path.chmod(0o644)
        with pytest.raises(ValueError):d._read(fd,path.name,len(payload),hashlib.sha256(payload).hexdigest())
    finally:os.close(fd)


def test_private_wire_symlink_refuses(tmp_path):
    target=tmp_path/'synthetic.csv';target.write_bytes(HEADER);target.chmod(0o600)
    link=tmp_path/'linked.csv';link.symlink_to(target)
    fd=os.open(tmp_path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        with pytest.raises((OSError,ValueError)):d._read(fd,link.name,len(HEADER),hashlib.sha256(HEADER).hexdigest())
    finally:os.close(fd)
