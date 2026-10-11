"""Continuous successor compared with the immutable raw normalizer; synthetic."""
from collections import defaultdict
from datetime import date, datetime, time
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

import pytest

from research.target_price_revisions_qc import extended_signal as s
from research.target_price_revisions_development import raw_revision as old

CALENDAR = Path('research/target_price_revisions_qc/extended_calendar.json').read_bytes()
CAPTURE = '2026-10-11T00:00:00Z'


def identity(ticker='A', permaticker='1', **changes):
    return {"ticker": ticker, "permaticker": permaticker, "figi": None,
        "category": "Domestic Common Stock", "exchange": "NYSE", "isdelisted": "N", **changes}


def rating(event='1', day='2020-12-30', firm='F', ticker='A', **changes):
    return {"benzinga_id": event, "benzinga_firm_id": firm, "ticker": ticker,
        "date": day, "last_updated": day+'T12:00:00Z', "currency": "USD",
        "price_target_action": "raises", "price_target": "11", "previous_price_target": "10", **changes}


def action(day, ticker='A', kind='split'):
    return {"ticker": ticker, "date": day, "action": kind, "contraticker": None}


def build(rows, identities=None, actions=None):
    return s.build_frames(rows, identities or [identity()], actions or [],
                          calendar_payload=CALENDAR, capture_utc=CAPTURE)


def gold(rows, identities, actions, frame):
    import json
    cal = json.loads(CALENDAR)
    dates = cal['warmup_sessions'] + cal['valuation_sessions']
    axis = [{"session_date": day, "open_utc": datetime.combine(date.fromisoformat(day),
        time(9,30), ZoneInfo('America/New_York')).isoformat()} for day in dates]
    native = [{**row, 'security_id':'SHARADAR:'+row['permaticker'],
               'isdelisted':row['isdelisted']=='Y'} for row in identities]
    scoped_actions = [{k: row[k] for k in ('ticker','date','action')}
                      for row in actions if row['date'] >= s.SOURCE_START]
    normalized = old.normalize_raw_revisions(rows, native, scoped_actions, axis,
        cutoff_utc=frame['cutoff_utc'], capture_utc=CAPTURE, view='censored',
        action_inventory_complete=True, identity_policy=old.SHARADAR_IDENTITY_POLICY,
        action_policy=old.NOMINAL_ACTION_POLICY)
    units = defaultdict(list)
    index = dates.index(frame['session'])
    with localcontext(Context(prec=48, rounding=ROUND_HALF_EVEN)):
        for event in normalized.events:
            age = index-1-event.eligible_session_index
            if 0 <= age <= 80:
                units[(event.security_id, (type(event.benzinga_firm_id).__name__, event.benzinga_firm_id),
                       event.eligible_session_index)].append(min(Fraction(1),max(Fraction(-1),Fraction(event.raw_revision_ratio))))
        firms = defaultdict(Decimal)
        for (sid, firm, eligible), values in units.items():
            unit = median(values)
            firms[(sid,firm)] += Decimal(unit.numerator)/Decimal(unit.denominator) * Decimal(2)**(-Decimal(index-1-eligible)/Decimal(20))
        scores = defaultdict(list)
        for (sid, _), value in firms.items():scores[sid].append(value)
        return normalized, {sid: str(median(values)) for sid,values in scores.items()}


def test_cached_continuous_normalization_matches_immutable_oracle():
    rows = [rating(), rating('2',firm=12,price_target='20'),
        rating('3',firm='12',price_target='9',price_target_action='lowers'),
        rating('4',day='2021-01-04'), rating('5',day='2021-01-05',price_target=None),
        rating('6',day='2021-01-05',last_updated='2025-01-01T12:00:00Z'),
        rating('7',day='2021-12-30'), rating('8',day='2024-12-30',ticker='B'),
        rating('9',day='2025-01-02',ticker='B',currency='EUR'),
        rating('10',day='2026-10-09',price_target_action='sets')]
    rows.append(dict(rows[0]))
    identities = [identity(), identity('B','2')]
    actions = [action('2010-01-01',kind='listed'), action('2021-02-01',kind='dividend'),
               action('2022-01-03',ticker='B')]
    result = build(rows,identities,actions)
    assert len(result['frames']) == 301
    assert result['source_census']['duplicate_rows']==1
    for frame, summary in zip(result['frames'],result['normalization']):
        normalized, scores = gold(rows,identities,actions,frame)
        assert summary['refusal_counts']==dict(normalized.refusal_counts)
        assert summary['accepted_distinct_events']==len(normalized.events)
        assert {row['security_id']:row['score'] for row in frame['states'] if row['state']=='scored'}==scores


