from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

from config import airport_airlines
from config.airline_codes import to_iata_codes
from ui.url_state import decode, encode


@pytest.mark.parametrize('airport,expected', [
    ('RKSI',('7C','AK','IT')), ('RKSS',('7C','IT')), ('RKPC',('7C','9C','UO')),
    ('RKPK',('7C','UO','9C','GJ')), ('RKTU',('7C','3U','DR','GJ')),
    ('RKTN',('7C','UO','ZE','3U','QW','GJ','8L','JD')), ('RKJB',('7C',)),
])
def test_airport_presets_and_url_defaults(airport, expected):
    assert to_iata_codes(airport_airlines(airport)) == tuple(sorted(expected))
    settings,error = decode({'airport':airport},date(2026,10,29))
    assert not error and settings.airlines == tuple(sorted(airport_airlines(airport)))
    assert decode(encode(settings),date(2026,10,29)) == (settings,None)


@pytest.mark.parametrize('explicit', ['XUM,ZZZ',''])
def test_explicit_url_airlines_override_presets(explicit):
    settings,error = decode({'airport':'RKTN','airlines':explicit},date(2026,10,29))
    assert not error
    assert settings.airlines == (('XUM','ZZZ') if explicit else ())


def test_airport_change_fills_codes_and_preserves_edits_until_next_change(monkeypatch):
    monkeypatch.delenv('CREW_DEMO',raising=False)
    app = AppTest.from_file('app.py',default_timeout=15).run()
    for airport in ('RKSS','RKPC','RKPK','RKTU','RKTN','RKJB','RKSI'):
        app.selectbox(key='airport').set_value(airport).run()
        assert not app.exception and not app.error
        assert app.text_input(key='codes').value == ', '.join(airport_airlines(airport))
        assert app.query_params['airlines'] == [','.join(sorted(airport_airlines(airport)))]
        assert 'job' not in app.session_state
    app.text_input(key='codes').set_value('XUM, JJA').run()
    app.radio(key='interval').set_value(30).run()
    assert app.text_input(key='codes').value == 'XUM, JJA'
    assert app.query_params['airlines'] == ['JJA,XUM']
    assert 'job' not in app.session_state
    app.text_input(key='codes').set_value('').run()
    app.radio(key='basis').set_value('actual').run()
    assert app.text_input(key='codes').value == ''
    assert all(button.disabled for button in app.button)
    app.selectbox(key='airport').set_value('RKSS').run()
    assert app.text_input(key='codes').value == 'JJA, TTW'
    assert not app.exception and not app.error


def test_explicit_url_airlines_are_not_replaced_on_first_load(monkeypatch):
    monkeypatch.delenv('CREW_DEMO',raising=False)
    app = AppTest.from_file('app.py',default_timeout=15)
    app.query_params.update(dict(v='3',airport='RKTN',airlines='ZZZ'))
    app.run()
    assert app.selectbox(key='airport').value == 'RKTN'
    assert app.text_input(key='codes').value == 'ZZZ'
    assert 'job' not in app.session_state
