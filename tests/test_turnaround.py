from dataclasses import replace
from datetime import date, datetime, timedelta
from io import BytesIO
import random

import pytest
from pypdf import PdfReader
from streamlit.testing.v1 import AppTest

from domain.models import Diagnostics, Flight, KST, Movement, Offsets, Settings
from engine.demand import analyze, cell_jobs
from engine.turnaround import build_jobs
from normalization.flights import actual_datetime, movement_context, normalize
from services.analysis import load_contract, run_analysis
from services.planner import plan
from tests.fixtures import VERIFIED, demo_result
from ui.url_state import decode, encode

BASE = datetime(2026, 10, 26, tzinfo=KST)
CONTRACT = replace(VERIFIED, actual_date_policy='bounded_early_180', actual_query_padding_days=1)


def settings(**kwargs):
    return Settings('RKSI', BASE.date(), BASE.date(), mode='custom', basis='actual',
                    airlines=('JJA',), quick_turn=True, **kwargs)


def flight(key, direction, minute, **kwargs):
    ref = BASE+timedelta(minutes=minute)
    offsets = Offsets(-20, 30, 40) if direction == 'arr' else Offsets(-50, 10, 20)
    f = Flight(key, direction, 'JJA'+key, 'RKSI', 'RKPC', ref, ref, ref, 'actual', (), (), '', ('',''),
               ref+timedelta(minutes=offsets.start), ref+timedelta(minutes=offsets.end),
               ref+timedelta(minutes=offsets.reusable), registration='HLTEST', spot='101')
    return replace(f, **kwargs)


def result(fs, s=None, **kwargs):
    return analyze(s or settings(), tuple(fs), Diagnostics(), BASE, BASE, **kwargs)


@pytest.mark.parametrize('clock,expected', [
    ('0700', '2026-10-26 07:00'), ('0659', '2026-10-27 06:59'),
    ('2300', '2026-10-26 23:00'), ('1100', '2026-10-26 11:00'),
])
@pytest.mark.parametrize('status', ['ARR', 'DLA'])
def test_date_rule_has_inclusive_three_hour_early_boundary_and_ignores_status(clock, expected, status):
    actual, warning = actual_datetime({'blockOnTime':clock, 'arrStatus':status}, 'arr', BASE.replace(hour=10), CONTRACT)
    assert actual.strftime('%Y-%m-%d %H:%M') == expected
    assert warning.startswith('실제 날짜 추정')


def test_date_rule_midnight_and_explicit_date_priority():
    value, _ = actual_datetime({'blockOnTime':'2351'}, 'arr', BASE.replace(minute=5), CONTRACT)
    assert value == BASE-timedelta(minutes=9)
    value, warning = actual_datetime({'blockOnTime':'202610271100'}, 'arr', BASE.replace(hour=10), CONTRACT)
    assert value == BASE+timedelta(days=1, hours=11) and warning is None
    value, warning = actual_datetime({'blockOnTime':'1100','blockOnDate':'20261027'}, 'arr', BASE.replace(hour=10), CONTRACT)
    assert value == BASE+timedelta(days=1, hours=11) and warning is None
    assert load_contract().actual_date_policy == 'bounded_early_180'


@pytest.mark.parametrize('interval', [30,60])
def test_turn_replaces_double_occupancy_without_changing_flight_counts(interval):
    fs = [flight('1','arr',600), flight('2','dep',640)]
    r = result(fs,settings(interval=interval))
    old = result(fs, replace(settings(interval=interval), quick_turn=False))
    assert r.maximum == 1 and old.maximum == 2
    assert len(r.jobs) == r.diagnostics.quick_turn_pairs == 1
    assert len(r.flights) == 2
    assert sum(c.dep_count for c in r.cells) == sum(c.arr_count for c in r.cells) == 1
    assert r.jobs[0].reusable == BASE+timedelta(minutes=660)
    for c in r.cells:
        assert c.maximum == c.dep_active+c.arr_active+c.turn_active
        assert len(cell_jobs(r,c.index,'peak')) == c.maximum