def test_global_event_conflict_never_resets_at_year_or_chunk_boundary():
    original=rating('X')
    conflict=rating('X',day='2025-01-02',price_target='30')
    result=build([original,conflict])
    assert all(row['states'][0]['state']=='unknown_input' for row in result['frames'])
    assert all(row['refusal_counts']['conflicting_native_event_id']==2 for row in result['normalization'])
    assert all(row['accepted_distinct_events']==0 for row in result['normalization'])


def test_cumulative_signal_window_actions_persist_but_future_actions_do_not_screen_past():
    result=build([rating(day='2020-12-29'),rating('2',day='2024-12-30')],actions=[action('2021-02-01')])
    first=result['frames'][0]['states'][0]
    assert first['state']=='scored'
    later=next(row for row in result['frames'] if row['session']=='2025-01-06')['states'][0]
    assert later['state']=='unknown_input' and 'corporate_action_ambiguity' in later['reasons']
    assert result['normalization'][-1]['cumulative_excluded_ticker_count']==1
    older=build([rating(day='2020-12-29')],actions=[action('1990-01-01',kind='listed')])
    assert older['frames'][0]['states'][0]['state']=='scored'
    assert older['source_census']['pre_warmup_actions_audit_only']==1


def test_missing_invalid_targets_and_current_delisting_are_never_measured_zero():
    missing=build([rating(price_target=None)])
    assert missing['frames'][0]['states'][0]['state']=='unknown_input'
    assert missing['frames'][0]['states'][0]['score'] is None
    delisted=build([rating()],identities=[identity(isdelisted='Y')])
    assert all(row['states'][0]['state']=='identity_ineligible' for row in delisted['frames'])


def test_global_identity_collision_is_not_repaired_by_relevant_ticker_filter():
    result=build([rating()],identities=[identity(),identity('UNOBSERVED','1')])
    assert result['identities'][0]['eligible'] is False
    assert result['identities'][0]['reason']=='ambiguous_snapshot_identity'


def test_multiple_observed_aliases_retain_one_ineligible_census_without_choosing_ticker():
    rows=[rating(),rating('2',ticker='B')]
    identities=[identity(),identity('B','1')]
    result=build(rows,identities=identities)
    assert result['identities']==[{'security_id':'SHARADAR:1','ticker':None,
        'eligible':False,'reason':'ambiguous_snapshot_identity'}]
    assert result['source_census']['native_identity_rows']==2
    assert result['source_census']['ambiguous_alias_identity_count']==1
    assert all(frame['states']==[{'security_id':'SHARADAR:1',
        'state':'identity_ineligible','score':None,'reasons':['ambiguous_snapshot_identity']}]
        for frame in result['frames'])
    normalized,scores=gold(rows,identities,[],result['frames'][0])
    assert not normalized.events and not scores


@pytest.mark.parametrize('change',[{'calendar_payload':CALENDAR+b' '},
    {'capture_utc':'2020-01-01T00:00:00Z'}, {'capture_utc':'2026-10-11T00:00:00'}])
def test_bound_calendar_and_capture_clock_refuse(change):
    with pytest.raises((s.SignalError, old.RawRevisionError)):
        s.build_frames([rating()],[identity()],[],**{'calendar_payload':CALENDAR,'capture_utc':CAPTURE,**change})


def test_extreme_upward_revision_ratio_is_clipped_to_the_unit_band():
    """TPR-CR23 regression: a 3.5x target raise contributes exactly +1, never 2.5.

    The independent score oracle clips the immutable normalizer's raw ratios
    to [-1, 1] before the firm median and decay; the successor must do the same.
    Issued 2020-12-29 makes the event eligible at the 2020-12-31 open, so the
    first 2021-01-04 decision sees age zero and an unscaled unit.
    """
    result = build([rating(day='2020-12-29', price_target='35', previous_price_target='10')])
    first = result['frames'][0]['states'][0]
    assert first['state'] == 'scored' and first['score'] == '1'
    normalized, scores = gold([rating(day='2020-12-29', price_target='35', previous_price_target='10')],
                              [identity()], [], result['frames'][0])
    assert scores == {'SHARADAR:1': '1'} and len(normalized.events) == 1
