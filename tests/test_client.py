import io
import json
from datetime import date,datetime,timedelta
from threading import Event

import pytest

from adapters.ubikais_client import Cancelled, CollectionError, UbikaisClient, ttl_seconds
from domain.models import KST
from services.planner import Task

TASK=Task(date(2026,10,26),'dep')


class Opener:
    def __init__(self,*pages):self.pages=list(pages);self.calls=0
    def __call__(self,request,timeout):
        self.calls+=1
        page=self.pages.pop(0)
        if isinstance(page,Exception):raise page
        return io.BytesIO(json.dumps(page).encode() if isinstance(page,dict) else page)


def ok(rows,total=None):return dict(status='success',total=len(rows) if total is None else total,records=rows)


@pytest.mark.parametrize('code', ['JJA','XUM','ZZZ'])
def test_icao_query_code_is_sent_verbatim(tmp_path, code):
    from urllib.parse import urlparse, parse_qs
    seen = []
    def opener(request, timeout):
        seen.append(parse_qs(urlparse(request.full_url).query)['srchAl'][0])
        return io.BytesIO(json.dumps(ok([])).encode())
    client = UbikaisClient(cache_dir=tmp_path,opener=opener,retries=0,pace=0)
    client.fetch('RKSI',Task(date(2026,10,26),'dep',code))
    assert seen == [code]


def test_pagination_and_completed_cache(tmp_path):
    opener=Opener(ok([{'flightPk':'1'}],2),ok([{'flightPk':'2'}],2))
    client=UbikaisClient(cache_dir=tmp_path,opener=opener,retries=0,pace=0)
    # Current date cache rules are independent of the fixture date.
    b=client.fetch('RKSI',TASK)
    assert len(b.records)==2 and opener.calls==2
    cached=client.fetch('RKSI',TASK)
    assert cached.cached and opener.calls==2


@pytest.mark.parametrize('pages',[
    [ok([{'id':1}],3),ok([{'id':1}],3)],
    [ok([{'id':1}],2),ok([],2)],
    [ok([{'id':1}],2),ok([{'id':2}],3)],
    [ok([{'id':1},{'id':2}],1)],
    [dict(status='success',total=-1,records=[])],
    [dict(status='success',total=1,records=['bad'])],
    [dict(status='failure',msg='DO_NOT_LEAK')],
    [b'<html>SECRET</html>'],
])
def test_bad_collection_never_cached_or_leaks_body(tmp_path,pages):
    client=UbikaisClient(cache_dir=tmp_path,opener=Opener(*pages),retries=0,pace=0)
    with pytest.raises(CollectionError) as exc:client.fetch('RKSI',TASK)
    assert 'SECRET' not in str(exc.value) and 'DO_NOT_LEAK' not in str(exc.value)
    assert not list(tmp_path.glob('*.json'))


def test_zero_is_success_and_broken_cache_recovers(tmp_path):
    client=UbikaisClient(cache_dir=tmp_path,opener=Opener(ok([])),pace=0)
    client._path('RKSI',TASK).write_text('broken')
    batch=client.fetch('RKSI',TASK)
    assert batch.records==()


def test_cancelled_before_request(tmp_path):
    event=Event();event.set()
    with pytest.raises(Cancelled):
        UbikaisClient(cache_dir=tmp_path,opener=Opener(),pace=0).fetch('RKSI',TASK,cancel=event)


def test_cancel_during_pagination_never_saves_partial_cache(tmp_path):
    event=Event()
    def opener(request,timeout):
        event.set()
        return io.BytesIO(json.dumps(ok([{'id':1}],2)).encode())
    with pytest.raises(Cancelled):
        UbikaisClient(cache_dir=tmp_path,opener=opener,pace=0).fetch('RKSI',TASK,cancel=event)
    assert not list(tmp_path.glob('*.json'))


def test_retry_timeout_then_success(tmp_path):
    opener=Opener(TimeoutError(),ok([]))
    assert UbikaisClient(cache_dir=tmp_path,opener=opener,retries=1,pace=0).fetch('RKSI',TASK).records==()
    assert opener.calls==2


def test_cutoff_ttls():
    now=datetime(2026,10,27,7,tzinfo=KST)
    assert ttl_seconds(now.date(),now,now)==1800
    assert ttl_seconds(now.date()+timedelta(days=2),now,now)==86400
    assert ttl_seconds(now.date()-timedelta(days=1),now-timedelta(hours=2),now)==0
    assert ttl_seconds(now.date()-timedelta(days=1),now,now)==604800

