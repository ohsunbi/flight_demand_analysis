from datetime import date, datetime

import pytest

from domain.models import Batch, Contract, KST, Offsets, Settings
from normalization.flights import normalize, parse_datetime
from tests.fixtures import VERIFIED

DAY=date(2026,10,26)


def norm(rows,basis='scheduled',direction='dep',contract=VERIFIED,**kwargs):
    s=Settings('RKSI',DAY,DAY,mode='custom',basis=basis,**kwargs)
    return normalize((Batch(DAY,direction,'',tuple(rows),datetime.now(KST)),),s,contract)


def raw(**kwargs):
    r=dict(flightPk='1',fpId='ESR100',schDate='20261026',schTime='1000',staDate='20261026',sta='1100',depStatus='DEP')
    r.update(kwargs);return r


def test_duplicate_and_same_flight_number_different_day():
    fs,d=norm([raw(),raw(),raw(flightPk='2',schDate='20261027')])
    assert len(fs)==2 and d.duplicates==1


def test_same_flight_returned_for_two_query_airlines_is_counted_once():
    s=Settings('RKSI',DAY,DAY,mode='custom',airlines=('ESR','KAL'))
    batches=tuple(Batch(DAY,'dep',code,(raw(),),datetime.now(KST)) for code in s.airlines)
    fs,d=normalize(batches,s,VERIFIED)
    assert len(fs)==1 and fs[0].query_airlines==('ESR','KAL') and d.duplicates==1


def test_actual_with_explicit_date_and_fallback():
    fs,d=norm([raw(blockOffTime='202610271100'),raw(flightPk='2')],basis='actual')
    assert fs[0].reference_source=='fallback'
    assert fs[1].reference==datetime(2026,10,27,11,tzinfo=KST)
    assert fs[1].start==datetime(2026,10,27,10,10,tzinfo=KST)


def test_undated_actual_never_infers_nearest_day():
    fs,d=norm([raw(schTime='0005',blockOffTime='2351')],basis='actual')
    assert fs[0].reference_source=='fallback'
    assert fs[0].actual is None and d.date_unresolved==1


def test_user_approved_nearest_date_handles_previous_and_next_day():
    from dataclasses import replace
    profile=replace(VERIFIED,actual_date_policy='nearest_scheduled')
    fs,_=norm([raw(schTime='0005',blockOffTime='2351'),raw(flightPk='2',schTime='2355',blockOffTime='0010')],basis='actual',contract=profile)
    assert fs[0].reference==datetime(2026,10,25,23,51,tzinfo=KST)
    assert fs[1].reference==datetime(2026,10,27,0,10,tzinfo=KST)
    assert all(f.reference_source=='actual_inferred' for f in fs)


def test_inferred_date_tie_chooses_scheduled_calendar_day():
    from dataclasses import replace
    fs,_=norm([raw(schTime='1200',blockOffTime='0000')],basis='actual',contract=replace(VERIFIED,actual_date_policy='nearest_scheduled'))
    assert fs[0].reference==datetime(2026,10,26,tzinfo=KST)


def test_explicit_actual_date_field():
    fs,_=norm([raw(blockOnDate='20261027',blockOnTime='0010')],basis='actual',direction='arr')
    assert fs[0].reference==datetime(2026,10,27,0,10,tzinfo=KST)


def test_cancel_unknown_missing_and_no_estimated_fallback():
    fs,d=norm([raw(depStatus='CNL'),raw(flightPk='2',depStatus='UNKNOWN'),raw(flightPk='3',schTime='',etd='1200')])
    assert len(fs)==1 and d.cancelled==1 and d.quarantined==1 and d.unknown_status==1


def test_conflicting_schedule_quarantines_instead_of_picking_list_order():
    fs,d=norm([raw(),raw(schTime='1100')])
    assert not fs and d.conflicts==1 and d.quarantined==1


def test_no_codeshare_guessing():
    fs,_=norm([raw(acId='same'),raw(flightPk='2',fpId='KAL100',acId='same')])
    assert len(fs)==2


def test_filters_and_validation():
    s=Settings('RKSI',DAY,DAY,mode='custom',airlines=('ESR',))
    batch=Batch(DAY,'dep','ESR',(raw(),),datetime.now(KST))
    fs,_=normalize((batch,),s,Contract())
    assert len(fs)==1 and fs[0].query_airlines==('ESR',)
    assert fs[0].flight_pk=='1'


@pytest.mark.parametrize('d,t',[('20260230','1200'),('20261026','2400'),('20261026','9:00'),('','1200'),('20261026','1260')])
def test_bad_date_time(d,t):
    assert parse_datetime(d,t) is None

