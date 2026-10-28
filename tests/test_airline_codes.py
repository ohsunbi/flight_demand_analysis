from datetime import date, datetime
import pytest

from config.airline_codes import IATA_TO_ICAO, parse_iata_codes, to_iata_codes
from domain.models import Batch, KST, Settings
from services.analysis import run_analysis
from tests.fixtures import VERIFIED
from ui.url_state import encode, decode


@pytest.mark.parametrize('iata,icao', [('IT','TTW'),('AK','AXM'),('UO','HKE'),('9C','CQH'),
                                      ('GJ','CDC'),('3U','CSC'),('DR','RLH'),('7C','JJA')])
def test_required_airlines_convert_and_roundtrip(iata,icao):
    assert parse_iata_codes(iata)==(icao,)
    assert to_iata_codes((icao,))==(iata,)
    settings=Settings('RKSI',date(2026,10,26),date(2026,10,26),mode='custom',airlines=(icao,))
    params=encode(settings)
    assert params['v']=='2' and params['airlines']==iata
    restored,error=decode(params,date(2026,10,28))
    assert not error and restored==settings


@pytest.mark.parametrize('code', ['JJA','KAL','7','7C1','??','ZZ','3S',''])
def test_bad_or_unregistered_codes_block(code):
    with pytest.raises(ValueError):parse_iata_codes(code)


def test_ambiguous_code_blocks(monkeypatch):
    monkeypatch.setitem(IATA_TO_ICAO,'XX',('AAA','BBB'))
    with pytest.raises(ValueError,match='여러 항공사'):parse_iata_codes('XX')


@pytest.mark.parametrize('code',['AS','HA'])
def test_shared_icao_does_not_silently_change_display_or_url(code):
    with pytest.raises(ValueError,match='중복'):parse_iata_codes(code)


def test_iata_input_reaches_api_as_icao_and_preserves_flights():
    codes='IT,AK,UO,9C,GJ,3U,DR'
    settings=Settings('RKSI',date(2026,10,26),date(2026,10,26),mode='custom',airlines=parse_iata_codes(codes))
    seen=[]
    class Client:
        def fetch(self,airport,task,**kwargs):
            seen.append(task.airline)
            rows=()
            if task.day==settings.start and task.direction=='dep':
                rows=(dict(flightPk=task.airline,fpId=task.airline+'100',schDate='20261026',schTime='1000'),)
            return Batch(task.day,task.direction,task.airline,rows,datetime(2026,10,28,tzinfo=KST))
    result=run_analysis(settings,Client(),VERIFIED)
    assert set(seen)=={'TTW','AXM','HKE','CQH','CDC','CSC','RLH'}
    assert sum(c.dep_count for c in result.cells)==7
    assert {f.query_airlines[0] for f in result.flights}==set(seen)
