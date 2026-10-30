"""Unified PNG/PDF rendering from one immutable analysis snapshot."""
from __future__ import annotations

import io
import textwrap
import threading
from contextlib import nullcontext
from zipfile import ZipFile, ZIP_DEFLATED

import matplotlib
matplotlib.use('Agg')
import matplotlib.colors as colors
import matplotlib.font_manager as fm
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
import numpy as np

from config import AIRPORTS, PALETTE, PALETTE_TEXT, ROOT, color_index
from config.airline_codes import to_iata_codes
from engine.demand import half_day_peaks

RENDER_LOCK = threading.RLock()
FONT = ROOT / 'assets' / 'fonts' / 'NanumGothic-Regular.ttf'
_FONT_PROPERTIES = None


def _font():
    global _FONT_PROPERTIES
    if not FONT.is_file():
        raise RuntimeError('배포 한글 글꼴이 없습니다. 보고서 생성을 중단했습니다.')
    if _FONT_PROPERTIES is None:
        fm.fontManager.addfont(str(FONT))
        _FONT_PROPERTIES = fm.FontProperties(fname=str(FONT))
    return _FONT_PROPERTIES.copy()


def _figure(result, col_start, col_end):
    """A4 portrait, all operating dates, at most 24 time columns per page."""
    s = result.settings
    fp = _font()
    width, height = 210/25.4*72, 297/25.4*72
    fig = Figure(figsize=(width/72,height/72), facecolor='white')
    def text(x,y,value,*,size=9,color='#242424',weight='normal',ha='left',va='top'):
        return fig.text(x/width,1-y/height,value,fontproperties=fp,fontsize=size,color=color,weight=weight,ha=ha,va=va)
    def box(x,y,w,h,*,fill='#f7f5f3',edge='none'):
        fig.add_artist(Rectangle((x/width,1-(y+h)/height),w/width,h/height,
                                transform=fig.transFigure,facecolor=fill,edgecolor=edge,linewidth=.6))
    renderer = FigureCanvasAgg(fig).get_renderer()
    def inline(x, y, parts, available, size=8.5):
        """Fit a single row, preserving bold labels and measured spacing."""
        def part_width(value, bold, font_size):
            prop=fp.copy()
            prop.set_size(font_size)
            prop.set_weight('bold' if bold else 'normal')
            return renderer.get_text_width_height_descent(value,prop,False)[0]*72/fig.dpi
        total=sum(part_width(value,bold,size) for value,bold in parts)
        size=min(size,size*available/max(total,1))
        for value,bold in parts:
            text(x,y,value,size=size,weight='bold' if bold else 'normal',
                 color='#68625e' if bold else '#242424')
            x+=part_width(value,bold,size)
    margin=28
    airport,iata=AIRPORTS[s.airport]
    header_top=16/25.4*72  # 16 mm of top whitespace on A4.
    text(margin,header_top,'RAMP HANDLING / RESOURCE PLANNING',size=7.5,color='#68625e')
    text(width-margin,header_top,f'{s.start:%Y.%m.%d} ~ {s.end:%Y.%m.%d}',size=9,ha='right')
    airlines=', '.join(to_iata_codes(s.airlines)) if s.airlines else '전체 항공사'
    scope = f' | 분석 대상 : {s.direction_label}' if s.directions != ('dep', 'arr') else ''
    airline_lines=textwrap.wrap(f'{airport}{scope} | 항공사 : {airlines}',width=55)
    if s.quick_turn_active:
        airline_lines.append(f'퀵턴 {s.turn_limit}분 이내 | 대기 연속 점유 | 연결 시 출발편 이동시간 적용')
    for i,line in enumerate(airline_lines):
        text(width-margin,header_top+16+i*11,line,size=9,ha='right')
    title_y=max(header_top+36,header_top+16+len(airline_lines)*11+10)
    box(margin,title_y,4,23,fill='#f15922')
    text(margin+14,title_y,f'램프조업 수요 분석 ({iata or s.airport})',size=20,weight='bold')
    card_y,card_h=title_y+40,58
    if result.synthetic:
        text(width-margin,card_y-14,'가상 데이터',size=9,color='#c2410c',ha='right',weight='bold')
    card_w=(width-2*margin-20)/3
    for i,(label,(maximum,_)) in enumerate(zip(('오전 최대 수요','오후 최대 수요'),half_day_peaks(result))):
        x=margin+i*(card_w+10)
        box(x,card_y,card_w,card_h,edge='#ded8d3')
        text(x+12,card_y+9,label,size=9)
        text(x+card_w-12,card_y+card_h-10,f'{maximum}개 조',size=19,color='#c2410c',weight='bold',ha='right',va='bottom')
    x=margin+2*(card_w+10)
    box(x,card_y,card_w,card_h,edge='#ded8d3')
    text(x+12,card_y+9,'출발 / 도착 편수',size=9)
    dep=sum(c.dep_count for c in result.cells); arr=sum(c.arr_count for c in result.cells)
    dep_label = f'{dep:,}' if 'dep' in s.directions else '—'
    arr_label = f'{arr:,}' if 'arr' in s.directions else '—'
    text(x+card_w-12,card_y+card_h-10,f'{dep_label} / {arr_label}편',size=16,color='#c2410c',weight='bold',ha='right',va='bottom')
    basis='STD/STA' if s.basis=='scheduled' else 'Ramp OUT/IN'
    clock=f'{s.day_start//60:02d}:{s.day_start%60:02d}'
    conditions=[('출도착 시간 기준  ',True),(basis,False),
                ('    |    집계 간격  ',True),(f'{s.interval}분',False),
                ('    |    일일 분석 시간대  ',True),(f'{clock} ~ 다음 날 {clock}',False)]
    def offset_label(minutes):
        return '기준시각' if minutes==0 else f'{abs(minutes)}분 {"전" if minutes<0 else "후"}'
    n=1440//s.interval
    cells=[result.cells[r*n+col_start:r*n+col_end] for r in range(s.days)]
    first,last=cells[0][0],cells[0][-1]
    end_time='24:00' if last.end.hour==last.end.minute==0 else last.end.strftime('%H:%M')
    # Three compact rows share the summary cards' outer edges.
    condition_y = card_y + 68
    box(margin, condition_y, width-2*margin, 64, fill='#ffffff', edge='#ded8d3')
    box(margin, condition_y, 70, 64, edge='#ded8d3')
    text(margin+35, condition_y+32, '분석 조건', size=9, ha='center', va='center')
    content_x = margin+82
    content_width = width-margin-12-content_x
    inline(content_x, condition_y+10, conditions, content_width)
    for i,(name,value,reference) in enumerate((('출발편',s.dep,'STD' if s.basis=='scheduled' else 'Ramp OUT'),
                                             ('도착편',s.arr,'STA' if s.basis=='scheduled' else 'Ramp IN'))):
        row_y = condition_y+28+i*17
        if ('dep' if i == 0 else 'arr') not in s.directions:
            inline(content_x, row_y, [(name+'   분석 제외', True)], content_width)
            continue
        travel_label = f'{value.reusable-value.end}분 적용'
        if s.quick_turn_active and i == 1:
            travel_label = f'{value.reusable-value.end}분 (단독편)'
        inline(content_x, row_y, [(name+'   조업 시간  ',True),
               (f'{reference} {offset_label(value.start)} ~ {reference} {offset_label(value.end)}',False),
               ('  |  조업 후 이동시간  ',True),(travel_label,False)], content_width)
    # Keep page scope and actual-time fallback separate from the three condition rows.
    if s.interval==30:
        text(width-margin, condition_y+72, f'이 페이지 시간대  {first.start:%H:%M} ~ {end_time}',
             size=7.5, color='#68625e', ha='right')
    if s.basis=='actual':
        text(margin, condition_y+72, '실제시각이 없는 편은 STD/STA 적용 · 날짜 추정은 조기 3시간 허용', size=7.5, color='#68625e')
    table_top=card_y+(184 if s.interval==30 or s.basis=='actual' else 166)
    table_height=min(height-table_top-24,s.days*28)
    table_bottom = 1-(table_top+table_height)/height
    ax = fig.add_axes([.12, table_bottom, .72, table_height/height])
    values = [[c.maximum for c in row] for row in cells]
    ax.imshow([[colors.to_rgba(PALETTE[color_index(v, result.maximum)]) for v in row] for row in values],
              aspect='auto', interpolation='nearest')
    labels = []
    for c in cells[0]:
        label = c.start.strftime('%H')
        if s.interval == 30 or c.start.minute:
            label += '\n' + c.start.strftime('%M')
        labels.append(label)
    ax.set_xticks(range(col_end-col_start), labels, fontproperties=fp, fontsize=11)
    ax.xaxis.tick_top()
    weekdays = ('월', '화', '수', '목', '금', '토', '일')
    ax.set_yticks(range(s.days), [f'{row[0].operating_day:%m/%d} ({weekdays[row[0].operating_day.weekday()]})' for row in cells],
                  fontproperties=fp, fontsize=10)
    ax.tick_params(axis='both', length=0, pad=7)
    for r, row in enumerate(values):
        for c, value in enumerate(row):
            ax.text(c, r, str(value), ha='center', va='center', fontproperties=fp, fontsize=10,
                    color=PALETTE_TEXT[color_index(value, result.maximum)])
    ax.set_xticks(np.arange(-.5, col_end-col_start, 1), minor=True)
    ax.set_yticks(np.arange(-.5, s.days, 1), minor=True)
    ax.grid(which='minor', color='white', linewidth=1.3)
    ax.tick_params(which='minor', length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)

    # Full operating-day totals remain identical on both half-day export pages.
    daily_counts = [
        (sum(c.dep_count for c in result.cells[r*n:(r+1)*n]),
         sum(c.arr_count for c in result.cells[r*n:(r+1)*n]))
        for r in range(s.days)
    ]
    count_values = np.asarray(daily_counts, dtype=float)
    # Compare dates within each direction; constant columns stay at the light end.
    count_range = np.ptp(count_values, axis=0)
    count_levels = np.divide(count_values-count_values.min(axis=0), count_range,
                             out=np.zeros_like(count_values), where=count_range > 0)
    counts_ax = fig.add_axes([.85, table_bottom, .10, table_height/height])
    counts_ax.imshow(count_levels,
                     cmap=colors.LinearSegmentedColormap.from_list('flight_counts', ['#fafafa', '#c6c6c6']),
                     vmin=0, vmax=1,
                     aspect='auto', interpolation='nearest')
    # Match the hour row, including the blank minute row on split-page reports.
    count_labels = [name + ('\n' if '\n' in labels[0] else '') for name in ('출발', '도착')]
    counts_ax.set_xticks([0, 1], count_labels, fontproperties=fp, fontsize=11)
    counts_ax.xaxis.tick_top()
    counts_ax.set_yticks([])
    counts_ax.tick_params(axis='both', length=0, pad=7)
    for r, counts in enumerate(daily_counts):
        for c, value in enumerate(counts):
            label = str(value) if ('dep' if c == 0 else 'arr') in s.directions else '—'
            counts_ax.text(c, r, label, ha='center', va='center',
                           fontproperties=fp, fontsize=9, color='#242424')
    counts_ax.set_xticks([-.5, .5, 1.5], minor=True)
    counts_ax.set_yticks(np.arange(-.5, s.days, 1), minor=True)
    counts_ax.grid(which='minor', color='white', linewidth=1.3)
    counts_ax.tick_params(which='minor', length=0)
    for spine in counts_ax.spines.values():
        spine.set_visible(False)
    return fig


