import io
import json
from dataclasses import asdict
from datetime import date, datetime
from threading import Event

import pytest

from adapters.ubikais_client import Cancelled, CollectionError, UbikaisClient
from domain.models import Batch, KST, Settings
from engine.demand import analyze
from normalization.flights import normalize
from services.analysis import run_analysis
from services.collection import collect
from services.planner import Task, plan
from tests.fixtures import VERIFIED


DAY = date(2026,10,26)
AT = datetime(2026,10,29,tzinfo=KST)


def settings(**kwargs):
    return Settings('RKSI',DAY,DAY,mode='custom',airlines=('JJA','TTW'),**kwargs)


def row(code='JJA', number='001F', **kwargs):
    return dict(flightPk=code+number,fpId=code+number,schDate='20261026',schTime='1000',
                staDate='20261026',sta='1000',blockOffTime='202610261030',
                blockOnTime='202610261030',**kwargs)


class Client:
    def __init__(self, rows):
        self.rows = tuple(rows)
        self.calls = []

    def fetch(self, airport, task, **kwargs):
        self.calls.append((task,kwargs))
        records = self.rows if task.day == DAY else ()
        if task.airline:
            records = tuple(r for r in records if r.get('fpId','').startswith(task.airline))
        return Batch(task.day,task.direction,task.airline,records,AT)


@pytest.mark.parametrize('basis', ['scheduled','actual'])
@pytest.mark.parametrize('interval', [30,60])
def test_whole_selection_matches_individual_normalization_and_engine(basis, interval):
    s = settings(basis=basis,interval=interval)
    client = Client((row(),row('TTW'),row('AAR'),row('TTW','002',depStatus='CNL',arrStatus='CNL')))
    progress = []
    batches,count,fallbacks = collect(s,client,VERIFIED,progress=lambda *v: progress.append(v))
    assert count == len(plan(s)) == len(client.calls) and fallbacks == 0
    assert {task.airline for task,_ in client.calls} == {''}
    assert sum(len(batch.records) for batch in batches) == 6
    assert progress[-1][0] < progress[-1][1]

    legacy = Client(client.rows)
    expected_batches = tuple(legacy.fetch(s.airport,Task(t.day,t.direction,code))
                             for t in plan(s) for code in s.airlines)
    flights,diag = normalize(expected_batches,s,VERIFIED)
    expected = analyze(s,flights,diag,AT,AT)
    result = run_analysis(s,Client(client.rows),VERIFIED)
    assert result.flights == expected.flights
    assert result.cells == expected.cells
    assert result.segments == expected.segments
    assert result.histogram_minutes == expected.histogram_minutes
    assert result.daily_crew_minutes == expected.daily_crew_minutes
    assert result.diagnostics.cancelled == 2
    assert {f.flight_id for f in result.flights} == {'JJA001F','TTW001F'}
    assert {f.query_airlines for f in result.flights} == {('JJA',),('TTW',)}


@pytest.mark.parametrize('identifier', ['', '12345', 'JJA-001', 'JJA001AB', None])
def test_unclassifiable_whole_group_is_replaced_by_individual_queries(identifier):
    class FallbackClient(Client):
        def fetch(self, airport, task, **kwargs):
            self.calls.append((task,kwargs))
            records = ()
            if task.day == DAY:
                if not task.airline:
                    records = (row(),dict(row('OTHER'),fpId=identifier))
                else:
                    records = (row(task.airline),)
            return Batch(task.day,task.direction,task.airline,records,AT)
    s = settings()
    client = FallbackClient(())
    result = run_analysis(s,client,VERIFIED,refresh=True)
    assert len(client.calls) == len(plan(s))+4
    assert all(kwargs['refresh'] for _,kwargs in client.calls)
    assert sum(cell.dep_count for cell in result.cells) == 2
    assert sum(cell.arr_count for cell in result.cells) == 2
    assert result.exportable
    assert any('개별 조회' in message for message in result.diagnostics.messages)


