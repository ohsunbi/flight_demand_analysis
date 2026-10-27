from __future__ import annotations

import calendar
import os
from dataclasses import asdict
from datetime import date, datetime, time

import pandas as pd
import streamlit as st

from config import AIRPORTS, legend_ranges
from domain.models import KST, Offsets, Settings
from services.analysis import Job, load_contract
from adapters.ubikais_client import UbikaisClient
from services.planner import plan
from ui import details, heatmap
from ui.url_state import decode, encode

st.set_page_config(page_title='Flight Crew Demand Analysis', page_icon='✈', layout='wide')
st.markdown('''<style>
.block-container {padding-top:3.5rem; max-width:1800px}
h1 {letter-spacing:-.04em} [data-testid="stMetricValue"] {color:#17636e}
[data-testid="stSidebar"] {background:#f5f8fa}
</style>''', unsafe_allow_html=True)

if 'initial' not in st.session_state:
    initial, error = decode(dict(st.query_params), datetime.now(KST).date())
    st.session_state.initial = initial
    st.session_state.url_error = error
initial = st.session_state.initial
contract = load_contract()

st.caption('FLIGHT OPERATIONS  /  RESOURCE PLANNING')
st.title('Flight Crew Demand Analysis')
st.write('운항편의 조업·재투입 대기시간을 반영한 **동시 조업조 수요**를 확인하세요.')
if st.session_state.get('url_error'):
    st.warning(st.session_state.url_error)
if not contract.verified:
    st.warning('UBIKAIS 데이터 계약 검증 중입니다. 실자료 조회는 잠정 분석으로 표시되며 정식 보고서 출력은 제한됩니다.')

