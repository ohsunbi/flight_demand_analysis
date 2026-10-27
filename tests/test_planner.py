from datetime import date

import pytest

from domain.models import Settings
from services.planner import plan


def test_multiple_airline_tasks_are_explicit():
    s=Settings('RKSI',date(2026,10,26),date(2026,10,26),mode='custom',airlines=('ESR','KAL'))
    tasks=plan(s)
    assert len(tasks)==16 and {t.airline for t in tasks}=={'ESR','KAL'}


def test_actual_contract_boundary_padding():
    s=Settings('RKSI',date(2026,10,26),date(2026,10,26),mode='custom',basis='actual')
    tasks=plan(s,actual_query_padding_days=2)
    assert min(t.day for t in tasks)==date(2026,10,22)
    assert max(t.day for t in tasks)==date(2026,10,29)


def test_zero_offsets_still_include_prior_query_day():
    from domain.models import Offsets
    s=Settings('RKSI',date(2026,10,26),date(2026,10,26),mode='custom',dep=Offsets(0,0,0),arr=Offsets(0,0,0))
    assert min(t.day for t in plan(s))==date(2026,10,25)