@pytest.mark.parametrize('interval', [30,60])
def test_waiting_is_continuous_and_only_departure_travel_is_added(interval):
    arr = flight('1','arr',600, reusable=BASE+timedelta(minutes=900))
    dep = flight('2','dep',700)
    r = result([arr, dep],settings(interval=interval))
    job = r.jobs[0]
    assert job.start == BASE+timedelta(minutes=580)
    assert job.end == BASE+timedelta(minutes=710)
    assert job.reusable == BASE+timedelta(minutes=720)
    assert any(s.start <= BASE+timedelta(minutes=645) < s.end and s.turn == 1 for s in r.segments)
    assert sum(r.daily_crew_minutes) == 140
    assert sum(r.histogram_minutes.values()) == 1440


def test_arrival_can_finish_later_than_departure():
    arr = flight('1','arr',600, end=BASE+timedelta(minutes=740), reusable=BASE+timedelta(minutes=750))
    r = result([arr,flight('2','dep',640)])
    assert r.jobs[0].end == BASE+timedelta(minutes=740)
    assert r.jobs[0].reusable == BASE+timedelta(minutes=750)


@pytest.mark.parametrize('gap,limit,paired', [(0,100,False),(100,100,True),(101,100,False),(360,360,True),(361,360,False)])
def test_turn_limit_boundaries(gap,limit,paired):
    r = result([flight('1','arr',600),flight('2','dep',600+gap)],settings(turn_limit=limit))
    assert r.diagnostics.quick_turn_pairs == int(paired)


@pytest.mark.parametrize('kwargs', [{'registration':''},{'registration':'OTHER'}, {'spot':''}, {'spot':'102'},
                                  {'actual':None,'reference_source':'fallback'}])
def test_missing_mismatched_and_fallback_flights_are_not_paired(kwargs):
    r = result([flight('1','arr',600),flight('2','dep',640,**kwargs)])
    assert r.diagnostics.quick_turn_pairs == 0 and len(r.jobs) == 2


def test_inferred_dates_allowed_and_conflicting_candidates_not_guessed():
    arr = flight('1','arr',600,reference_source='actual_inferred')
    dep = flight('2','dep',640,reference_source='actual_inferred')
    assert result([arr,dep]).diagnostics.quick_turn_pairs == 1
    assert result([arr,replace(arr,key='3',reference=arr.reference+timedelta(minutes=1),actual=arr.actual+timedelta(minutes=1)),dep]).diagnostics.quick_turn_pairs == 0
    assert result([arr,dep,replace(dep,key='4')]).diagnostics.quick_turn_pairs == 0


def test_repeated_rotations_pair_one_to_one_and_ignore_input_order():
    fs = [flight('1','arr',600),flight('2','dep',640),flight('3','arr',900),flight('4','dep',940)]
    first = result(fs)
    second = result(list(reversed(fs)))
    assert first.diagnostics.quick_turn_pairs == 2
    assert first.jobs == second.jobs
    assert len({f.key for job in first.jobs for f in job.flights}) == 4


@pytest.mark.parametrize('actual,minute', [(True,620),(False,300)])
def test_unselected_or_uncertain_intermediate_movement_blocks_connection(actual,minute):
    m = Movement('unselected','RKSI','dep','HLTEST','101',BASE+timedelta(minutes=minute),actual)
    r = result([flight('1','arr',600),flight('2','dep',640)],context=(m,))
    assert r.diagnostics.quick_turn_pairs == 0
    assert len(r.flights) == 2 and sum(c.dep_count for c in r.cells) == 1


@pytest.mark.parametrize('interval', [30,60])
def test_boundary_pair_is_built_before_window_filter(interval):
    r = result([flight('1','arr',-41),flight('2','dep',59)],settings(interval=interval))
    assert r.cells[0].turn_active == 1
    assert r.segments[0].start == BASE and r.segments[0].total == 1
    assert r.diagnostics.quick_turn_pairs == 1 and len(r.flights) == 2
    assert sum(c.arr_count for c in r.cells) == 0 and sum(c.dep_count for c in r.cells) == 1


