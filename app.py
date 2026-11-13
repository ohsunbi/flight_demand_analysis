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
from ui.help import display_help
from ui.url_state import decode, encode

st.set_page_config(page_title='시간대별 램프조업 수요 분석', page_icon='✈', layout='wide')
st.markdown('''<style>
.block-container {padding-top:1.9rem; max-width:1800px}
.app-header {margin:0 0 8px}
.app-header-eyebrow {margin:0 0 2px 20px; color:#8b8580; font-size:.68rem; line-height:1.2; letter-spacing:.04em}
.app-header-title {display:flex; align-items:center; gap:20px}
.app-header-title::before {content:""; flex:0 0 4px; height:clamp(28px,3vw,40px); background:#f15922; border-radius:2px}
.app-header h1 {margin:0; padding:0; color:#242424; font-size:clamp(1.3rem,1.8vw,1.8rem); line-height:1.25; font-weight:700; letter-spacing:-.035em; word-break:keep-all; overflow-wrap:anywhere}
@media (max-width:640px) {
  .app-header-title {gap:14px}
  .app-header-eyebrow {margin-left:18px}
}
[data-testid="stMetricValue"] {color:#c2410c}
[data-testid="stSidebar"] {background:#f7f5f3}
.st-key-analysis_settings [data-testid="stVerticalBlock"] {gap:.35rem}
.st-key-analysis_settings hr {margin:.2rem 0}
.inline-field-label {color:#5f5a56; font-size:.78rem; font-weight:500; white-space:nowrap}
.inline-direction-label {color:#242424; font-size:.88rem; font-weight:600; white-space:nowrap}
.st-key-filter_row [data-testid="stHorizontalBlock"] {align-items:flex-start; gap:.8rem}
.st-key-condition_row [data-testid="stLayoutWrapper"]:has(.st-key-dep_group),
.st-key-condition_row [data-testid="stLayoutWrapper"]:has(.st-key-arr_group),
.st-key-dep_group, .st-key-arr_group {flex:0 0 auto !important; width:fit-content !important}
.st-key-dep_group [data-testid="stHorizontalBlock"],
.st-key-arr_group [data-testid="stHorizontalBlock"] {gap:.5rem !important}
.st-key-dep_direction_toggle,
.st-key-arr_direction_toggle {box-sizing:border-box; padding-inline:.5rem !important}
.st-key-condition_row [data-testid="stLayoutWrapper"]:has(.st-key-analysis_actions) {margin-left:auto !important}
.st-key-condition_row [data-testid="stElementContainer"]:has([data-testid="stNumberInput"]) {flex-grow:0 !important; min-width:0 !important}
.st-key-analysis_actions {width:auto !important; min-width:200px; max-width:280px; margin:0 0 0 auto !important; display:flex !important; flex-direction:column; align-items:stretch; gap:.4rem !important}
.st-key-analysis_actions [data-testid="stElementContainer"],
.st-key-analysis_actions [data-testid="stButton"],
.st-key-analysis_actions [data-testid="stTooltipHoverTarget"],
.st-key-analysis_actions button {width:100% !important; max-width:none !important}
.st-key-analysis_actions [data-testid="stElementContainer"] {flex:0 1 auto; min-width:180px; max-width:280px; margin-left:auto}
.st-key-analysis_actions .st-key-current_conditions {width:100% !important; min-width:180px; max-width:280px}
.st-key-analysis_actions .st-key-current_conditions button {width:100% !important; height:38px !important; max-width:none !important}
.st-key-run_analysis button[kind="primary"]:hover,
.st-key-run_analysis button[kind="primary"]:focus,
.st-key-run_analysis button[kind="primary"]:focus-visible,
.st-key-run_analysis button[kind="primary"]:active,
.st-key-run_analysis button[kind="primary"]:disabled,
.st-key-run_analysis [data-testid="stBaseButton-primary"]:hover,
.st-key-run_analysis [data-testid="stBaseButton-primary"]:focus,
.st-key-run_analysis [data-testid="stBaseButton-primary"]:focus-visible,
.st-key-run_analysis [data-testid="stBaseButton-primary"]:active,
.st-key-run_analysis [data-testid="stBaseButton-primary"]:disabled {
  background-color:#7c2d12 !important; border-color:#7c2d12 !important; color:#fff !important; opacity:1 !important
}
.st-key-refresh_data button {height:38px !important}
.st-key-refresh_data button p {white-space:nowrap; font-size:12px !important}
.st-key-run_analysis button {height:38px !important}
.st-key-refresh_data button, .st-key-run_analysis button {display:flex; align-items:center; justify-content:center}
.st-key-refresh_data button p {font-weight:500; line-height:1.3}
.st-key-run_analysis button p {font-size:15px !important; font-weight:700; line-height:1.3}
div[data-testid="stProgress"] div[role="progressbar"] {height:16px !important; min-height:16px !important}
div[data-testid="stProgress"] div[role="progressbar"] > div {height:100% !important}
.work-time-direction {color:#242424; font-size:.88rem; font-weight:600; white-space:nowrap}
.st-key-source_options [role="radiogroup"] {gap:.35rem .8rem}
.st-key-source_options label {font-size:.82rem}
.st-key-additional_settings_row [data-testid="stHorizontalBlock"] {align-items:flex-end}
@media (max-width:1300px) {
  .st-key-filter_row [data-testid="stHorizontalBlock"] {flex-wrap:wrap}
  .st-key-condition_row {flex-wrap:wrap}
}
@media (max-width:800px) {
  .st-key-filter_row [data-testid="stHorizontalBlock"] {flex-direction:column}
  .st-key-condition_row {flex-direction:column; align-items:flex-start}
  .st-key-condition_row [data-testid="stLayoutWrapper"]:has(.st-key-analysis_actions) {margin-left:0 !important}
  .st-key-analysis_actions {margin-left:0 !important}
  .st-key-additional_settings_row [data-testid="stHorizontalBlock"] {flex-wrap:wrap}
  .st-key-analysis_actions {flex-direction:column !important}
}
.st-key-summary_metrics [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .st-key-summary_am) {align-items:stretch}
.st-key-summary_metrics [data-testid="stColumn"]:has(.st-key-summary_am),
.st-key-summary_metrics [data-testid="stColumn"]:has(.st-key-summary_pm),
.st-key-summary_metrics [data-testid="stColumn"]:has(.st-key-summary_flights) {box-sizing:border-box; align-self:stretch; padding:12px 14px 10px; border:1px solid #ded8d3; border-radius:10px}
.summary-date-label {color:#68625e; font-size:13px; font-weight:400; white-space:nowrap}
.summary-dates {display:flex; align-items:flex-start; gap:5px; margin:0; padding-top:6px; color:#242424; font-size:13px; font-weight:400; line-height:1.3}
.summary-month-row {display:flex; align-items:flex-start; gap:6px}
.summary-month {color:#68625e; font-size:12px; font-weight:400; white-space:nowrap}
.summary-day {white-space:nowrap}
.summary-weekday {font-size:12px; font-weight:400; color:#68625e}
.st-key-work_times [data-testid="stCaptionContainer"] p {color:#68625e; font-size:.75rem; line-height:1.3; margin:0}
</style>''', unsafe_allow_html=True)

