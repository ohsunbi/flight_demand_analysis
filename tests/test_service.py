from datetime import date,datetime

import pytest

from domain.models import Batch, Contract, KST, Settings
from services.analysis import run_analysis
from tests.fixtures import VERIFIED


class Client:
    def fetch(self,airport,task,**kwargs):
        rows=()
        if str(task.day)=='2026-10-26' and task.direction=='dep':
            rows=(dict(flightPk='one',fpId='ESR100',schDate='20261026',schTime='1000',blockOffDate='20261026',blockOffTime='1100',depStatus='DEP'),)
        return Batch(task.day,task.direction,'',rows,datetime.now(KST))


def test_reference_counts_follow_actual_and_export_gate():
    s=Settings('RKSI',date(2026,10,26),date(2026,10,26),mode='custom',basis='actual')
    r=run_analysis(s,Client(),VERIFIED)
    assert r.cells[10].dep_count==0 and r.cells[11].dep_count==1
    assert r.diagnostics.actual_used==1 and r.exportable
    unverified=run_analysis(s,Client(),Contract())
    assert not unverified.exportable and unverified.blockers


def test_partial_failure_does_not_return_analysis():
    class Failed(Client):
        def fetch(self,airport,task,**kwargs):
            if task.direction=='arr':raise RuntimeError('fixture failure')
            return super().fetch(airport,task,**kwargs)
    s=Settings('RKSI',date(2026,10,26),date(2026,10,26),mode='custom')
    with pytest.raises(RuntimeError):run_analysis(s,Failed(),VERIFIED)


def test_query_date_contract_drift_fails_closed():
    class Drift(Client):
        def fetch(self,airport,task,**kwargs):
            return Batch(task.day,task.direction,'',(dict(flightPk='x',fpId='ESR1',schDate='20260101',schTime='1200',staDate='20260101',sta='1200'),),datetime.now(KST))
    from adapters.ubikais_client import CollectionError
    with pytest.raises(CollectionError):
        run_analysis(Settings('RKSI',date(2026,10,26),date(2026,10,26),mode='custom'),Drift(),VERIFIED)

