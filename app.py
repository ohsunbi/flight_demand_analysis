from __future__ import annotations

import calendar
import os
from dataclasses import asdict
from datetime import date, datetime

import pandas as pd
import streamlit as st

from config import AIRPORTS, airport_airlines
from config.airline_codes import ICAO_TO_IATA, parse_icao_codes, to_iata_codes
from domain.models import KST, Offsets, Settings
from engine.demand import half_day_peaks
from services.analysis import Job, load_contract
from adapters.ubikais_client import UbikaisClient
from services.planner import plan
from ui import details, heatmap
from ui.summary import occurrence_dates
from ui.url_state import decode, encode

st.set_page_config(page_title='시간대별 램프조업 수요 분석', page_icon='✈', layout='wide')
st.markdown('''<style>
.block-container {padding-top:3.5rem; max-width:1800px}
.app-header {margin:0 0 12px}
.app-header-title {display:flex; align-items:center; gap:20px}
.app-header-title::before {content:""; flex:0 0 4px; height:clamp(28px,3vw,40px); background:#f15922; border-radius:2px}
.app-header h1 {margin:0; padding:0; color:#242424; font-size:clamp(1.6rem,2.5vw,2.4rem); line-height:1.3; font-weight:700; letter-spacing:-.035em; word-break:keep-all; overflow-wrap:anywhere}
.app-header p {margin:14px 0 0 24px; color:#59514c; font-size:.95rem; line-height:1.65; word-break:keep-all; overflow-wrap:anywhere}
@media (max-width:640px) {
  .app-header-title {gap:14px}
  .app-header p {margin-left:18px; margin-top:12px}
}
[data-testid="stMetricValue"] {color:#c2410c}
[data-testid="stSidebar"] {background:#f7f5f3}
.st-key-analysis_settings [data-testid="stVerticalBlock"] {gap:.5rem}
.st-key-analysis_settings hr {margin:.4rem 0}
.settings-section-title {display:flex; align-items:center; gap:8px; margin:0; padding:0; color:#242424; font-size:18px; line-height:1.4; font-weight:700; letter-spacing:-.02em}
.settings-section-title::before {content:""; flex:0 0 6px; height:6px; background:#f15922; border-radius:1px}
.st-key-work_times {padding-top:12px}
.st-key-analysis_actions {width:180px !important; margin-left:auto; display:flex !important; flex-direction:column; gap:12px !important}
.st-key-analysis_actions [data-testid="stElementContainer"],
.st-key-analysis_actions [data-testid="stButton"],
.st-key-analysis_actions [data-testid="stTooltipHoverTarget"],
.st-key-analysis_actions button {width:100% !important; max-width:none !important}
.st-key-refresh_data button {height:80px !important}
.st-key-run_analysis button {height:120px !important}
.st-key-refresh_data button, .st-key-run_analysis button {display:flex; align-items:center; justify-content:center}
.st-key-refresh_data button p {font-size:17px !important; font-weight:500; line-height:1.4}
.st-key-run_analysis button p {font-size:20px !important; font-weight:700; line-height:1.4}
.st-key-dep_time_card, .st-key-arr_time_card {box-sizing:border-box; min-height:212px; border:1px solid #ded8d3; border-radius:10px; padding:16px}
.st-key-work_times [data-testid="stColumn"]:has(> div .st-key-analysis_actions) {flex:0 0 180px; min-width:180px; max-width:180px; align-self:stretch}
@media (max-width:1100px) {
  .st-key-work_times [data-testid="stColumn"]:has(> div .st-key-analysis_actions) {flex:1 0 100%; min-width:100%; max-width:100%}
  .st-key-refresh_data button {height:48px !important}
  .st-key-run_analysis button {height:56px !important}
  .st-key-refresh_data button p {font-size:16px !important}
  .st-key-run_analysis button p {font-size:18px !important}
  .st-key-dep_time_card, .st-key-arr_time_card {min-height:0}
}
.work-time-heading {display:flex; align-items:baseline; justify-content:space-between; margin:0 0 10px; gap:12px}
.work-time-heading strong {color:#c2410c; font-size:1rem}
.work-time-heading span {color:#68625e; font-size:.8rem}
.work-time-label {color:#242424; font-size:.9rem; font-weight:600; margin:0 0 4px}
.st-key-summary_metrics [data-testid="stHorizontalBlock"] {align-items:stretch}
.st-key-summary_metrics [data-testid="stColumn"] {box-sizing:border-box; align-self:stretch; padding:20px 20px 16px; border:1px solid #ded8d3; border-radius:10px}
.summary-date-label {color:#68625e; font-size:13px; font-weight:400; white-space:nowrap}
.summary-dates {display:flex; align-items:flex-start; gap:8px; margin:12px 0 0; color:#242424; font-size:16px; font-weight:600; line-height:26px}
.summary-month-row {display:flex; align-items:flex-start; gap:10px}
.summary-month {color:#68625e; font-size:14px; font-weight:400; white-space:nowrap}
.summary-day {white-space:nowrap}
.summary-weekday {font-size:13px; font-weight:400; color:#68625e}
.st-key-work_times [data-testid="stCaptionContainer"] p {color:#68625e; font-size:.8rem; line-height:1.5}
</style>''', unsafe_allow_html=True)