if 'initial' not in st.session_state:
    initial, error = decode(dict(st.query_params), datetime.now(KST).date())
    st.session_state.initial = initial
    st.session_state.url_error = error
initial = st.session_state.initial
if 'codes' not in st.session_state:
    st.session_state.codes = ', '.join(initial.airlines)
contract = load_contract()

st.html('''<header class="app-header">
<div class="app-header-eyebrow">RAMP HANDLING / RESOURCE PLANNING</div>
<div class="app-header-title"><h1>시간대별 램프조업 수요 분석</h1></div>
</header>''')
if st.session_state.get('url_error'):
    st.warning(st.session_state.url_error)
if not contract.verified:
    st.warning('UBIKAIS 데이터 계약 검증 중입니다. 실자료 조회는 잠정 분석으로 표시되며 정식 보고서 출력은 제한됩니다.')

def airport_changed():
    st.session_state.codes = ', '.join(airport_airlines(st.session_state.airport))


def inline_label(label):
    st.html(f'<span class="inline-field-label">{label}</span>', width='content')


def describe_offset(reference, minutes):
    if minutes < 0:
        return f'{reference} {abs(minutes)}분 전'
    if minutes > 0:
        return f'{reference} {minutes}분 후'
    return f'{reference} 시각'


settings_panel = st.container(border=True, key='analysis_settings')
with settings_panel:
    with st.container(key='filter_row', horizontal=True, vertical_alignment='top', gap='medium'):
        with st.container(key='target_group', width='content'):
            with st.container(horizontal=True, vertical_alignment='top', gap='small'):
                with st.container(width='content'):
                    inline_label('공항')
                    airport = st.selectbox('공항', list(AIRPORTS), index=list(AIRPORTS).index(initial.airport),
                                           format_func=lambda x: f'{AIRPORTS[x][0]} · {AIRPORTS[x][1] or x}',
                                           key='airport', width='stretch', on_change=airport_changed,
                                           label_visibility='collapsed')
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
                with st.container(width='content'):
                    inline_label('항공사 코드')
                    codes = st.text_input('항공사 코드 (ICAO 3자리)', value=None, placeholder='예시: JJA',
                                          key='codes', width='stretch', help='\n\n'.join(code_help),
                                          label_visibility='collapsed')
        with st.container(key='period_group', horizontal=True, vertical_alignment='top', gap='small', width='content'):
            with st.container(width='content'):
                inline_label('기간 선택')
                mode = st.radio('기간 선택', ['month', 'custom'], index=0 if initial.mode == 'month' else 1,
                                format_func=lambda x: '월별' if x == 'month' else '사용자 지정',
                                horizontal=True, key='mode', label_visibility='collapsed', width='content')
            if mode == 'month':
                with st.container(horizontal=True, vertical_alignment='top', width='content', gap='small'):
                    with st.container(width=90):
                        inline_label('연도')
                        year = st.number_input('연도', min_value=2000, max_value=2100, value=initial.start.year,
                                               step=1, key='year', label_visibility='collapsed', width='stretch')
                    with st.container(width=80):
                        inline_label('월')
                        month = st.selectbox('월', list(range(1, 13)), index=initial.start.month-1,
                                             key='month', label_visibility='collapsed', width='stretch')
                start = date(year, month, 1)
                end = date(year, month, calendar.monthrange(year, month)[1])
            else:
                with st.container(width='stretch'):
                    inline_label('조회 날짜')
                    dates = st.date_input('시작일 ~ 종료일 (최대 31일)', value=(initial.start, initial.end),
                                          format='YYYY-MM-DD', key='dates', width='stretch',
                                          label_visibility='collapsed')
                    start, end = (dates[0], dates[-1]) if len(dates) == 2 else (None, None)
        with st.container(key='basis_group', horizontal=True, vertical_alignment='top', gap='medium', width='content'):
            with st.container(width='content'):
                inline_label('분석 간격')
                interval = st.radio('분석 간격', [60, 30], index=0 if initial.interval == 60 else 1,
                                    format_func=lambda x: f'{x}분', horizontal=True, key='interval',
                                    label_visibility='collapsed', width='content')
            with st.container(width='content'):
                inline_label('분석 기준')
                basis = st.radio('분석 기준시각', ['scheduled', 'actual'],
                                 index=0 if initial.basis == 'scheduled' else 1,
                                 format_func=lambda x: 'STA/STD' if x == 'scheduled' else 'RAMP IN/OUT',
                                 horizontal=True, key='basis', label_visibility='collapsed',
                                 help='RAMP IN/OUT 시각이 없으면 STA/STD 시각을 사용합니다.', width='content')
            quick_turn_available = (
                basis == 'actual'
                and st.session_state.get('dep_included', 'dep' in initial.directions)
                and st.session_state.get('arr_included', 'arr' in initial.directions)
            )
            requested_turn = st.session_state.get('quick_turn', initial.quick_turn)
            requested_limit = st.session_state.get('turn_limit', initial.turn_limit)
            with st.container(width='content'):
                inline_label('퀵턴')
                turn_menu = st.popover(f'{requested_limit}분' if requested_turn and quick_turn_available else '미적용',
                                       disabled=not quick_turn_available, key='turn_settings',
                                       help='RAMP IN/OUT 기준에서 출발·도착을 모두 사용할 때 적용합니다.')
                with turn_menu:
                    quick_turn = st.checkbox('퀵턴 반영', value=initial.quick_turn, key='quick_turn',
                                             disabled=not quick_turn_available)
                    turn_limit = st.number_input('제한시간 (분)', min_value=1, max_value=360,
                                                 value=initial.turn_limit, step=1, key='turn_limit',
                                                 disabled=not quick_turn or not quick_turn_available)
                    if quick_turn:
                        st.caption(f'조건: RAMP IN ~ RAMP OUT {turn_limit}분 이내 · REG·SPOT 일치')
                        st.caption('적용 계산: 대기시간 포함 연속 점유 · 출발편 이동시간만 적용')
    offsets = []
    directions = []
    with st.container(key='condition_row', horizontal=True, vertical_alignment='center', gap='small'):
        for name, prefix, value in zip(['출발', '도착'], ['dep', 'arr'], [initial.dep, initial.arr]):
            with st.container(key=f'{prefix}_group', width='content'):
                with st.container(horizontal=True, vertical_alignment='top', gap='small'):
                    with st.container(width='content', key=f'{prefix}_direction_toggle'):
                        st.html(f'<span class="inline-direction-label">{name}편</span>', width='content')
                        included = st.checkbox('사용', value=prefix in initial.directions,
                                               key=f'{prefix}_included')
                    vals = []
                    reference_label = ('STD' if prefix == 'dep' else 'STA') if basis == 'scheduled' else ('RAMP OUT' if prefix == 'dep' else 'RAMP IN')
                    for label, key, v in zip(['조업 시작', '조업 종료'], ['start', 'end'], [value.start, value.end]):
                        with st.container(width=125):
                            inline_label(f'{label} (분)')
                            minutes = st.number_input(f'{name}편 {label}', min_value=-10080, max_value=10080,
                                                      value=v, step=1, key=f'{prefix}_{key}', label_visibility='collapsed',
                                                      disabled=not included, help=f'{reference_label} 대비 조업 {label} 시각(분)입니다.',
                                                      width='stretch')
                        vals.append(minutes)
                    with st.container(width=125):
                        inline_label('이동소요 (분)')
                        travel = st.number_input(f'{name}편 이동소요 시간 (분)', min_value=0, max_value=20160,
                                                 value=value.reusable-value.end, step=1, key=f'{prefix}_travel',
                                                 label_visibility='collapsed', disabled=not included,
                                                 help='조업 종료 후 다음 작업에 투입되기까지 필요한 시간입니다.',
                                                 width='stretch')
                if included:
                    directions.append(prefix)
                offsets.append(Offsets(vals[0], vals[1], vals[1]+travel))
        actions = st.container(key='analysis_actions', width='content')