def build_export(result, kind):
    """Build only the requested file, without Streamlit or external I/O."""
    if not result.exportable:
        raise ValueError('미확정 분석은 출력할 수 없습니다.')
    if kind not in ('png', 'pdf'):
        raise ValueError('지원하지 않는 출력 형식입니다.')
    output = io.BytesIO()
    with RENDER_LOCK, matplotlib.rc_context({'pdf.fonttype':42, 'axes.unicode_minus':False}):
        n = 1440 // result.settings.interval
        spans = [(c,min(n,c+24)) for c in range(0,n,24)]
        with (ZipFile(output,'w',compression=ZIP_DEFLATED) if kind=='png' and len(spans)>1 else nullcontext(None)) as archive:
            with (PdfPages(output, metadata={'Title':'시간대별 조업조 수요'}) if kind=='pdf' else nullcontext(None)) as pages:
                for c0,c1 in spans:
                    fig = None
                    try:
                        fig = _figure(result,c0,c1)
                        if np.prod(fig.get_size_inches()*180) > 20_000_000:
                            raise ValueError('차트 안전 크기를 초과했습니다.')
                        if pages is not None:
                            pages.savefig(fig)
                        else:
                            target = io.BytesIO() if archive is not None else output
                            fig.savefig(target,format='png',dpi=180)
                            if archive is not None:
                                a,b=result.cells[c0].start,result.cells[c1-1].end
                                archive.writestr(f'{output_stem(result)}_{a:%H%M}-{b:%H%M}.png',target.getvalue())
                    finally:
                        if fig is not None:
                            fig.clear()
    return output.getvalue()


def lazy_download(result, kind, cache):
    """Capture a snapshot and session-local cache; callback runs off the UI thread."""
    def generate():
        with RENDER_LOCK:
            if kind not in cache:
                try:
                    cache[kind] = build_export(result, kind)
                except Exception:
                    raise RuntimeError('파일 생성에 실패했습니다. 잠시 후 다시 시도하세요.') from None
            return cache[kind]
    return generate


def output_stem(result):
    s = result.settings
    airport_code = AIRPORTS[s.airport][1] or s.airport
    return f'램프조업_수요분석_{airport_code}_{s.start:%y%m%d}_{s.end:%y%m%d}'


def build_downloads(result):
    zipped = result.settings.interval == 30
    return dict(png=build_export(result, 'png'), pdf=build_export(result, 'pdf'),
                png_name=output_stem(result)+('.zip' if zipped else '.png'),
                png_mime='application/zip' if zipped else 'image/png', pdf_name=output_stem(result)+'.pdf')
