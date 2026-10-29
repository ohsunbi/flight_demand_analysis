from datetime import date

import pytest

from domain.models import Settings
from services.planner import plan


def test_multiple_airlines_share_date_direction_tasks():
    s=Settings('RKSI',date(2026,10,26),date(2026,10,26),mode='custom',airlines=('ESR','KAL'))
    tasks=plan(s)
    assert len(tasks)==8 and {t.airline for t in tasks}=={''}
    assert len({(t.day,t.direction) for t in tasks}) == len(tasks)


def test_daegu_month_with_eight_airlines_needs_72_complete_snapshots():
    from config import MAX_QUERY_TASKS, airport_airlines
    assert MAX_QUERY_TASKS == 1000
    settings = Settings('RKTN',date(2026,10,1),date(2026,10,31),basis='actual',
                        airlines=airport_airlines('RKTN'))
    assert len(plan(settings,actual_query_padding_days=1)) == 72


def test_actual_contract_boundary_padding():
    s=Settings('RKSI',date(2026,10,26),date(2026,10,26),mode='custom',basis='actual')
    tasks=plan(s,actual_query_padding_days=2)
    assert min(t.day for t in tasks)==date(2026,10,22)
    assert max(t.day for t in tasks)==date(2026,10,29)


def test_zero_offsets_still_include_prior_query_day():
    from domain.models import Offsets
    s=Settings('RKSI',date(2026,10,26),date(2026,10,26),mode='custom',dep=Offsets(0,0,0),arr=Offsets(0,0,0))
    assert min(t.day for t in plan(s))==date(2026,10,25)