if 'initial' not in st.session_state:
    initial, error = decode(dict(st.query_params), datetime.now(KST).date())
    st.session_state.initial = initial
    st.session_state.url_error = error
initial = st.session_state.initial
if 'codes' not in st.session_state:
    st.session_state.codes = ','.join(initial.airlines)
contract = load_contract()

st.caption('RAMP HANDLING  /  RESOURCE PLANNING')
st.html('''<header class="app-header">
<div class="app-header-title"><h1>시간대별 램프조업 수요 분석</h1></div>
<p>운항 스케줄과 조업 소요시간을 바탕으로 <strong>시간대별 필요 조 개수</strong>를 확인하세요.</p>
</header>''')
if st.session_state.get('url_error'):
    st.warning(st.session_state.url_error)
if not contract.verified:
    st.warning('UBIKAIS 데이터 계약 검증 중입니다. 실자료 조회는 잠정 분석으로 표시되며 정식 보고서 출력은 제한됩니다.')

def airport_changed():
    st.session_state.codes = ', '.join(airport_airlines(st.session_state.airport))


settings_panel = st.container(border=True, key='analysis_settings')
with settings_panel:
    target_col, period_col, time_col = st.columns(3, gap='medium')
    with target_col:
        st.html('<h2 class="settings-section-title">조회 대상</h2>')
        airport = st.selectbox('공항', list(AIRPORTS), index=list(AIRPORTS).index(initial.airport),
                               format_func=lambda x: f'{AIRPORTS[x][0]} · {AIRPORTS[x][1] or x} ({x})', key='airport', width=360,
                               on_change=airport_changed)
        try:
            preview_input = st.session_state.get('codes', ','.join(initial.airlines))
            parse_icao_codes(preview_input, allow_empty=True)
            preview_codes = tuple(dict.fromkeys(code.strip().upper() for code in preview_input.split(',') if code.strip()))
        except ValueError:
            preview_codes = ()
        code_help = ['ICAO 영문 3자리 코드로 입력하세요. 여러 항공사는 쉼표(,)로 구분합니다.']
        mapped = [ICAO_TO_IATA[code] for code in preview_codes if code in ICAO_TO_IATA]
        if mapped:
            code_help.append(f'\\* 입력된 코드(IATA) : {", ".join(mapped)}')
        unknown = [code for code in preview_codes if code not in ICAO_TO_IATA]
        if unknown:
            code_help.append(f'변환 정보 없음: {", ".join(unknown)}')
        if not preview_codes:
            code_help.append('항공사 코드를 입력·확인하세요.')
        codes = st.text_input('항공사 코드 (ICAO 3자리)', value=None, placeholder='JJA, TTW, AXM', key='codes', width=360,
                              help='\n\n'.join(code_help))
    with period_col:
        st.html('<h2 class="settings-section-title">조회 기간</h2>')
        mode = st.radio('기간 선택', ['month', 'custom'], index=0 if initial.mode == 'month' else 1,
                        format_func=lambda x: '월별' if x == 'month' else '사용자 지정', horizontal=True, key='mode')
        if mode == 'month':
            with st.container(width=360):
                ycol, mcol = st.columns(2)
                year = ycol.number_input('연도', min_value=2000, max_value=2100, value=initial.start.year, step=1, key='year')
                month = mcol.selectbox('월', list(range(1,13)), index=initial.start.month-1, key='month')
            start = date(year, month, 1); end = date(year, month, calendar.monthrange(year, month)[1])
        else:
            dates = st.date_input('시작일 ~ 종료일 (최대 31일)', value=(initial.start, initial.end), format='YYYY-MM-DD', key='dates', width=360)
            start, end = (dates[0], dates[-1]) if len(dates) == 2 else (None, None)
    with time_col:
        st.html('<h2 class="settings-section-title">시간 설정</h2>')
        basis = st.radio('분석 기준시각', ['scheduled', 'actual'], index=0 if initial.basis == 'scheduled' else 1,
                         format_func=lambda x: '계획 (STA/STD)' if x == 'scheduled' else '실제 (RAMP IN/OUT)',
                         horizontal=True, key='basis', help='실제는 RAMP IN/OUT 기준이며, 값이 없으면 STA/STD를 사용합니다.')
        interval_col, day_col = st.columns(2)
        interval = interval_col.radio('분석 간격', [60, 30], index=0 if initial.interval == 60 else 1,
                                     format_func=lambda x: f'{x}분', horizontal=True, key='interval')
        day_starts = sorted(set(range(0, 1440, 30)) | {initial.day_start})
        ds = day_col.selectbox('조업 개시 시간', day_starts, index=day_starts.index(initial.day_start),
                               format_func=lambda v: f'{v//60:02d}:{v%60:02d}', key='day_start', width=160,
                               help='한국시간 기준, 선택한 시각부터 24시간을 하루로 집계합니다. 예: 06:00부터 다음 날 06:00까지. 기존 URL의 분 단위 값은 그대로 복원합니다.')
    st.divider()
    with st.container(key='work_times'):
        dep_col, arr_col, action_col = st.columns([1, 1, .32], gap='medium')
        with action_col:
            actions = st.container(key='analysis_actions')
        direction_cols = (dep_col, arr_col)
        offsets = []
        for direction_col, name, value, prefix in zip(direction_cols, ['출발', '도착'], [initial.dep, initial.arr], ['dep', 'arr']):
            reference_label = ('STD' if prefix == 'dep' else 'STA') if basis == 'scheduled' else ('RAMP OUT' if prefix == 'dep' else 'RAMP IN')
            with direction_col, st.container(border=False, key=f'{prefix}_time_card'):
                st.html(f'<div class="work-time-heading"><strong>{name}편 시간 설정</strong><span>단위: 분</span></div>')
                row = st.columns(3, gap='small')
                vals = []
                for col, label, key, v in zip(row[:2], ['조업 시작', '조업 종료'], ['start', 'end'], [value.start, value.end]):
                    with col:
                        st.html(f'<p class="work-time-label">{label}</p>')
                        minutes = st.number_input(f'{name}편 {label} (분)', min_value=-10080, max_value=10080,
                                                  value=v, step=1, key=f'{prefix}_{key}', label_visibility='collapsed')
                        st.caption(f'{reference_label} {abs(minutes)}분 {"전" if minutes < 0 else "후"}' if minutes else f'{reference_label} 시각')
                        vals.append(minutes)
                with row[2]:
                    st.html('<p class="work-time-label">이동소요 시간</p>')
                    travel = st.number_input(f'{name}편 이동소요 시간 (분)', min_value=0, max_value=20160,
                                             value=value.reusable-value.end, step=1, key=f'{prefix}_travel',
                                             label_visibility='collapsed', help='조업 종료 후 다음 작업에 투입되기까지 필요한 시간입니다.')
                    st.caption(f'조업 종료 후 {travel}분')
            offsets.append(Offsets(vals[0], vals[1], vals[1]+travel))