with st.container(border=True):
    c1, c2, c3, c4 = st.columns([1.1, 1, 1.4, 1.5])
    airport = c1.selectbox('공항', list(AIRPORTS), index=list(AIRPORTS).index(initial.airport),
                           format_func=lambda x: f'{AIRPORTS[x][0]} · {AIRPORTS[x][1] or x} ({x})', key='airport')
    mode = c2.radio('기간 선택', ['month', 'custom'], index=0 if initial.mode == 'month' else 1,
                    format_func=lambda x: '월별' if x == 'month' else '사용자 지정', horizontal=True, key='mode')
    if mode == 'month':
        ycol, mcol = c3.columns(2)
        year = ycol.number_input('연도', min_value=2000, max_value=2100, value=initial.start.year, step=1, key='year')
        month = mcol.selectbox('월', list(range(1,13)), index=initial.start.month-1, key='month')
        start = date(year, month, 1); end = date(year, month, calendar.monthrange(year, month)[1])
    else:
        dates = c3.date_input('시작일 ~ 종료일 (최대 31일)', value=(initial.start, initial.end), format='YYYY-MM-DD', key='dates')
        start, end = (dates[0], dates[-1]) if len(dates) == 2 else (None, None)
    basis = c4.radio('시간 기준', ['scheduled', 'actual'], index=0 if initial.basis == 'scheduled' else 1,
                     format_func=lambda x: '예정' if x == 'scheduled' else '실제 주기장 우선', horizontal=True, key='basis')
    a1, a2, a3 = st.columns([1, 2, 1])
    airline_mode = a1.radio('항공사 범위', ['전체', '특정 복수'], index=int(bool(initial.airlines)), horizontal=True, key='airline_mode')
    codes = a2.text_input('항공사 코드 (영문 3자리, 쉼표로 구분)', value=','.join(initial.airlines), disabled=airline_mode == '전체', placeholder='ESR, KAL, AAR', key='codes')
    interval = a3.radio('시간 셀', [60, 30], index=0 if initial.interval == 60 else 1,
                        format_func=lambda x: f'{x}분', horizontal=True, key='interval')
    with st.expander('조업시간 · 운영일 설정'):
        ds = st.time_input('운영일 시작 (한국시간)', value=time(initial.day_start//60, initial.day_start%60), step=60, key='day_start')
        st.caption('기준시각 전은 음수, 후는 양수인 분 단위입니다. 조업 종료 후 재투입 대기시간도 조를 점유합니다.')
        oc = st.columns(2)
        offsets = []
        for col, name, value, prefix in [(oc[0], '출발', initial.dep, 'dep'), (oc[1], '도착', initial.arr, 'arr')]:
            col.markdown(f'**{name}**')
            sub = col.columns(3)
            vals = [sub[i].number_input(label, min_value=-10080, max_value=10080, value=v, step=1, key=f'{prefix}_{key}')
                    for i, (label, key, v) in enumerate(zip(['시작 (분)', '조업 종료 (분)', '재투입 (분)'], ['start','end','reusable'], [value.start,value.end,value.reusable]))]
            offsets.append(Offsets(*vals))

settings = None
try:
    if start is None or end is None:
        raise ValueError('시작일과 종료일을 모두 선택하세요.')
    airlines = tuple(sorted(set(c.strip().upper() for c in codes.split(',') if c.strip()))) if airline_mode != '전체' else ()
    if airline_mode != '전체' and not airlines:
        raise ValueError('항공사 코드를 한 개 이상 입력하세요.')
    settings = Settings(airport, start, end, mode, airlines, basis, ds.hour*60+ds.minute, interval, *offsets)
    tasks = plan(settings, actual_query_padding_days=(contract.actual_query_padding_days or 0) if basis == 'actual' else 0)
    params = encode(settings)
    if dict(st.query_params) != params:
        st.query_params.from_dict(params)
except ValueError as exc:
    st.error(str(exc)); settings = None

busy = 'job' in st.session_state
b1, b2, info = st.columns([1,1,4])
run = b1.button('조회 · 분석 실행', type='primary', width='stretch', disabled=not settings or busy)
refresh = b2.button('데이터 새로고침', width='stretch', disabled=not settings or busy,
                    help='캐시를 우회하고 현재 입력 조건으로 다시 조회합니다.')
if settings:
    info.caption(f'{settings.days}개 운영일 · 출발/도착·보충일 포함 {len(tasks)}개 조회 단위 + 필요한 추가 페이지\n주소창 URL로 현재 설정을 공유할 수 있습니다. URL을 열어도 자동 조회하지 않습니다.')

if run or refresh:
    cookie = os.getenv('UBIKAIS_COOKIE')
    if not cookie:
        try:
            cookie = st.secrets.get('UBIKAIS_COOKIE')
        except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
            cookie = None
    st.session_state.job = Job(settings, UbikaisClient(cookie=cookie), contract, refresh=refresh)
    st.rerun()


@st.fragment(run_every='1s')
def job_status():
    job = st.session_state.get('job')
    if job is None:
        return
    fraction, message = job.status()
    st.progress(fraction, text=message)
    if st.button('조회 중단', key='cancel_job'):
        job.cancel.set()
    if job.future.done():
        try:
            result = job.future.result()
            if job.cancel.is_set():
                from adapters.ubikais_client import Cancelled
                raise Cancelled('조회가 중단되었습니다. 이전 결과를 유지했습니다.')
            st.session_state.result = result
            st.session_state.cell_selection = 0
            st.session_state.pop('downloads', None)
            st.session_state.pop('job_error', None)
        except Exception as exc:
            # Known service failures contain sanitized messages. Unexpected internals stay hidden.
            from adapters.ubikais_client import CollectionError
            st.session_state.job_error = str(exc) if isinstance(exc, (CollectionError, ValueError)) else '분석 중 오류가 발생했습니다. 기존 결과를 유지했습니다.'
        del st.session_state.job
        st.rerun()

if 'job' in st.session_state:
    job_status()
if st.session_state.get('job_error'):
    st.error(st.session_state.job_error)

# Explicit development-only fixture mode is not exposed as a data source in the product.
if os.getenv('CREW_DEMO') == '1' and 'result' not in st.session_state and settings:
    from tests.fixtures import demo_result
    st.session_state.result = demo_result(settings)

result = st.session_state.get('result')
if result is None:
    st.info('조건을 선택하고 조회 · 분석 실행을 누르세요. 분석은 최대 31개 운영일까지 가능합니다.')
    st.stop()

applied = result.settings
dirty = settings is None or settings.signature != applied.signature
if dirty:
    st.info('입력 조건이 변경되었습니다. 아래는 이전 조회 결과입니다. 새 조건을 적용하려면 조회 · 분석 실행을 누르세요.')
name, iata = AIRPORTS[applied.airport]
st.divider()
st.caption(f'적용 결과 · {name} {iata} · {applied.start} ~ {applied.end} · {"전체 항공사" if not applied.airlines else ", ".join(applied.airlines)} · {"예정" if applied.basis == "scheduled" else "실제 주기장 우선"} · {applied.interval}분 셀 · 결과 {result.result_id}')
if result.synthetic:
    st.warning('개발 검증용 가상 데이터입니다. 실제 운항자료가 아닙니다.')
for blocker in result.blockers:
    st.warning(blocker)
metrics = st.columns(4)
metrics[0].metric('월간 최대 수요' if applied.mode == 'month' else '분석 기간 최대 수요', f'{result.maximum}개 조')
metrics[1].metric('일별 최대의 평균', f'{sum(result.daily_max)/len(result.daily_max):.1f}개 조')
peak = result.peak_cell
metrics[2].metric('최대 수요 대표시각', peak.peak.strftime('%m-%d %H:%M') if peak else '없음')
metrics[3].metric('출발 / 도착 편수', f'{sum(c.dep_count for c in result.cells)} / {sum(c.arr_count for c in result.cells)}')
if peak:
    st.caption(f'최대 발생 운영일 {peak.operating_day} · 대표 피크 순간 출발 {peak.dep_active}개 조 + 도착 {peak.arr_active}개 조')
if applied.basis == 'actual':
    st.caption(f'기간 편수 기준: 실제시각 사용 {result.diagnostics.actual_used}편 (그중 실제 날짜 추정 {result.diagnostics.actual_date_inferred}편) · 예정 대체 {result.diagnostics.scheduled_used}편')
    if result.diagnostics.actual_date_inferred:
        st.info('날짜 없는 주기장 시각은 예정시각에 가장 가까운 날짜로 계산했습니다. 하루 이상 지연된 운항은 날짜를 잘못 배치할 수 있습니다.')

left, right = st.columns([2.2, 1], gap='large')
with left:
    st.subheader('시간대별 최대 필요 조업조')
    st.caption(f'전체 기간 공통 범례 0~{result.maximum}개 조 · 셀을 클릭하면 오른쪽에서 상세를 확인합니다. ⁺¹은 다음 달력 날짜입니다.')
    st.html('<div style="display:flex;gap:12px;flex-wrap:wrap;margin:6px 0 14px;font-size:12px">' + ''.join(
        f'<span><span style="display:inline-block;width:18px;height:12px;background:{color};border:1px solid #dce5ea;margin-right:4px"></span>{label}개 조</span>'
        for color,label in legend_ranges(result.maximum)) + '</div>')
    selected = heatmap.display(result)
with right:
    details.display(result, selected)

with st.expander('데이터 품질 · 추가 분석'):
    diag = result.diagnostics
    st.write(f'수집 {diag.raw}건 · 완전 중복 {diag.duplicates}건 · 확인된 결항 제외 {diag.cancelled}건 · 격리 {diag.quarantined}건')
    st.write(f'기간 편수 중 실제시각 사용 {diag.actual_used}편 (실제 날짜 추정 {diag.actual_date_inferred}편 포함) · 예정시각 사용 {diag.scheduled_used}편')
    for message in diag.messages:
        st.write(message)
    st.caption(f'자료 수집: {result.collected_from:%Y-%m-%d %H:%M:%S} ~ {result.collected_until:%Y-%m-%d %H:%M:%S} KST')
    st.caption(f'자료 버전 {result.data_version or "가상 자료"} · 정규화 v1 / 계산 엔진 v1')
    hist = result.histogram_minutes
    st.dataframe(pd.DataFrame([{'필요 조업조': k, '정확히 해당 조 수 (분)': v,
                               '해당 조 수 이상 (분)': sum(t for j,t in hist.items() if j >= k)} for k,v in hist.items()]), hide_index=True)
    st.caption(f'기간 총 점유량: {sum(result.daily_crew_minutes)/60:.1f} 조·시간. 0조 수요 시간도 포함합니다.')

st.subheader('보고서 다운로드')
if not result.exportable:
    st.caption('데이터 계약 또는 품질 확인이 완료되지 않아 정식 내보내기가 비활성화되었습니다.')
elif settings is None:
    st.caption('잘못된 입력을 수정하면 현재 적용 결과의 보고서를 생성할 수 있습니다.')
else:
    if st.button('현재 적용 결과의 PNG · PDF 생성', key='generate_reports'):
        from reports.render import build_downloads
        try:
            with st.spinner('전체 날짜와 시간 열을 포함한 보고서를 생성합니다…'):
                st.session_state.downloads = (result.result_id, build_downloads(result))
        except Exception:
            st.error('보고서 생성에 실패했습니다. 배포 글꼴과 출력 환경을 확인하세요.')
    saved = st.session_state.get('downloads')
    if saved and saved[0] == result.result_id:
        files = saved[1]
        d1, d2 = st.columns(2)
        d1.download_button('PNG 다운로드' if files['png_name'].endswith('.png') else 'PNG 묶음 다운로드', files['png'], files['png_name'], files['png_mime'], width='stretch')
        d2.download_button('PDF 다운로드', files['pdf'], files['pdf_name'], 'application/pdf', width='stretch')
