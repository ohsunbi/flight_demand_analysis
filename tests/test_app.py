from streamlit.testing.v1 import AppTest


def test_analysis_completion_message_tracks_job_outcome(monkeypatch):
    from concurrent.futures import Future
    from threading import Event
    from adapters.ubikais_client import CollectionError
    from services import analysis
    from tests.fixtures import demo_result
    from ui import heatmap

    jobs=[]
    class FakeJob:
        def __init__(self,settings,*args,**kwargs):
            self.settings=settings
            self.future=Future()
            self.cancel=Event()
            jobs.append(self)
        def status(self):
            return 0.5,'검증용 작업'

    monkeypatch.delenv('CREW_DEMO',raising=False)
    monkeypatch.setattr(analysis,'Job',FakeJob)
    monkeypatch.setattr(heatmap,'display',lambda result: 0)
    app=AppTest.from_file('app.py',default_timeout=15).run()
    assert not app.success
    app.button(key='run_analysis').click().run()
    assert not app.success
    jobs[-1].future.set_result(demo_result(jobs[-1].settings))
    app.run()
    assert not app.exception
    assert any(e.value=='분석이 완료되었습니다. 아래에서 결과를 확인하세요.' for e in app.success)
    app.text_input(key='codes').set_value('KAL').run()
    assert not app.success
    app.button(key='run_analysis').click().run()
    assert not app.success
    jobs[-1].future.set_exception(CollectionError('검증용 실패'))
    app.run()
    assert not app.exception and not app.success and app.error
    app.button(key='run_analysis').click().run()
    jobs[-1].cancel.set()
    jobs[-1].future.set_result(demo_result(jobs[-1].settings))
    app.run()
    assert not app.exception and not app.success and app.error


def test_result_summary_shows_half_day_peaks_without_result_id(monkeypatch):
    from ui import heatmap
    monkeypatch.setenv('CREW_DEMO','1')
    monkeypatch.setattr(heatmap,'display',lambda result: 0)
    app=AppTest.from_file('app.py',default_timeout=15)
    app.query_params.update(dict(mode='custom',start='2026-10-25',end='2026-10-27'))
    app.run()
    assert not app.exception
    assert [m.label for m in app.metric[:3]]==['오전 최대 수요','오후 최대 수요','출발 / 도착 편수']
    assert all(m.label not in ('일별 최대의 평균','최대 수요 대표시각','분석 기간 최대 수요','월간 최대 수요') for m in app.metric)
    applied_caption=next(c.value for c in app.caption if c.value.startswith('적용 결과'))
    assert app.session_state.result.result_id not in applied_caption
    date_blocks=[e.proto.body for e in app.get('html') if 'summary-dates' in e.proto.body]
    assert len(date_blocks)==2
    assert all('발생일' in body for body in date_blocks)
    assert all('10/25' not in body for body in date_blocks)
    assert any('10월' in body and '25<span class="summary-weekday">(일)</span>' in body for body in date_blocks)
    assert [e.proto.label for e in app.get('download_button')]==['PNG','PDF']
    assert app.session_state.export_cache[1]=={}
    assert not any(e.value=='보고서 다운로드' for e in app.subheader)


def test_initial_app_does_not_fetch_automatically(monkeypatch):
    monkeypatch.delenv('CREW_DEMO',raising=False)
    app=AppTest.from_file('app.py',default_timeout=15).run()
    assert not app.exception
    assert 'result' not in app.session_state
    assert 'job' not in app.session_state
    assert app.radio(key='basis').value=='scheduled'
    assert app.radio(key='interval').value==60
    assert not app.text_input(key='codes').disabled
    assert all(r.key != 'airline_mode' for r in app.radio)
    assert app.text_input(key='codes').value=='JJA, TTW, AXM'
    assert all(not b.disabled for b in app.button)
    assert app.radio(key='basis').options==['계획 (STA/STD)', '실제 (RAMP IN/OUT)']
    assert app.selectbox(key='day_start').options==[f'{v//60:02d}:{v%60:02d}' for v in range(0,1440,30)]
    actual=AppTest.from_file('app.py',default_timeout=15)
    actual.query_params.update(dict(mode='custom',start='2026-10-26',end='2026-10-26',basis='actual',airlines='KAL,ESR'))
    actual.run()
    assert not actual.exception
    assert actual.text_input(key='codes').value=='ESR, KAL'
    assert not any('조회 단위' in c.value or '주소창 URL' in c.value for c in actual.caption)
    assert [b.label for b in actual.button]==['새로 조회','분석 실행']
    assert not actual.button[0].disabled
    assert 'job' not in actual.session_state


def test_invalid_offsets_prevent_analysis(monkeypatch):
    monkeypatch.delenv('CREW_DEMO',raising=False)
    app=AppTest.from_file('app.py',default_timeout=15).run()
    app.text_input(key='codes').set_value('ESR').run()
    app.number_input(key='dep_start').set_value(100).run()
    assert not app.exception
    assert any('출발편' in e.value and '조업 시작' in e.value for e in app.warning)
    assert all(b.disabled for b in app.button)
    assert 'job' not in app.session_state
    app.number_input(key='dep_start').set_value(-50).run()
    app.number_input(key='arr_end').set_value(10080).run()
    assert any('도착편' in e.value and '재투입 가능' in e.value for e in app.warning)
    assert all(b.disabled for b in app.button)
    app.number_input(key='arr_end').set_value(30).run()
    assert not app.exception
    assert not app.warning
    assert all(not b.disabled for b in app.button)