settings = None
invalid_offsets = []
for name, value in zip(('출발편', '도착편'), offsets):
    if value.start > value.end:
        invalid_offsets.append(f'{name}: 조업 시작은 조업 종료보다 늦을 수 없습니다.')
    if abs(value.reusable) > 10080:
        invalid_offsets.append(f'{name}: 조업 종료 + 이동소요 시간으로 계산한 재투입 가능 시각은 기준시각 대비 ±7일 이내여야 합니다.')
try:
    if invalid_offsets:
        raise ValueError(' '.join(invalid_offsets))
    if start is None or end is None:
        raise ValueError('시작일과 종료일을 모두 선택하세요.')
    airlines = parse_icao_codes(codes)
    settings = Settings(airport, start, end, mode, airlines, basis, ds, interval, *offsets)
    tasks = plan(settings, actual_query_padding_days=(contract.actual_query_padding_days or 0) if basis == 'actual' else 0)
    params = encode(settings)
    if dict(st.query_params) != params:
        st.query_params.from_dict(params)
except ValueError as exc:
    if invalid_offsets:
        st.warning(str(exc))
    else:
        st.error(str(exc))
    settings = None

busy = 'job' in st.session_state
with actions:
    refresh = st.button('새로 조회', key='refresh_data', width=180, disabled=not settings or busy,
                        help='캐시를 사용하지 않고 현재 입력 조건의 운항자료를 다시 수집해 분석합니다.')
    run = st.button('분석 실행', key='run_analysis', type='primary', width=180, disabled=not settings or busy,
                    help='유효한 캐시를 활용하고, 없거나 만료된 자료는 조회해 분석합니다.')