with st.expander('추가 설정', expanded=False):
    with st.container(key='additional_panel'):
        with st.container(key='additional_settings_row', horizontal=True,
                          vertical_alignment='bottom', gap='small'):
            with st.container(width=150):
                inline_label('조업 개시 시간')
                day_starts = sorted(set(range(0, 1440, 30)) | {initial.day_start})
                ds = st.selectbox('조업 개시 시간', day_starts, index=day_starts.index(initial.day_start),
                                  format_func=lambda v: f'{v//60:02d}:{v%60:02d}', key='day_start', width='stretch',
                                  label_visibility='collapsed',
                                  help='한국시간 기준, 선택한 시각부터 24시간을 하루로 집계합니다. 예: 06:00부터 다음 날 06:00까지. 기존 URL의 분 단위 값은 그대로 복원합니다.')
            with st.container(width=220):
                refresh_slot = st.empty()

        st.divider()
        st.markdown('**운항편 자료 가져오기**')
        source_mode = st.radio('자료 수집 방식', ['site', 'site_excel', 'excel'],
                               format_func=lambda x: {'site': '외부 사이트 조회',
                                                      'site_excel': '외부 조회 + 엑셀 추가',
                                                      'excel': '엑셀만 사용'}[x],
                               horizontal=True, key='collection_mode')
        source_ready = source_mode == 'site'
        if source_ready:
            st.caption('현재는 외부 사이트 조회를 사용합니다.')
        else:
            st.info('선택한 자료 수집 방식은 아직 구현되지 않았습니다.')