@pytest.mark.parametrize('interval', [30,60])
def test_random_turns_match_independent_occupancy_and_integral(interval):
    rng = random.Random(774)
    fs=[];intervals=[]
    for i in range(25):
        minute=rng.randint(-180,1500);gap=rng.randint(1,160)
        arr=flight(f'a{i}','arr',minute,registration=f'HL{i}')
        dep=flight(f'd{i}','dep',minute+gap,registration=f'HL{i}')
        if i%4==0:
            dep=replace(dep,actual=None,reference_source='fallback')
        fs.extend((arr,dep))
        if gap<=100 and dep.actual is not None:
            intervals.append((min(arr.start,dep.start),max(arr.end,dep.end)+timedelta(minutes=10)))
        else:
            intervals.extend(((arr.start,arr.reusable),(dep.start,dep.reusable)))
    r=result(fs,settings(interval=interval))
    for cell in r.cells:
        points=sorted({cell.start,cell.end,*[t for pair in intervals for t in pair if cell.start<t<cell.end]})
        expected=max((sum(a<=lo+(hi-lo)/2<b for a,b in intervals) for lo,hi in zip(points,points[1:])),default=0)
        assert cell.maximum==expected
    a,b=r.settings.window
    minutes=sum(max(0,(min(end,b)-max(start,a)).total_seconds()/60) for start,end in intervals)
    assert sum(r.daily_crew_minutes)==pytest.approx(minutes)
    assert sum(r.histogram_minutes.values())==1440
    assert sum(c.dep_count for c in r.cells)==sum(f.direction=='dep' and a<=f.reference<b for f in fs)
    assert sum(c.arr_count for c in r.cells)==sum(f.direction=='arr' and a<=f.reference<b for f in fs)


def test_job_building_checks_cancellation():
    def check():
        raise RuntimeError('cancelled fixture')
    with pytest.raises(RuntimeError, match='cancelled fixture'):
        result([flight('1','arr',600),flight('2','dep',640)],check=check)


@pytest.mark.parametrize('intermediate', [False, True])
def test_service_full_snapshot_context_and_field_preservation(intermediate):
    from domain.models import Batch
    from adapters.ubikais_client import Cancelled
    from threading import Event
    calls = []
    class Client:
        def fetch(self, airport, task, **kwargs):
            calls.append(task)
            rows = []
            if task.day == BASE.date():
                if task.direction == 'arr':
                    rows.append(dict(flightPk='a',fpId='JJA1',staDate='20261026',sta='1000',
                                     blockOnTime='1000',acId=' hltest ',standArr='101'))
                else:
                    rows.append(dict(flightPk='d',fpId='JJA2',schDate='20261026',schTime='1040',
                                     blockOffTime='1040',acId='HLTEST',standDep='101'))
                    if intermediate:
                        rows.append(dict(flightPk='other',fpId='KAL9',schDate='20261026',schTime='1020',
                                         blockOffTime='1020',acId='HLTEST',standDep='101'))
            return Batch(task.day,task.direction,task.airline,tuple(rows),BASE)
    r = run_analysis(settings(),Client(),CONTRACT)
    assert r.exportable and len(r.flights) == 2
    assert r.diagnostics.raw == 2
    assert all(f.registration == 'HLTEST' and f.spot == '101' for f in r.flights)
    assert r.diagnostics.quick_turn_pairs == int(not intermediate)
    assert sum(c.dep_count for c in r.cells) == sum(c.arr_count for c in r.cells) == 1
    assert all(not task.airline for task in calls)
    cancel = Event();cancel.set()
    with pytest.raises(Cancelled):
        run_analysis(settings(),Client(),CONTRACT,cancel=cancel)


def test_conflicting_full_snapshot_movement_and_spot_changes_are_not_bridged():
    arr,dep = flight('1','arr',600),flight('2','dep',640)
    conflict = Movement(arr.key,'RKSI','arr','HLTEST','102',arr.actual,True)
    assert result([arr,dep],context=(conflict,)).diagnostics.quick_turn_pairs == 0
    middle = [Movement('x','RKSI','dep','HLTEST','102',BASE+timedelta(minutes=610),True),
              Movement('y','RKSI','arr','HLTEST','102',BASE+timedelta(minutes=620),True)]
    assert result([arr,dep],context=middle).diagnostics.quick_turn_pairs == 0


def test_unpaired_context_is_only_used_when_quick_turn_is_active():
    fs = [flight('1','arr',600),flight('2','dep',640)]
    m = Movement('other','RKSI','dep','HLTEST','101',BASE+timedelta(minutes=620),True)
    s = replace(settings(),quick_turn=False)
    assert result(fs,s).cells == result(fs,s,context=(m,)).cells


