from dataclasses import replace
from datetime import date, datetime
from io import BytesIO

import pytest
from pypdf import PdfReader
from streamlit.testing.v1 import AppTest

from domain.models import Batch, Diagnostics, KST, Offsets, Settings
from engine.demand import analyze
from normalization.flights import normalize
from reports.render import build_export
from services.analysis import run_analysis
from services.planner import plan
from tests.fixtures import VERIFIED, demo_result
from ui.url_state import decode, encode


DAY = date(2026, 10, 26)
AT = datetime(2026, 10, 28, tzinfo=KST)


def settings(**kwargs):
    return Settings('RKSI', DAY, DAY, mode='custom', airlines=('JJA',), **kwargs)


@pytest.mark.parametrize('directions', [('dep',), ('arr',), ('dep', 'arr')])
def test_direction_settings_url_and_signature(directions):
    s = settings(directions=directions)
    assert decode(encode(s), DAY) == (s, None)
    assert {task.direction for task in plan(s)} == set(directions)
    assert s.signature == settings(directions=directions).signature
    if len(directions) == 1:
        assert s.signature != settings().signature


@pytest.mark.parametrize('value', ['', 'dep,dep', 'arr,dep', 'other'])
def test_invalid_direction_url_falls_back_safely(value):
    restored, error = decode({'directions': value}, DAY)
    assert error and restored.directions == ('dep', 'arr')


def test_legacy_url_without_directions_keeps_both():
    params = encode(settings())
    params.pop('directions')
    assert decode(params, DAY) == (settings(), None)
    with pytest.raises(ValueError, match='하나 이상'):
        settings(directions=()).validate()


@pytest.mark.parametrize('bad', [Offsets(100, 30, 40), Offsets(0, 10080, 10090)])
def test_disabled_offsets_preserved_but_validated_when_enabled(bad):
    s = settings(directions=('dep',), arr=bad)
    s.validate()
    assert decode(encode(s), DAY) == (s, None)
    assert {t.direction for t in plan(s)} == {'dep'}
    with pytest.raises(ValueError):
        replace(s, directions=('dep', 'arr')).validate()


@pytest.mark.parametrize('direction', ['dep', 'arr'])
@pytest.mark.parametrize('basis', ['scheduled', 'actual'])
def test_service_never_requests_excluded_direction(direction, basis):
    calls = []

    class Client:
        def fetch(self, airport, task, **kwargs):
            calls.append(task.direction)
            assert task.direction == direction
            rows = ()
            if task.day == DAY:
                rows = (dict(flightPk='one', fpId='JJA100', schDate='20261026', schTime='1000',
                             staDate='20261026', sta='1000', blockOffTime='202610261100',
                             blockOnTime='202610261100'),)
            return Batch(task.day, task.direction, task.airline, rows, AT)

    result = run_analysis(settings(directions=(direction,), basis=basis), Client(), VERIFIED)
    assert calls and set(calls) == {direction}
    assert len(result.flights) == 1 and result.exportable
    assert sum(c.dep_count for c in result.cells) == int(direction == 'dep')
    assert sum(c.arr_count for c in result.cells) == int(direction == 'arr')
    assert result.flights[0].reference.hour == (11 if basis == 'actual' else 10)


@pytest.mark.parametrize('direction', ['dep', 'arr'])
def test_core_excludes_opposite_direction_even_with_mixed_input(direction):
    both = demo_result(settings())
    s = replace(both.settings, directions=(direction,))
    result = analyze(s, both.flights, Diagnostics(), AT, AT)
    expected = analyze(s, tuple(f for f in both.flights if f.direction == direction), Diagnostics(), AT, AT)
    assert result.cells == expected.cells
    assert result.segments == expected.segments
    assert result.flights and all(f.direction == direction for f in result.flights)
    excluded = 'arr' if direction == 'dep' else 'dep'
    flights, diagnostics = normalize((Batch(DAY, excluded, '', ({'invalid': True},), AT),), s, VERIFIED)
    assert not flights and diagnostics.raw == diagnostics.quarantined == 0


def test_ui_excluded_invalid_inputs_and_restore(monkeypatch):
    monkeypatch.delenv('CREW_DEMO', raising=False)
    app = AppTest.from_file('app.py', default_timeout=15).run()
    assert app.checkbox(key='dep_included').value and app.checkbox(key='arr_included').value
    app.number_input(key='arr_start').set_value(100).run()
    assert app.warning and app.button(key='run_analysis').disabled
    app.checkbox(key='arr_included').uncheck().run()
    assert not app.exception and not app.error and not app.warning
    assert not app.button(key='run_analysis').disabled
    assert app.number_input(key='arr_start').disabled
    assert app.number_input(key='arr_start').value == 100
    assert app.query_params['directions'] == ['dep']
    restored = AppTest.from_file('app.py', default_timeout=15)
    restored.query_params.update({k: v[0] for k, v in app.query_params.items()})
    restored.run()
    assert not restored.exception and not restored.error
    assert not restored.checkbox(key='arr_included').value
    assert restored.number_input(key='arr_start').value == 100
    app.checkbox(key='dep_included').uncheck().run()
    assert app.error and app.button(key='run_analysis').disabled and app.button(key='refresh_data').disabled
    app.checkbox(key='arr_included').check().run()
    assert app.warning and app.button(key='run_analysis').disabled
    app.number_input(key='arr_start').set_value(-20).run()
    assert not app.exception and not app.error and not app.warning
    assert not app.button(key='run_analysis').disabled
    assert 'job' not in app.session_state


@pytest.mark.parametrize('direction', ['dep', 'arr'])
def test_single_direction_result_ui_marks_excluded_counts(monkeypatch, direction):
    from ui import heatmap
    monkeypatch.setattr(heatmap, 'display', lambda result: 0)
    monkeypatch.setenv('CREW_DEMO', '1')
    app = AppTest.from_file('app.py', default_timeout=15)
    app.query_params.update(encode(settings(directions=(direction,))))
    app.run()
    assert not app.exception and not app.error
    metric = next(m for m in app.metric if m.label == '출발 / 도착 편수')
    assert metric.value == ('16 / —' if direction == 'dep' else '— / 16')
    assert any('분석 대상:' in c.value for c in app.caption)
    assert any('—' in c.value and '조업 편수' in c.value for c in app.caption)
    app.checkbox(key=f'{"arr" if direction == "dep" else "dep"}_included').check().run()
    assert any('이전 조회 결과' in info.value for info in app.info)
    updated_metric = next(m for m in app.metric if m.label == '출발 / 도착 편수')
    assert updated_metric.value == ('16 / —' if direction == 'dep' else '— / 16')


@pytest.mark.parametrize('direction', ['dep', 'arr'])
@pytest.mark.parametrize('interval', [60, 30])
def test_single_direction_report_keeps_scope_and_dash(direction, interval):
    result = demo_result(settings(directions=(direction,), interval=interval))
    reader = PdfReader(BytesIO(build_export(result, 'pdf')))
    assert len(reader.pages) == (1 if interval == 60 else 2)
    included, excluded = ('출발편', '도착편') if direction == 'dep' else ('도착편', '출발편')
    for page in reader.pages:
        text = page.extract_text()
        assert f'분석 대상 : {included}' in text
        assert f'{excluded}   분석 제외' in text
        assert '—' in text and ('16 / —편' if direction == 'dep' else '— / 16편') in text