settings = None
invalid_offsets = []
for direction, name, value in zip(('dep', 'arr'), ('출발편', '도착편'), offsets):
    if direction not in directions:
        continue
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
    settings = Settings(airport, start, end, mode, airlines, basis, ds, interval, *offsets,
                        directions=tuple(directions), quick_turn=quick_turn, turn_limit=turn_limit)
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
refresh = refresh_slot.button('운항편 재조회 및 분석', key='refresh_data', width='stretch',
                               disabled=not settings or busy or not source_ready,
                               help='캐시를 사용하지 않고 현재 입력 조건의 운항자료를 다시 수집해 분석합니다.')
with actions:
    with st.popover('분석조건 보기', type='secondary', width='stretch', key='current_conditions'):
        airport_name, airport_iata = AIRPORTS[airport]
        airlines_text = codes.strip() or '미입력'
        if start is None or end is None:
            period_text = '날짜 미완성'
        elif mode == 'month':
            period_text = start.strftime('%Y년 %m월')
        else:
            period_text = f'{start:%Y-%m-%d} ~ {end:%Y-%m-%d}'
        basis_text = 'STA/STD' if basis == 'scheduled' else 'RAMP IN/OUT'
        condition_lines = [
            '**조회·분석 조건**',
            f'- **공항:** {airport_name} · {airport_iata or airport} ({airport})',
            f'- **항공사:** {airlines_text}',
            f'- **기간:** {period_text}',
            f'- **기준:** {basis_text}',
            f'- **간격:** {interval}분',
        ]
        direction_lines = []
        for name, prefix, value in zip(['출발', '도착'], ['dep', 'arr'], [initial.dep, initial.arr]):
            if not st.session_state.get(f'{prefix}_included', prefix in initial.directions):
                continue
            start_minutes = int(st.session_state.get(f'{prefix}_start', value.start))
            end_minutes = int(st.session_state.get(f'{prefix}_end', value.end))
            travel_minutes = int(st.session_state.get(f'{prefix}_travel', value.reusable-value.end))
            reference = ('STD' if prefix == 'dep' else 'STA') if basis == 'scheduled' else ('RAMP OUT' if prefix == 'dep' else 'RAMP IN')
            start_desc = describe_offset(reference, start_minutes).removeprefix(f'{reference} ')
            end_desc = describe_offset(reference, end_minutes).removeprefix(f'{reference} ')
            direction_lines.append(
                f'- **{name}편:** {reference} {start_desc} ~ {end_desc} · 이동 {travel_minutes}분')
        if direction_lines:
            condition_lines.extend(['', '**조업 조건**', *direction_lines])
        day_start_value = int(st.session_state.get('day_start', initial.day_start))
        day_start_text = f'{day_start_value // 60:02d}:{day_start_value % 60:02d}'
        quick_turn_value = bool(st.session_state.get('quick_turn', initial.quick_turn))
        turn_limit_value = int(st.session_state.get('turn_limit', initial.turn_limit))
        can_apply_turn = basis == 'actual' and all(
            st.session_state.get(f'{prefix}_included', prefix in initial.directions)
            for prefix in ('dep', 'arr'))
        if quick_turn_value and can_apply_turn:
            turn_text = f'적용 · {turn_limit_value}분 이내'
        elif quick_turn_value:
            turn_text = '선택됨 · 현재 기준/방향에서 비활성'
        else:
            turn_text = '미적용'
        collection_label = {
            'site': '외부 사이트 조회',
            'site_excel': '외부 조회 + 엑셀 추가',
            'excel': '엑셀만 사용',
        }.get(st.session_state.get('collection_mode', 'site'), '외부 사이트 조회')
        condition_lines.extend([
            '',
            '**추가 설정**',
            f'- **조업 개시:** {day_start_text}',
            f'- **퀵턴:** {turn_text}',
            f'- **자료 수집:** {collection_label}',
        ])
        st.markdown('\n'.join(condition_lines))
    run = st.button('분석 실행', key='run_analysis', type='primary', width='stretch', disabled=not settings or busy or not source_ready,
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
    display_help()
    st.stop()

applied = result.settings
def direction_count(direction, value):
    return str(value) if direction in applied.directions else '—'
dirty = settings is None or settings.signature != applied.signature
if (not dirty and 'job' not in st.session_state and not st.session_state.get('job_error')
        and st.session_state.get('completed_result_id') == result.result_id
        and st.session_state.get('completion_toast_result_id') != result.result_id):
    st.toast('분석이 완료되었습니다.', icon='✅')
    st.session_state.completion_toast_result_id = result.result_id
if dirty:
    st.info('입력 조건이 변경되었습니다. 아래는 이전 조회 결과입니다. 새 조건을 적용하려면 분석 실행을 누르세요.')
name, iata = AIRPORTS[applied.airport]
if applied.directions != ('dep', 'arr'):
    st.caption(f'분석 대상: {applied.direction_label}')
if result.synthetic:
    st.warning('개발 검증용 가상 데이터입니다. 실제 운항자료가 아닙니다.')
for blocker in result.blockers:
    st.warning(blocker)
with st.container(key='summary_metrics'):
    metrics = st.columns(3, gap='medium')
    for col, label, key, (maximum, dates) in zip(metrics[:2], ['오전 최대 수요', '오후 최대 수요'], ['summary_am', 'summary_pm'], half_day_peaks(result)):
        with col, st.container(border=False, key=key):
            metric_col, dates_col = st.columns([1.2, 1], gap='small', vertical_alignment='top')
            metric_col.metric(label, f'{maximum}개 조', help='한국시간 기준 오전 00:00부터 12:00 미만, 오후 12:00부터 다음 날 00:00 미만입니다. 분석 범위에 포함된 구간만 집계합니다.')
            dates_col.html(occurrence_dates(dates))
    with metrics[2], st.container(border=False, key='summary_flights'):
        st.metric('출발 / 도착 편수', f'{direction_count("dep", sum(c.dep_count for c in result.cells))} / {direction_count("arr", sum(c.arr_count for c in result.cells))}')
left, right = st.columns([2.2, 1], gap='large')
with left:
    title_col, download_col = st.columns([1.1, 1], vertical_alignment='center')
    title_col.subheader('시간대별 조업조 수요')
    from reports.render import lazy_download, output_stem
    saved_exports = st.session_state.get('export_cache')
    if saved_exports is None or saved_exports[0] != result.result_id or len(saved_exports) < 3 or saved_exports[2] != 'unified-a4-v15':
        saved_exports = (result.result_id, {}, 'unified-a4-v15')
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
    if applied.quick_turn_active:
        st.write(f'분석 범위 관련 퀵턴 연결 {diag.quick_turn_pairs}건 · 개별 조업 {diag.quick_turn_unpaired}건')
    for message in diag.messages:
        st.write(message)
    st.caption(f'자료 수집: {result.collected_from:%Y-%m-%d %H:%M:%S} ~ {result.collected_until:%Y-%m-%d %H:%M:%S} KST')
    st.caption(f'자료 버전 {result.data_version or "가상 자료"} · 정규화 v2 / 계산 엔진 v2')
    hist = result.histogram_minutes
    st.dataframe(pd.DataFrame([{'필요 조업조': k, '정확히 해당 조 수 (분)': v,
                               '해당 조 수 이상 (분)': sum(t for j,t in hist.items() if j >= k)} for k,v in hist.items()]), hide_index=True)
    st.caption(f'기간 총 점유량: {sum(result.daily_crew_minutes)/60:.1f} 조·시간. 0조 수요 시간도 포함합니다.')

display_help()
