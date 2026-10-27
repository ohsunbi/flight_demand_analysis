from datetime import date, datetime, timedelta
import random

import pytest

from domain.models import Diagnostics, Flight, KST, Offsets, Settings
from engine.demand import analyze, cell_flights

BASE = datetime(2026,10,26,tzinfo=KST)


def settings(**kwargs):
    return Settings('RKSI',date(2026,10,26),date(2026,10,26),mode='custom',**kwargs)


def flight(key,start,end,direction='dep',reference=None):
    ref = BASE + timedelta(minutes=start if reference is None else reference)
    return Flight(str(key),direction,'ESR'+str(key),'RKSI','RKPC',ref,None,ref,'scheduled',(),(),'',('',''),
                  BASE+timedelta(minutes=start),BASE+timedelta(minutes=end),BASE+timedelta(minutes=end))


def run(fs, s=None):
    return analyze(s or settings(),tuple(fs),Diagnostics(),BASE,BASE)


def test_nonconcurrent_direction_maxima():
    r = run([flight(i,540,550) for i in range(2)] + [flight(i+2,560,570,'arr') for i in range(3)])
    c = r.cells[9]
    assert (c.maximum,c.dep_active,c.arr_active,c.peak) == (3,0,3,BASE+timedelta(minutes=560))
    assert len(cell_flights(r,9,'peak')) == 3
    assert len(cell_flights(r,9,'overlap')) == 5


def test_half_open_instant_reuse_and_edges():
    r = run([flight(1,540,600),flight(2,600,660),flight(3,-30,0),flight(4,1440,1500)])
    assert r.maximum == 1
    assert r.cells[9].dep_active == 1 and r.cells[10].dep_active == 1
    assert r.cells[0].maximum == 0 and r.cells[-1].maximum == 0


def test_carry_in_and_reference_independence():
    r = run([flight(1,-60,10,reference=-20),flight(2,100,110,reference=5)])
    c = r.cells[0]
    assert c.maximum == 1 and c.peak == BASE
    assert c.dep_count == 1
    assert [f.key for f in cell_flights(r,0,'reference')] == ['2']


def test_zero_length_counts_and_empty_timeline():
    r = run([flight(1,10,10)])
    assert r.maximum == 0 and r.peak_cell is None
    assert r.cells[0].dep_count == 1
    assert r.histogram_minutes == {0:1440}
    assert len(run([]).segments) == 1


def test_earliest_tied_peaks():
    r = run([flight(1,2,3),flight(2,5,8)])
    assert r.cells[0].peak == BASE+timedelta(minutes=2)
    assert len(r.cells[0].peak_intervals)==2


@pytest.mark.parametrize('start_minute,interval',[(0,60),(195,30),(1439,60)])
def test_arbitrary_day_start(start_minute,interval):
    r=run([flight(1,start_minute-10,start_minute+10)],settings(day_start=start_minute,interval=interval))
    assert r.cells[0].maximum==1 and r.cells[0].peak==r.settings.window[0]
    assert len(r.cells)==1440//interval
    assert sum(r.histogram_minutes.values())==1440


def test_random_independent_oracle_and_integral():
    rng=random.Random(914)
    for _ in range(80):
        fs=[flight(i,rng.randint(-90,1500),0,'dep') for i in range(0)]
        for i in range(rng.randint(0,25)):
            start=rng.randint(-90,1500); end=start+rng.randint(0,250)
            fs.append(flight(i,start,end,rng.choice(['dep','arr'])))
        r=run(fs)
        for c in r.cells:
            points=sorted({c.start,c.end,*[t for f in fs for t in (f.start,f.reusable) if c.start<t<c.end]})
            samples=[]
            for l,h in zip(points,points[1:]):
                mid=l+(h-l)/2
                samples.append(sum(f.start<=mid<f.reusable for f in fs))
            assert c.maximum==max(samples,default=0)
            assert len(cell_flights(r,c.index,'peak'))==c.maximum
            assert c.dep_active+c.arr_active==c.maximum
        assert sum(r.histogram_minutes.values())==1440
        direct=sum(max(0,(min(f.reusable,BASE+timedelta(days=1))-max(f.start,BASE)).total_seconds())/60 for f in fs)
        assert sum(k*v for k,v in r.histogram_minutes.items())==pytest.approx(direct)
        assert r.daily_crew_minutes[0]==pytest.approx(direct)
        assert sum((s.end-s.start).total_seconds() for s in r.segments)==86400
        assert all(s.dep>=0 and s.arr>=0 for s in r.segments)


def test_month_boundary_and_leap_day():
    for begin,end in [(date(2024,2,28),date(2024,3,1)),(date(2026,12,31),date(2027,1,1))]:
        s=Settings('RKSI',begin,end,mode='custom')
        r=run([],s)
        assert r.cells[-1].operating_day==end
        assert len(r.daily_max)==(end-begin).days+1