def test_failed_individual_fallback_never_returns_partial_analysis():
    class Failed(Client):
        def fetch(self, airport, task, **kwargs):
            if task.day == DAY and task.airline == 'TTW':
                raise CollectionError('fixture failure')
            self.calls.append((task,kwargs))
            records = (dict(row(),fpId=''),) if task.day == DAY else ()
            return Batch(task.day,task.direction,task.airline,records,AT)
    with pytest.raises(CollectionError,match='fixture failure'):
        run_analysis(settings(),Failed(()),VERIFIED)


def test_collection_failure_is_not_treated_as_a_reason_to_retry_other_airlines():
    class Failed(Client):
        def fetch(self, airport, task, **kwargs):
            self.calls.append((task,kwargs))
            raise CollectionError('fixture incomplete collection')
    client = Failed(())
    with pytest.raises(CollectionError):
        collect(settings(),client,VERIFIED)
    assert len(client.calls) == 1


def test_cancel_after_whole_fetch_prevents_selection_and_fallback():
    event = Event()
    class Stop(Client):
        def fetch(self, airport, task, **kwargs):
            batch = super().fetch(airport,task,**kwargs)
            event.set()
            return batch
    client = Stop((dict(row(),fpId=''),))
    with pytest.raises(Cancelled):
        collect(settings(),client,VERIFIED,cancel=event)
    assert len(client.calls) == 1


def test_raw_date_drift_is_checked_before_selection():
    client = Client((dict(row('AAR'),schDate='20260101',staDate='20260101'),))
    with pytest.raises(CollectionError,match='조회 날짜 규칙'):
        collect(settings(),client,VERIFIED)


@pytest.mark.parametrize('planned,allowed', [(998,True),(999,False)])
def test_1000_unit_budget_counts_whole_and_individual_queries(monkeypatch, planned, allowed):
    from services import collection
    assert collection.MAX_QUERY_TASKS == 1000
    monkeypatch.setattr(collection,'plan',lambda *a,**k: (Task(DAY,'dep'),)*planned)
    class OneFallback(Client):
        def fetch(self, airport, task, **kwargs):
            self.calls.append((task,kwargs))
            records = (dict(row(),fpId=''),) if len(self.calls) == 1 else ()
            return Batch(task.day,task.direction,task.airline,records,AT)
    client = OneFallback(())
    if allowed:
        _,count,fallbacks = collect(settings(),client,VERIFIED)
        assert count == 1000 and fallbacks == 1 and len(client.calls) == 1000
    else:
        with pytest.raises(CollectionError,match='운영 제한'):
            collect(settings(),client,VERIFIED)
        assert len(client.calls) == 1


def test_whole_cache_is_shared_without_selection_leakage_and_refresh_bypasses_it(monkeypatch,tmp_path):
    from services import collection
    monkeypatch.setattr(collection,'plan',lambda *a,**k: (Task(DAY,'dep'),))
    calls = []
    records = [row(),row('TTW'),row('AAR')]
    def opener(request,timeout):
        calls.append(1)
        return io.BytesIO(json.dumps(dict(status='success',total=3,records=records)).encode())
    client = UbikaisClient(cache_dir=tmp_path,opener=opener,retries=0,pace=0)
    a,_,_ = collect(Settings('RKSI',DAY,DAY,mode='custom',airlines=('JJA',)),client,VERIFIED)
    b,_,_ = collect(Settings('RKSI',DAY,DAY,mode='custom',airlines=('TTW',)),client,VERIFIED)
    assert a[0].records[0]['fpId'] == 'JJA001F' and b[0].records[0]['fpId'] == 'TTW001F'
    assert b[0].cached and len(calls) == 1
    assert len(list(tmp_path.glob('*.json'))) == 1
    saved = json.loads(next(tmp_path.glob('*.json')).read_text(encoding='utf-8'))
    assert saved['complete'] and len(saved['records']) == 3
    collect(settings(),client,VERIFIED,refresh=True)
    assert len(calls) == 2
