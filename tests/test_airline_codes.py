from datetime import date, datetime
import re

import pytest

from config.airline_codes import ICAO_TO_IATA, flight_label, parse_icao_codes, to_iata_codes
from domain.models import Batch, KST, Settings
from services.analysis import run_analysis
from tests.fixtures import VERIFIED
from ui.url_state import encode, decode


@pytest.mark.parametrize('icao,iata', [('TTW','IT'),('AXM','AK'),('HKE','UO'),('CQH','9C'),
    ('CDC','GJ'),('CSC','3U'),('RLH','DR'),('JJA','7C'),('FDX','FX'),('JST','JQ'),
    ('TZP','ZG'),('XUM','XU'),('ASA','AS')])
def test_query_codes_roundtrip_and_display_only(icao, iata):
    assert parse_icao_codes(icao.lower()) == (icao,)
    assert to_iata_codes((icao,)) == (iata,)
    assert flight_label(icao+'001F') == iata+'001F'
    settings = Settings('RKSI',date(2026,10,26),date(2026,10,26),mode='custom',airlines=(icao,))
    params = encode(settings)
    assert params['v'] == '3' and params['airlines'] == icao
    restored, error = decode(params,date(2026,10,29))
    assert not error and restored == settings


def test_partial_display_reference_never_limits_queries():
    assert len(ICAO_TO_IATA) == 310
    assert all(re.fullmatch('[A-Z]{3}',k) and re.fullmatch('[A-Z0-9]{2}',v)
               for k,v in ICAO_TO_IATA.items())
    assert parse_icao_codes(' zzz, jja, ZZZ ') == ('JJA','ZZZ')
    assert to_iata_codes(('ZZZ',)) == ('ZZZ',)
    assert flight_label('ZZZ001F') == 'ZZZ001F'
    settings = Settings('RKSI',date(2026,10,26),date(2026,10,26),mode='custom',airlines=('ZZZ',))
    assert decode(encode(settings),date(2026,10,29)) == (settings,None)


@pytest.mark.parametrize('code', ['7C','KE','7','7C1','??','', 'JJA1','JJ-A','제주'])
def test_bad_query_codes_block(code):
    with pytest.raises(ValueError):
        parse_icao_codes(code)


@pytest.mark.parametrize('params', [{'v':'2','airlines':'7C,IT'}, {'v':'2'},
                                  {'v':'2','airlines':''}, {'v':'1','airlines':'JJA'}])
def test_old_url_versions_are_rejected(params):
    restored,error = decode(params,date(2026,10,29))
    assert error and restored.airlines == ('JJA',)


def test_duplicate_display_codes_do_not_change_query_identity(monkeypatch):
    monkeypatch.setitem(ICAO_TO_IATA,'AAA','XX')
    monkeypatch.setitem(ICAO_TO_IATA,'BBB','XX')
    assert parse_icao_codes('AAA,BBB') == ('AAA','BBB')
    assert to_iata_codes(('AAA','BBB')) == ('XX','XX')
    settings = Settings('RKSI',date(2026,10,26),date(2026,10,26),mode='custom',airlines=('AAA','BBB'))
    assert decode(encode(settings),date(2026,10,29)) == (settings,None)


@pytest.mark.parametrize('original', ['7C001F','JJA','JJA-001',' XUM001 ','XJJA001',''])
def test_nonstandard_flight_identifiers_stay_unchanged(original):
    assert flight_label(original) == original


def test_query_codes_reach_collector_unchanged_and_preserve_flights():
    codes = ('AXM','CDC','CQH','CSC','HKE','RLH','TTW','XUM','ZZZ')
    settings = Settings('RKSI',date(2026,10,26),date(2026,10,26),mode='custom',airlines=codes)
    seen = []
    class Client:
        def fetch(self,airport,task,**kwargs):
            seen.append(task.airline)
            rows = ()
            if task.day == settings.start and task.direction == 'dep':
                rows = (dict(flightPk=task.airline,fpId=task.airline+'001F',schDate='20261026',schTime='1000'),)
            return Batch(task.day,task.direction,task.airline,rows,datetime(2026,10,29,tzinfo=KST))
    result = run_analysis(settings,Client(),VERIFIED)
    assert set(seen) == set(codes)
    assert sum(c.dep_count for c in result.cells) == len(codes)
    assert {f.flight_id for f in result.flights} == {code+'001F' for code in codes}
    assert {f.query_airlines[0] for f in result.flights} == set(codes)
