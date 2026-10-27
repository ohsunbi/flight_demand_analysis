import pandas as pd
import streamlit as st

from engine.demand import cell_flights


def fmt(value):
    return value.strftime('%m-%d %H:%M') if value else '—'


def frame(flights):
    return pd.DataFrame([{
        '방향': '출발' if f.direction == 'dep' else '도착', '편명': f.flight_id,
        '조회 항공사': ', '.join(f.query_airlines) or '전체',
        '상대 공항': f.route, '예정': fmt(f.scheduled), '실제 주기장': fmt(f.actual),
        '주기장 원본 시각': f.actual_clock,
        '선택 기준': fmt(f.reference), '사용 시각': {'actual':'실제', 'actual_inferred':'실제·날짜 추정', 'fallback':'예정 대체', 'scheduled':'예정'}[f.reference_source],
        '조업 시작': fmt(f.start), '조업 종료': fmt(f.end), '재투입': fmt(f.reusable),
        '주의': ' · '.join(f.warnings),
    } for f in flights])


def display(result, index):
    cell = result.cells[index]
    st.subheader('시간대 상세')
    st.caption(f'운영일 {cell.operating_day} · {cell.start:%m-%d %H:%M} ~ {cell.end:%m-%d %H:%M}')
    st.metric('최대 필요 조업조', f'{cell.maximum}개 조')
    st.write(f'대표 피크 **{fmt(cell.peak)}** · 출발 **{cell.dep_active}** / 도착 **{cell.arr_active}**')
    st.caption(f'기준시각에 따른 편수: 출발 {cell.dep_count}편 · 도착 {cell.arr_count}편')
    tabs = st.tabs(['피크 점유', '점유 겹침', '기준시각'])
    for tab, kind in zip(tabs, ['peak', 'overlap', 'reference']):
        with tab:
            flights = cell_flights(result, index, kind)
            st.caption(f'{len(flights)}편 · 목록을 가로로 스크롤하면 조업시각을 확인할 수 있습니다.')
            if flights:
                st.dataframe(frame(flights), hide_index=True, width='stretch', height=350)
            else:
                st.info('해당 운항편이 없습니다.')
    if len(cell.peak_intervals) > 1:
        with st.expander('동률 피크 구간'):
            for a, b in cell.peak_intervals:
                st.write(f'{a:%m-%d %H:%M} ~ {b:%m-%d %H:%M}')