def test_airline_input_normalization_and_clear_blocks_queries(monkeypatch):
    monkeypatch.delenv('CREW_DEMO',raising=False)
    app=AppTest.from_file('app.py',default_timeout=15).run()
    app.text_input(key='codes').set_value(' esr, kal, ESR ').run()
    assert not app.exception
    assert app.query_params['airlines']==['ESR,KAL']
    assert all(not b.disabled for b in app.button)
    assert 'job' not in app.session_state
    app.text_input(key='codes').set_value(' , ').run()
    assert not app.exception
    assert all(b.disabled for b in app.button)
    assert 'job' not in app.session_state


def test_legacy_day_start_restored_and_half_hour_selection(monkeypatch):
    monkeypatch.delenv('CREW_DEMO',raising=False)
    app=AppTest.from_file('app.py',default_timeout=15)
    app.query_params.update(dict(day_start='195',airlines='KAL'))
    app.run()
    assert not app.exception
    assert app.selectbox(key='day_start').value==195
    assert app.text_input(key='codes').value=='KAL'
    assert app.query_params['day_start']==['195']
    app.selectbox(key='day_start').set_value(360).run()
    assert not app.exception
    assert app.query_params['day_start']==['360']
    assert 'job' not in app.session_state


def test_explicit_empty_airline_url_blocks_queries(monkeypatch):
    monkeypatch.delenv('CREW_DEMO',raising=False)
    app=AppTest.from_file('app.py',default_timeout=15)
    app.query_params.update(dict(airlines=''))
    app.run()
    assert not app.exception
    assert app.text_input(key='codes').value==''
    assert all(b.disabled for b in app.button)
    assert 'job' not in app.session_state


def test_invalid_icao_input_blocks_web_queries(monkeypatch):
    monkeypatch.delenv('CREW_DEMO',raising=False)
    app=AppTest.from_file('app.py',default_timeout=15).run()
    for code in ('7C','ZZ','3S','KAL1'):
        app.text_input(key='codes').set_value(code).run()
        assert not app.exception
        assert app.error and all(b.disabled for b in app.button)
        assert 'job' not in app.session_state


def test_unlisted_icao_and_unsupported_url_do_not_fetch(monkeypatch):
    monkeypatch.delenv('CREW_DEMO',raising=False)
    app = AppTest.from_file('app.py',default_timeout=15).run()
    app.text_input(key='codes').set_value(' xum, zzz, XUM ').run()
    assert not app.exception and not app.error
    assert app.query_params['v'] == ['4']
    assert app.query_params['airlines'] == ['XUM,ZZZ']
    assert all(not button.disabled for button in app.button)
    assert 'job' not in app.session_state
    legacy = AppTest.from_file('app.py',default_timeout=15)
    legacy.query_params.update(dict(v='2',airlines='7C,IT'))
    legacy.run()
    assert not legacy.exception
    assert legacy.warning
    assert legacy.text_input(key='codes').value == 'JJA, TTW, AXM'
    assert legacy.query_params['v'] == ['4']
    assert legacy.query_params['airlines'] == ['AXM,JJA,TTW']
    assert 'job' not in legacy.session_state


def test_travel_time_drives_reuse_and_demand(monkeypatch):
    from datetime import date, datetime
    from domain.models import Batch, KST
    from services.analysis import run_analysis
    from tests.fixtures import VERIFIED
    from ui.url_state import decode

    monkeypatch.delenv('CREW_DEMO',raising=False)
    app=AppTest.from_file('app.py',default_timeout=15)
    app.query_params.update(dict(mode='custom',start='2026-10-26',end='2026-10-26',dep='0,40,50'))
    app.run()
    assert not app.exception
    assert app.number_input(key='dep_travel').value==10
    assert app.number_input(key='dep_travel').min==0

    class Client:
        def fetch(self,airport,task,**kwargs):
            rows=()
            if task.day==date(2026,10,26) and task.direction=='dep':
                rows=tuple(dict(flightPk=str(i),fpId=f'JJA{i}',schDate='20261026',schTime=t)
                           for i,t in enumerate(('1000','1045')))
            return Batch(task.day,task.direction,task.airline,rows,datetime(2026,10,28,tzinfo=KST))

    def result():
        settings,error=decode({k:v[0] for k,v in app.query_params.items()},date(2026,10,28))
        assert not error
        return run_analysis(settings,Client(),VERIFIED)

    original=result()
    assert original.maximum==2
    assert (original.flights[0].reusable-original.flights[0].end).total_seconds()/60==10
    app.number_input(key='dep_travel').set_value(0).run()
    assert app.query_params['dep']==['0,40,40']
    assert result().maximum==1
    app.number_input(key='dep_end').set_value(50).run()
    assert app.query_params['dep']==['0,50,50']
    assert result().maximum==2
    assert not app.exception
    assert 'job' not in app.session_state
