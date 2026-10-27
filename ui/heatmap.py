import streamlit as st

from config import PALETTE, ROOT

_component = st.components.v2.component(
    'crew_demand_heatmap', html='<div class="heatmap" role="region" aria-label="조업조 수요 히트맵"></div>',
    css=(ROOT / 'ui' / 'heatmap.css').read_text(encoding='utf-8'),
    js=(ROOT / 'ui' / 'heatmap.js').read_text(encoding='utf-8'),
)


def display(result):
    n = 1440 // result.settings.interval
    first = result.cells[:n]
    headers = [f'{c.start:%H:%M}' + ('⁺¹' if c.start.date() > result.settings.start else '') for c in first]
    values = [[c.maximum for c in result.cells[i:i+n]] for i in range(0, len(result.cells), n)]
    selection = st.session_state.get('cell_selection', 0)
    data = dict(headers=headers, values=values,
                rows=[result.cells[i].operating_day.isoformat() for i in range(0, len(result.cells), n)],
                daily=result.daily_max, maximum=result.maximum, selected=selection, palette=PALETTE)
    event = _component(data=data, default={'selection': selection}, key='heatmap_' + result.result_id,
                       on_selection_change=lambda: None)
    selected = event.selection
    if type(selected) is int and 0 <= selected < len(result.cells):
        st.session_state.cell_selection = selected
    return st.session_state.get('cell_selection', 0)