def test_planner_covers_merged_jobs_with_extreme_offsets_and_day_boundaries():
    rng = random.Random(194)
    for _ in range(100):
        def offsets():
            start,end,reusable = sorted(rng.sample(range(-10080,10081),3))
            return Offsets(start,end,reusable)
        s = settings(dep=offsets(),arr=offsets(),turn_limit=rng.randint(1,360),day_start=195)
        tasks = plan(s,actual_query_padding_days=1)
        days = {d:{t.day for t in tasks if t.direction==d} for d in ('dep','arr')}
        a,b = s.window
        for _ in range(20):
            ar = a+timedelta(minutes=rng.randint(-31000,31000))
            de = ar+timedelta(minutes=rng.randint(1,s.turn_limit))
            start = min(ar+timedelta(minutes=s.arr.start),de+timedelta(minutes=s.dep.start))
            end = max(ar+timedelta(minutes=s.arr.end),de+timedelta(minutes=s.dep.end))+timedelta(minutes=s.dep.reusable-s.dep.end)
            if start < b and end > a:
                for d,ref in (('arr',ar),('dep',de)):
                    scheduled = ref-timedelta(minutes=rng.randint(-180,1259))
                    assert scheduled.date() in days[d]
                    assert scheduled.date()-timedelta(days=1) in days[d]


def test_url_v4_roundtrip_legacy_v3_and_inactive_preference():
    s = settings(turn_limit=360)
    assert encode(s)['v'] == '4' and decode(encode(s),BASE.date()) == (s,None)
    legacy = encode(replace(s,quick_turn=False))
    legacy.update(v='3');legacy.pop('quick_turn');legacy.pop('turn_limit')
    restored,error = decode(legacy,BASE.date())
    assert not error and not restored.quick_turn
    assert not replace(s,basis='scheduled').quick_turn_active
    assert not replace(s,directions=('dep',)).quick_turn_active
    for patch in ({'turn_limit':'0'},{'turn_limit':'361'},{'quick_turn':'yes'},{'v':'3'}):
        restored,error = decode(encode(s)|patch,BASE.date())
        assert error and not restored.quick_turn


def test_ui_popover_preference_restore_and_bottom_help(monkeypatch):
    monkeypatch.delenv('CREW_DEMO',raising=False)
    app = AppTest.from_file('app.py',default_timeout=15)
    app.query_params.update(encode(replace(settings(),quick_turn=False)))
    app.run()
    assert not app.exception and not app.checkbox(key='quick_turn').disabled
    app.checkbox(key='quick_turn').check().run()
    app.number_input(key='turn_limit').set_value(360).run()
    assert not app.exception and app.query_params['quick_turn'] == ['1']
    assert app.query_params['turn_limit'] == ['360']
    app.radio(key='basis').set_value('scheduled').run()
    assert not app.exception and app.checkbox(key='quick_turn').disabled
    assert app.checkbox(key='quick_turn').value
    app.radio(key='basis').set_value('actual').run()
    app.checkbox(key='arr_included').uncheck().run()
    assert app.checkbox(key='quick_turn').disabled and app.number_input(key='turn_limit').value == 360
    app.checkbox(key='arr_included').check().run()
    assert not app.checkbox(key='quick_turn').disabled and app.checkbox(key='quick_turn').value
    assert any(e.label == '도움말 · 계산 기준' for e in app.expander)
    assert 'job' not in app.session_state


@pytest.mark.parametrize('interval',[60,30])
def test_turn_report_and_job_detail_keep_flights_and_settings(interval):
    from reports.render import build_export
    from ui.details import job_frame
    r = demo_result(settings(interval=interval))
    assert r.diagnostics.quick_turn_pairs > 0
    pair = next(j for j in r.jobs if j.kind == 'turn')
    frame = job_frame((pair,))
    assert frame.iloc[0]['유형'] == '연결'
    assert frame.iloc[0]['도착편'] != '—' and frame.iloc[0]['출발편'] != '—'
    assert sum(c.dep_count for c in r.cells) == sum(c.arr_count for c in r.cells) == 16
    doc = PdfReader(BytesIO(build_export(r,'pdf')))
    assert len(doc.pages) == (1 if interval==60 else 2)
    for page in doc.pages:
        text = page.extract_text()
        assert '퀵턴 100분 이내' in text and '대기 연속 점유' in text
        assert '16 / 16편' in text and '조기 3시간 허용' in text
