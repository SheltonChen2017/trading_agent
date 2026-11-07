"""Canonical optional seams; fabricated source/key/wire, denied network."""
import importlib.util
from pathlib import Path
import pytest

ROOT=Path('/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest')

# These cases need the lane's pinned physical root: code manifests, protocol
# paths and sibling imports are built from the designated macOS worktree.
_DESIGNATED_ROOT_ONLY = pytest.mark.skipif(
    Path.cwd().resolve() != ROOT,
    reason=(
        "the lane pins its physical root, code manifest and protocol paths to the "
        "designated macOS worktree; this host is not it, see the lane record SI-CR18-005"
    ),
)

def proposed_module():
    from scripts import capture_short_interest_native_daily_active as module
    return module

def existing_fictional_helpers():
    spec=importlib.util.spec_from_file_location('fictional_producer_helpers',ROOT/'tests/test_short_interest_native_daily_active_capture.py')
    helpers=importlib.util.module_from_spec(spec); spec.loader.exec_module(helpers)
    return helpers

@_DESIGNATED_ROOT_ONLY
def test_proposed_transport_remote_refusal_is_zero_wire_and_zero_HTTP_counter(monkeypatch):
    from scripts.short_interest_lane_batch_guard import LaneBatchRefusal
    helpers=existing_fictional_helpers(); runtime=proposed_module()
    monkeypatch.setattr(helpers,'runtime',runtime)
    case=helpers.setup(monkeypatch); callbacks=[]
    def refused(opener,request,maximum,*,on_http_start):
        callbacks.append('guard-refused-before-http')
        raise LaneBatchRefusal('matching_actual_remote_advanced_or_ambiguous')
    case[2]['transport']=refused
    result=helpers.run(case)
    assert callbacks and case[5]==[] and result['http_invocations']==0
    assert result['complete_frozen_sequence'] is False
    assert all(value['http_invoked'] is False for value in result['attempts'])

@_DESIGNATED_ROOT_ONLY
def test_proposed_transport_callback_and_typed_report_observer_preserve_full_fictional_sequence(monkeypatch):
    from research.short_interest_etf.native_daily_active_reference import DailyActiveReferenceQualification
    helpers=existing_fictional_helpers(); runtime=proposed_module()
    monkeypatch.setattr(helpers,'runtime',runtime)
    case=helpers.setup(monkeypatch); observed=[]; starts=[]
    def transport(opener,request,maximum,*,on_http_start):
        on_http_start(); starts.append(request.full_url)
        return runtime._http(opener,request,maximum)
    def observe(report):
        assert type(report) is DailyActiveReferenceQualification
        assert report._plan is case[0] and report._index is case[1]
        observed.append(report.to_payload()['day_ordinal'])
    case[2].update(transport=transport,on_qualified_day=observe,lane_guard=lambda *args:None)
    result=helpers.run(case)
    assert result['complete_frozen_sequence'] is True
    assert result['http_invocations']==len(starts)==len(case[5])==1169
    assert sorted(observed)==list(range(1,1170))

@_DESIGNATED_ROOT_ONLY
def test_default_transport_and_guard_path_remains_fictional_full_sequence(monkeypatch):
    helpers=existing_fictional_helpers(); runtime=proposed_module()
    monkeypatch.setattr(helpers,'runtime',runtime)
    case=helpers.setup(monkeypatch); result=helpers.run(case)
    assert result['complete_frozen_sequence'] is True and result['http_invocations']==len(case[5])==1169
