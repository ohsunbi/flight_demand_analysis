"""Report-only rendering from one immutable analysis snapshot."""
from __future__ import annotations

import io
import textwrap
import threading
from datetime import datetime

import matplotlib
matplotlib.use('Agg')
import matplotlib.colors as colors
import matplotlib.font_manager as fm
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.patches import Patch
import numpy as np

from config import AIRPORTS, PALETTE, ROOT, color_index, legend_ranges
from domain.models import KST

RENDER_LOCK = threading.RLock()
FONT = ROOT / 'assets' / 'fonts' / 'NanumGothic-Regular.ttf'
ROWS_PER_PAGE = 18
_FONT_PROPERTIES = None


def _font():
    global _FONT_PROPERTIES
    if not FONT.is_file():
        raise RuntimeError('배포 한글 글꼴이 없습니다. 보고서 생성을 중단했습니다.')
    if _FONT_PROPERTIES is None:
        fm.fontManager.addfont(str(FONT))
        _FONT_PROPERTIES = fm.FontProperties(fname=str(FONT))
    return _FONT_PROPERTIES.copy()


def _legend(maximum):
    return [Patch(facecolor=color, edgecolor='#dce5ea', label=label) for color,label in legend_ranges(maximum)]


def _figure(result, row_start, row_end, col_start, col_end, *, png=False, page=1, pages=1, generated_at=None):
    fp = _font()
    s = result.settings
    n = 1440 // s.interval
    rows = row_end - row_start
    columns = col_end - col_start
    width = (24 if n == 48 else 16) if png else 11.69
    height = max(8.0, 4.5 + rows * .29) if png else 8.27
    fig = Figure(figsize=(width, height), facecolor='white')
    title = 'Flight Crew Demand Analysis'
    if result.synthetic:
        title += ' | 가상 데이터'
    fig.text(.055, .94, title, fontproperties=fp, fontsize=18 if png else 16, color='#123e4c', weight='bold')
    airport, iata = AIRPORTS[s.airport]
    basis = '예정 STD/STA' if s.basis == 'scheduled' else '실제 주기장 우선 (없으면 예정 대체)'
    airlines = '전체 항공사' if not s.airlines else ', '.join(s.airlines)
    # Airline code list has a fixed input bound and is wrapped separately from other metadata.
    meta = f'{airport} {s.airport}/{iata or "-"}  |  {s.start} ~ {s.end}  |  {basis}'
    fig.text(.055, .895, meta, fontproperties=fp, fontsize=10 if png else 9)
    for i, line in enumerate(textwrap.wrap('항공사: ' + airlines, width=130 if png else 112)):
        fig.text(.055, .863 - i*.022, line, fontproperties=fp, fontsize=9 if png else 8)
    offset = (f'운영일 시작 {s.day_start//60:02d}:{s.day_start%60:02d} KST  |  '
              f'출발 시작/종료/재투입 {s.dep.start:+d}/{s.dep.end:+d}/{s.dep.reusable:+d}분  |  '
              f'도착 {s.arr.start:+d}/{s.arr.end:+d}/{s.arr.reusable:+d}분')
    fig.text(.055, .802, offset, fontproperties=fp, fontsize=9 if png else 8)
    fig.text(.055, .773, '조업 종료 후 재투입 대기시간도 점유에 포함합니다. 시간 열은 각 셀의 시작시각입니다.', fontproperties=fp, fontsize=9 if png else 8)
    peak = result.peak_cell
    summary = f'기간 최대 {result.maximum}개 조  |  일별 최대 평균 {sum(result.daily_max)/len(result.daily_max):.1f}개 조'
    if peak:
        summary += f'  |  대표 피크 {peak.peak:%m-%d %H:%M} (출발 {peak.dep_active} / 도착 {peak.arr_active})'
    fig.text(.055, .738, summary, fontproperties=fp, fontsize=10 if png else 9, color='#17636e')
    counts = f'기간 출발 {sum(c.dep_count for c in result.cells)}편 / 도착 {sum(c.arr_count for c in result.cells)}편'
    if s.basis == 'actual':
        counts += f'  |  실제 사용 {result.diagnostics.actual_used}편 (날짜 추정 {result.diagnostics.actual_date_inferred}편) / 예정 대체 {result.diagnostics.scheduled_used}편'
    fig.text(.055, .71, counts, fontproperties=fp, fontsize=9 if png else 8)
    if result.diagnostics.actual_date_inferred:
        fig.text(.055, .681, '실제 날짜 추정: 예정시각에 가장 가까운 날짜를 사용합니다. 하루 이상 지연은 날짜가 부정확할 수 있습니다.', fontproperties=fp, fontsize=8, color='#965318')

    table_height = .43 if png else .43 * min(1, rows / ROWS_PER_PAGE)
    table_bottom = .61 - table_height
    ax = fig.add_axes([.09, table_bottom, .80, table_height])
    cells = [[result.cells[r*n+c] for c in range(col_start, col_end)] for r in range(row_start,row_end)]
    values = [[c.maximum for c in row] for row in cells]
    image = np.array([[colors.to_rgba(PALETTE[color_index(v,result.maximum)]) for v in row] for row in values])
    ax.imshow(image, aspect='auto', interpolation='nearest')
    labels = [f'{c.start:%H:%M}' + ('+1' if c.start.date() > c.operating_day else '') for c in cells[0]]
    ax.set_xticks(range(columns), labels, fontsize=8 if png else 6.6, fontproperties=fp)
    ax.xaxis.tick_top()
    for label in ax.get_xticklabels():
        label.set_rotation(45)
        label.set_ha('left')
        label.set_rotation_mode('anchor')
    ax.tick_params(axis='both', length=0, pad=6)
    ax.set_yticks(range(rows), [str(row[0].operating_day) for row in cells], fontsize=9 if png else 8, fontproperties=fp)
    for r, row in enumerate(values):
        for c, value in enumerate(row):
            ax.text(c, r, str(value), ha='center', va='center', fontproperties=fp,
                    fontsize=10 if png else 8, color='white' if color_index(value,result.maximum)>=4 else '#123e4c')
        ax.text(columns + .1, r, str(result.daily_max[row_start+r]), ha='left', va='center', fontproperties=fp, fontsize=10 if png else 8, color='#123e4c')
    ax.text(columns + .1, -.85, '일 최대', fontproperties=fp, fontsize=9 if png else 7)
    ax.set_xticks(np.arange(-.5, columns, 1), minor=True)
    ax.set_yticks(np.arange(-.5, rows, 1), minor=True)
    ax.grid(which='minor', color='white', linewidth=1.2)
    ax.tick_params(which='minor', length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    legends = _legend(result.maximum)
    fig.legend(handles=legends, loc='lower left', bbox_to_anchor=(.08,max(.105,table_bottom-.075)), ncol=7,
               prop=fm.FontProperties(fname=str(FONT), size=9 if png else 8), frameon=False,
               title='최대 동시 필요 조업조 수 (개 조)', title_fontproperties=fm.FontProperties(fname=str(FONT), size=9))
    first = cells[0][0]; last = cells[-1][-1]
    def clock_label(dt):
        return dt.strftime('%H:%M') + ('(+1일)' if dt.date() > first.operating_day else '')
    fig.text(.055, .078, f'표시 운영일 {first.operating_day} ~ {last.operating_day}  |  운영일 내 시간 {clock_label(first.start)} ~ {clock_label(cells[0][-1].end)}  |  {page}/{pages}', fontproperties=fp, fontsize=8)
    fig.text(.055, .052, f'수집 기준 {result.collected_from:%Y-%m-%d %H:%M} ~ {result.collected_until:%Y-%m-%d %H:%M} KST', fontproperties=fp, fontsize=8)
    fig.text(.055, .028, f'생성 {generated_at:%Y-%m-%d %H:%M} KST  |  결과 {result.result_id}  |  반복된 요약·일 최대는 합산하지 않습니다.', fontproperties=fp, fontsize=8)
    return fig


def build_downloads(result):
    if not result.exportable:
        raise ValueError('미확정 분석은 정식 보고서로 출력할 수 없습니다.')
    generated_at = datetime.now(KST)
    n = 1440 // result.settings.interval
    spans = [(r, min(result.settings.days,r+ROWS_PER_PAGE), c, min(n,c+24))
             for r in range(0,result.settings.days,ROWS_PER_PAGE) for c in range(0,n,24)]
    with RENDER_LOCK, matplotlib.rc_context({'pdf.fonttype':42, 'axes.unicode_minus':False}):
        png = io.BytesIO(); pdf = io.BytesIO()
        fig = None
        try:
            fig = _figure(result,0,result.settings.days,0,n,png=True,generated_at=generated_at)
            pixels = fig.get_size_inches()*180
            if pixels[0]*pixels[1] > 20_000_000:
                raise ValueError('PNG 안전 크기를 초과했습니다.')
            fig.savefig(png, format='png', dpi=180)
        finally:
            if fig is not None:
                fig.clear()
        with PdfPages(pdf, metadata={'Title':'Flight Crew Demand Analysis', 'Subject':result.result_id}) as pages:
            for i, (r0,r1,c0,c1) in enumerate(spans):
                fig = None
                try:
                    fig = _figure(result,r0,r1,c0,c1,page=i+1,pages=len(spans),generated_at=generated_at)
                    pages.savefig(fig)
                finally:
                    if fig is not None:
                        fig.clear()
    stem = f'crew_{result.settings.airport}_{result.settings.start}_{result.settings.end}_{result.result_id}'
    return dict(png=png.getvalue(), pdf=pdf.getvalue(), png_name=stem+'.png', png_mime='image/png', pdf_name=stem+'.pdf')