if run or refresh:
    st.session_state.pop('completed_result_id', None)
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
            st.session_state.completed_result_id = result.result_id
            st.session_state.cell_selection = 0
            st.session_state.pop('downloads', None)
            st.session_state.pop('export_cache', None)
            st.session_state.pop('job_error', None)
        except Exception as exc:
            st.session_state.pop('completed_result_id', None)
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
    st.info('조건을 선택하고 분석 실행을 누르세요. 분석은 최대 31개 운영일까지 가능합니다.')
    st.stop()

applied = result.settings
dirty = settings is None or settings.signature != applied.signature
if (not dirty and 'job' not in st.session_state and not st.session_state.get('job_error')
        and st.session_state.get('completed_result_id') == result.result_id):
    st.success('분석이 완료되었습니다. 아래에서 결과를 확인하세요.')
if dirty:
    st.info('입력 조건이 변경되었습니다. 아래는 이전 조회 결과입니다. 새 조건을 적용하려면 분석 실행을 누르세요.')
name, iata = AIRPORTS[applied.airport]
st.divider()
st.caption(f'적용 결과 · {name} {iata} · {applied.start} ~ {applied.end} · {"전체 항공사" if not applied.airlines else ", ".join(to_iata_codes(applied.airlines))} · {"계획 (STA/STD)" if applied.basis == "scheduled" else "실제 (RAMP IN/OUT)"} · 분석 간격 {applied.interval}분')
if result.synthetic:
    st.warning('개발 검증용 가상 데이터입니다. 실제 운항자료가 아닙니다.')
for blocker in result.blockers:
    st.warning(blocker)
with st.container(key='summary_metrics'):
    metrics = st.columns(3, gap='medium')
    for col, label, key, (maximum, dates) in zip(metrics[:2], ['오전 최대 수요', '오후 최대 수요'], ['summary_am', 'summary_pm'], half_day_peaks(result)):
        with col, st.container(border=False, key=key):
            st.metric(label, f'{maximum}개 조', help='한국시간 기준 오전 00:00부터 12:00 미만, 오후 12:00부터 다음 날 00:00 미만입니다. 분석 범위에 포함된 구간만 집계합니다.')
            st.html(occurrence_dates(dates))
    with metrics[2], st.container(border=False, key='summary_flights'):
        st.metric('출발 / 도착 편수', f'{sum(c.dep_count for c in result.cells)} / {sum(c.arr_count for c in result.cells)}')
if applied.basis == 'actual':
    st.caption(f'기간 편수 기준: 실제시각 사용 {result.diagnostics.actual_used}편 (그중 실제 날짜 추정 {result.diagnostics.actual_date_inferred}편) · 예정 대체 {result.diagnostics.scheduled_used}편')
    if result.diagnostics.actual_date_inferred:
        st.info('날짜 없는 주기장 시각은 예정시각에 가장 가까운 날짜로 계산했습니다. 하루 이상 지연된 운항은 날짜를 잘못 배치할 수 있습니다.')

left, right = st.columns([2.2, 1], gap='large')
with left:
    title_col, download_col = st.columns([1.1, 1], vertical_alignment='center')
    title_col.subheader('시간대별 조업조 수요')
    from reports.render import lazy_download, output_stem
    saved_exports = st.session_state.get('export_cache')
    if saved_exports is None or saved_exports[0] != result.result_id or len(saved_exports) < 3 or saved_exports[2] != 'unified-a4-v10':
        saved_exports = (result.result_id, {}, 'unified-a4-v10')
        st.session_state.export_cache = saved_exports
    export_disabled = not result.exportable or settings is None
    stem = output_stem(result)
    with download_col, st.container(horizontal=True, horizontal_alignment='right', gap='small'):
        download_menu = st.popover('다운로드', icon=':material/download:', disabled=export_disabled)
    with download_menu:
        for label, kind, extension, mime in [('PNG', 'png', 'zip' if applied.interval==30 else 'png', 'application/zip' if applied.interval==30 else 'image/png'),
                                             ('PDF', 'pdf', 'pdf', 'application/pdf')]:
            st.download_button(label, lazy_download(result, kind, saved_exports[1]),
                               file_name=f'{stem}.{extension}', mime=mime,
                               key=f'export_{kind}_{result.result_id}', on_click='ignore', disabled=export_disabled, width='stretch')
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
