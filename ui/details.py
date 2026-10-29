import pandas as pd
import streamlit as st

from engine.demand import cell_flights
from config.airport_codes import icao_to_iata
from config.airline_codes import flight_label


def fmt(value):
    return value.strftime('%H:%M') if value else '—'


def frame(flights):
    return pd.DataFrame([{
        '방향': '출발' if f.direction == 'dep' else '도착', '편명': flight_label(f.flight_id),
        '출도착지': icao_to_iata(f.route),
        'STA/STD': f.scheduled.strftime('%H:%M') if f.scheduled else '—',
        'RAMP I/O': f.actual.strftime('%H:%M') if f.actual else '—',
        '조업 시작': fmt(f.start), '조업 종료': fmt(f.end),
        '후속 조업 가능': fmt(f.reusable),
    } for f in flights])


def display(result, index):
    with st.container(key='cell_details'):
        _display(result, index)


def _display(result, index):
    cell = result.cells[index]
    end_label = cell.end.strftime('%H:%M' if cell.end.date() == cell.start.date() else '%m/%d %H:%M')
    st.html(f'''<style>
.st-key-cell_details [data-testid="stVerticalBlock"] {{gap:.5rem}}
.detail-summary {{display:grid; grid-template-columns:minmax(0,1fr) auto; gap:4px 16px; margin:0 0 8px; color:#242424}}
.detail-summary-label {{font-size:14px; line-height:1.5; color:#59514c}}
.detail-summary-value {{font-size:clamp(20px,1.6vw,26px); font-weight:700; line-height:1.35; overflow-wrap:anywhere}}
.detail-summary-right {{text-align:right}}
.detail-summary-demand {{color:#c2410c; white-space:nowrap}}
</style>
<div class="detail-summary">
<div class="detail-summary-label">{cell.start:%m/%d}</div>
<div class="detail-summary-label detail-summary-right">필요 조 개수</div>
<div class="detail-summary-value">{cell.start:%H:%M}–{end_label}</div>
<div class="detail-summary-value detail-summary-right detail-summary-demand">{cell.maximum}개 조</div>
</div>''')
    peak_label = cell.peak.strftime('%H:%M') if cell.peak else '없음'
    st.write(f'피크 시간 **{peak_label}** · 출발편 **{cell.dep_active}개 조** / 도착편 **{cell.arr_active}개 조**')
    work_flights = cell_flights(result, index, 'work')
    dep_count = sum(f.direction == 'dep' for f in work_flights)
    arr_count = sum(f.direction == 'arr' for f in work_flights)
    st.caption(f'해당 시간대 조업 편수 · 출발 {dep_count}편 / 도착 {arr_count}편',
               help='조업 시작부터 종료 직전까지가 선택한 시간대와 겹치는 편수입니다. 이동시간은 제외합니다. 한 편이 여러 시간대에 포함될 수 있으며, 필요 조 개수에는 이동시간도 포함됩니다.')
    interval_label = '1시간 기준' if result.settings.interval == 60 else '30분 기준'
    tabs = st.tabs(['피크 시간 기준', interval_label])
    for tab, kind in zip(tabs, ['peak', 'work']):
        with tab:
            flights = cell_flights(result, index, kind)
            if flights:
                st.dataframe(frame(flights), hide_index=True, width='stretch', height=350)
            else:
                st.info('해당 운항편이 없습니다.')
    if len(cell.peak_intervals) > 1:
        with st.expander('동률 피크 구간'):
            for a, b in cell.peak_intervals:
                st.write(f'{a:%m-%d %H:%M} ~ {b:%m-%d %H:%M}')
