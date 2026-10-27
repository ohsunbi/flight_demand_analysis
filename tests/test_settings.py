from datetime import date,timedelta

import pytest

from domain.models import Offsets,Settings
from services.planner import plan
from ui.url_state import decode,encode


def test_url_roundtrip_all_settings():
    s=Settings('RKPC',date(2026,12,25),date(2027,1,5),mode='custom',airlines=('AAR','ESR'),basis='actual',day_start=195,interval=30,dep=Offsets(-2000,-100,50))
    restored,error=decode(encode(s),date(2026,10,27))
    assert not error and restored==s


@pytest.mark.parametrize('params',[{'v':'99'},{'dep':'1,2'},{'interval':'1'},{'airport':'../../x'},{'airlines':'ESR,<script>'},{'start':'2026-01-01','end':'2026-12-31'},{'start':'9999-12-01','end':'9999-12-31'}])
def test_invalid_urls_safe_fallback(params):
    s,error=decode(params,date(2026,10,27))
    assert error and s.airport=='RKSI'


def test_planner_extreme_offsets_uses_more_than_one_boundary_day():
    s=Settings('RKSI',date(2026,10,26),date(2026,10,26),mode='custom',dep=Offsets(-3000,0,3000))
    tasks=plan(s)
    ds=[t.day for t in tasks if t.direction=='dep']
    assert min(ds)<=s.start-timedelta(days=2) and max(ds)>=s.end+timedelta(days=2)


def test_period_limit_and_offset_order():
    with pytest.raises(ValueError):Settings('RKSI',date(2026,1,1),date(2026,2,1),mode='custom').validate()
    with pytest.raises(ValueError):Offsets(1,0,2).validate()
    Settings('RKSI',date(2026,1,1),date(2026,1,31)).validate()
