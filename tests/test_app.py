from streamlit.testing.v1 import AppTest


def test_initial_app_does_not_fetch_automatically(monkeypatch):
    monkeypatch.delenv('CREW_DEMO',raising=False)
    app=AppTest.from_file('app.py',default_timeout=15).run()
    assert not app.exception
    assert 'result' not in app.session_state
    assert 'job' not in app.session_state
    assert app.radio(key='basis').value=='scheduled'
    assert app.radio(key='interval').value==60
    actual=AppTest.from_file('app.py',default_timeout=15)
    actual.query_params.update(dict(mode='custom',start='2026-10-26',end='2026-10-26',basis='actual'))
    actual.run()
    assert not actual.exception
    assert any('12개 조회 단위' in c.value for c in actual.caption)


def test_invalid_offsets_prevent_analysis(monkeypatch):
    monkeypatch.delenv('CREW_DEMO',raising=False)
    app=AppTest.from_file('app.py',default_timeout=15).run()
    app.number_input(key='dep_start').set_value(100).run()
    assert not app.exception
    assert any('조업 시작' in e.value for e in app.error)
    assert app.button[0].disabled
