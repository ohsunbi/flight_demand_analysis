from datetime import date
from io import BytesIO
from zipfile import ZipFile

import pytest
from PIL import Image
from pypdf import PdfReader

from domain.models import Settings
from tests.fixtures import demo_result
from reports.render import build_downloads


def test_report_contains_whole_day_and_period():
    r=demo_result(Settings('RKSI',date(2026,10,26),date(2026,10,26),mode='custom',interval=30))
    data=build_downloads(r)
    reader=PdfReader(BytesIO(data['pdf']))
    assert len(reader.pages)==2
    text='\n'.join(p.extract_text() for p in reader.pages)
    assert '00' in text and '23' in text and '30' in text and '2026.10.26' in text
    assert '가상 데이터' in text
    assert '10분 적용' in text and '오전 최대 수요' in text and '오후 최대 수요' in text
    assert '일별 최대 평균' not in text and '대표 피크' not in text
    with ZipFile(BytesIO(data['png'])) as archive:
        assert len(archive.namelist()) == 2
        assert all(Image.open(BytesIO(archive.read(name))).height > 2000 for name in archive.namelist())


def test_report_airlines_use_display_codes_without_changing_selected_codes():
    from reports.render import build_export
    settings = Settings('RKSI',date(2026,10,26),date(2026,10,26),mode='custom',
                        airlines=('FDX','JJA','TTW','XUM','ZZZ'))
    result = demo_result(settings)
    reader = PdfReader(BytesIO(build_export(result,'pdf')))
    assert '항공사 : 7C, FX, IT, XU, ZZZ' in reader.pages[0].extract_text()
    assert result.settings.airlines == ('FDX','JJA','TTW','XUM','ZZZ')
    assert all(f.flight_id[:3] in settings.airlines for f in result.flights)


def test_unconfirmed_result_cannot_export():
    r=demo_result(Settings('RKSI',date(2026,10,26),date(2026,10,26),mode='custom'))
    r.exportable=False
    with pytest.raises(ValueError):build_downloads(r)


def test_missing_font_fails_explicitly(monkeypatch,tmp_path):
    import reports.render as render
    r=demo_result(Settings('RKSI',date(2026,10,26),date(2026,10,26),mode='custom'))
    monkeypatch.setattr(render,'FONT',tmp_path/'missing.ttf')
    with pytest.raises(RuntimeError):render.build_downloads(r)


def test_repeated_downloads_do_not_accumulate_registered_fonts():
    import matplotlib.font_manager as fm
    from reports.render import FONT
    r=demo_result(Settings('RKSI',date(2026,10,26),date(2026,10,26),mode='custom'))
    build_downloads(r)
    count=lambda:sum(str(f.fname)==str(FONT) for f in fm.fontManager.ttflist)
    before=count()
    build_downloads(r)
    assert count()==before


@pytest.mark.parametrize('interval,report_pages', [(60,1),(30,2)])
def test_chart_and_report_exports_cover_full_month(interval,report_pages):
    from reports.render import build_export
    r=demo_result(Settings('RKSI',date(2026,10,1),date(2026,10,31),interval=interval))
    png_data=build_export(r,'png')
    if interval==30:
        with ZipFile(BytesIO(png_data)) as archive:
            assert len(archive.namelist())==2
            assert all(name.startswith('램프조업_수요분석_ICN_261001_261031_') for name in archive.namelist())
            assert '0000-1200' in archive.namelist()[0] and '1200-0000' in archive.namelist()[1]
            png_images=[Image.open(BytesIO(archive.read(name))) for name in archive.namelist()]
    else:
        png_images=[Image.open(BytesIO(png_data))]
    assert all(1400<png.width<1600 and 2000<png.height<2200 and png.height>png.width for png in png_images)
    chart=PdfReader(BytesIO(build_export(r,'pdf')))
    assert len(chart.pages)==(2 if interval==30 else 1)
    for page in chart.pages:
        assert abs(float(page.mediabox.width)-595.28)<1
        assert abs(float(page.mediabox.height)-841.89)<1
    text='\n'.join(page.extract_text() for page in chart.pages)
    assert '램프조업 수요 분석 (ICN)' in text and '2026.10.01 ~ 2026.10.31' in text
    assert '분석 기간' not in text and '표시 시간' not in text
    assert '10/01' in text and '10/31' in text
    assert '분석 조건' in text
    assert 'STD 50분 전 ~ STD 10분 후' in text
    assert 'STA 20분 전 ~ STA 30분 후' in text
    assert '조업 후 이동시간' in text and '10분 적용' in text
    assert all(value not in text for value in ('발생일', '전체 기간 요약', '구간 최대', '조 개수', '수집', '생성', '자료 UBIKAIS', '일별 최대 평균', '대표 피크'))
    assert '+1' not in text
    assert '23' in text and ('30' in text if interval==30 else True)
    report=chart
    assert len(report.pages)==report_pages
    assert '10분 적용' in report.pages[0].extract_text()
    for page in report.pages:
        assert abs(float(page.mediabox.width)-595.28)<1
        assert abs(float(page.mediabox.height)-841.89)<1
        page_text=page.extract_text()
        assert all(f'10/{day:02d}' in page_text for day in range(1,32))
        assert '오전 최대 수요' in page_text and '오후 최대 수요' in page_text
        assert '일별 편수' not in page_text and '출발' in page_text and '도착' in page_text
        assert r.result_id not in page_text
    assert '00:00' in report.pages[0].extract_text() if interval==60 else '00' in report.pages[0].extract_text()


@pytest.mark.parametrize('basis', ['scheduled', 'actual'])
@pytest.mark.parametrize('interval', [60, 30])
@pytest.mark.parametrize('day_start', [0, 120, 720])
def test_daily_flight_counts_follow_full_operating_day_on_each_page(basis, interval, day_start):
    from datetime import timedelta
    from reports.render import _figure

    settings = Settings('RKSI', date(2026,10,26), date(2026,10,28), mode='custom',
                        basis=basis, interval=interval, day_start=day_start)
    result = demo_result(settings)
    a, _ = settings.window
    expected = []
    for day in range(settings.days):
        start, end = a+timedelta(days=day), a+timedelta(days=day+1)
        expected.append(tuple(sum(f.direction == direction and start <= f.reference < end
                                  for f in result.flights) for direction in ('dep', 'arr')))
    n = 1440//interval
    for col_start in range(0, n, 24):
        fig = _figure(result, col_start, min(n, col_start+24))
        try:
            ax = fig.axes[1]
            displayed = {(int(t.get_position()[1]), int(t.get_position()[0])): int(t.get_text())
                         for t in ax.texts if t.get_text().isdigit()}
            assert [[displayed[r, c] for c in range(2)] for r in range(settings.days)] == [list(v) for v in expected]
            assert sum(displayed[r, 0] for r in range(settings.days)) == sum(c.dep_count for c in result.cells)
            assert sum(displayed[r, 1] for r in range(settings.days)) == sum(c.arr_count for c in result.cells)
        finally:
            fig.clear()


@pytest.mark.parametrize('interval,day_start', [(60, 0), (30, 120), (60, 125)])
@pytest.mark.parametrize('totals', [((0, 10), (10, 100)), ((0, 0), (0, 0)),
                                  ((53, 60), (60, 53)), ((56, 53), (56, 60))])
def test_count_shading_compares_each_direction_and_headers_align_with_hours(interval, day_start, totals):
    from dataclasses import replace
    import numpy as np
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from reports.render import _figure

    result = demo_result(Settings('RKSI', date(2026,10,26), date(2026,10,27),
                                  mode='custom', interval=interval, day_start=day_start))
    n = 1440//interval
    result.cells = tuple(replace(c, dep_count=totals[i//n][0] if i % n == 0 else 0,
                                arr_count=totals[i//n][1] if i % n == 0 else 0)
                         for i, c in enumerate(result.cells))
    previous_shades = None
    for col_start in range(0, n, 24):
        fig = _figure(result, col_start, min(n, col_start+24))
        try:
            canvas = FigureCanvasAgg(fig)
            canvas.draw()
            renderer = canvas.get_renderer()
            heatmap, counts = fig.axes
            def first_baseline(label):
                # Korean and numeric glyph bounds differ even on the same baseline.
                return (label.get_transform().transform(label.get_position())[1]
                        + label._get_layout(renderer)[1][0][3])
            hour_baseline = first_baseline(heatmap.get_xticklabels()[0])
            assert all(abs(first_baseline(label)-hour_baseline) < .1
                       for label in counts.get_xticklabels())
            assert not any(t.get_text() == '일별 편수' for t in counts.texts)
            image = counts.images[0]
            assert image.norm.vmin == 0 and image.norm.vmax == 1
            shades = image.to_rgba(image.get_array())
            assert np.allclose(shades[..., 0], shades[..., 1])
            assert np.allclose(shades[..., 1], shades[..., 2])
            for column in range(2):
                values = np.array(totals)[:, column]
                if values.min() == values.max():
                    assert np.allclose(shades[:, column], image.cmap(0.0))
                else:
                    assert np.allclose(shades[values.argmin(), column], image.cmap(0.0))
                    assert np.allclose(shades[values.argmax(), column], image.cmap(1.0))
            if previous_shades is not None:
                assert np.allclose(shades, previous_shades)
            previous_shades = shades
        finally:
            fig.clear()


def test_chart_split_respects_non_midnight_operating_day():
    from reports.render import build_export
    r=demo_result(Settings('RKSI',date(2026,10,26),date(2026,10,26),mode='custom',interval=30,day_start=360,airlines=('JJA','KAL')))
    chart=PdfReader(BytesIO(build_export(r,'pdf')))
    assert len(chart.pages)==2
    assert '06:00 ~ 18:00' in chart.pages[0].extract_text()
    assert '18:00 ~ 06:00' in chart.pages[1].extract_text()
    assert all('+1' not in page.extract_text() for page in chart.pages)
    assert all('램프조업 수요 분석 (ICN)' in page.extract_text() and '항공사 : 7C, KE' in page.extract_text() for page in chart.pages)


@pytest.mark.parametrize('basis', ['scheduled', 'actual'])
@pytest.mark.parametrize('interval', [60, 30])
def test_condition_panel_is_three_readable_rows_within_summary_width(basis, interval):
    import pymupdf
    from reports.render import build_export

    settings = Settings('RKSI', date(2026,10,1), date(2026,10,31),
                        basis=basis, interval=interval, day_start=120)
    document = pymupdf.open(stream=build_export(demo_result(settings), 'pdf'), filetype='pdf')
    for page in document:
        title = page.search_for('분석 조건')[0]
        panels = [drawing['rect'] for drawing in page.get_drawings()
                  if drawing['rect'].contains(title) and drawing['rect'].height < page.rect.height/2]
        panel = max(panels, key=lambda rect: rect.width)
        title_background = min(panels, key=lambda rect: rect.width)
        assert title_background.width < panel.width/4
        assert abs((title.x0+title.x1)/2-(title_background.x0+title_background.x1)/2) < 1
        assert abs((title.y0+title.y1)/2-(title_background.y0+title_background.y1)/2) < 2
        cards = [drawing['rect'] for drawing in page.get_drawings()
                 if drawing['rect'].y1 < panel.y0 and drawing['rect'].height > 50]
        assert len(cards) == 3
        assert abs(panel.x0-min(card.x0 for card in cards)) < 1
        assert abs(panel.x1-max(card.x1 for card in cards)) < 1
        assert panel.height < 70
        spans = [span for block in page.get_text('dict')['blocks'] if 'lines' in block
                 for line in block['lines'] for span in line['spans']
                 if panel.contains(pymupdf.Rect(span['bbox'])) and span['text'] != '분석 조건']
        rows = []
        for baseline in sorted(span['origin'][1] for span in spans):
            if not rows or baseline-rows[-1] > 1:
                rows.append(baseline)
        assert len(rows) == 3
        assert min(span['size'] for span in spans) >= 8
        assert '일일 분석 시간대' in page.get_text() and '02:00 ~ 다음 날 02:00' in page.get_text()
        assert '출도착 시간 기준' in page.get_text() and '집계 간격' in page.get_text()
        assert '계획(' not in page.get_text() and '실제(' not in page.get_text()
        all_spans = [span for block in page.get_text('dict')['blocks'] if 'lines' in block
                     for line in block['lines'] for span in line['spans']]
        heading = next(span for span in all_spans if span['text'] == '분석 조건')
        card_heading = next(span for span in all_spans if span['text'] == '오전 최대 수요')
        assert (heading['size'], heading['color'], heading['font']) == (
            card_heading['size'], card_heading['color'], card_heading['font'])
        for timing in (span for span in spans if '분 전 ~' in span['text']):
            separator = next(rect for rect in page.search_for('|')
                             if abs(rect.y0-timing['bbox'][1]) < 1)
            assert 0 <= separator.x0-timing['bbox'][2] < 15
        assert '한국시간' not in page.get_text() and '운영일' not in page.get_text()
        assert '10/01' in page.get_text() and '10/31' in page.get_text()
        if basis == 'actual':
            assert '실제시각이 없는 편은 STD/STA 적용' in page.get_text()
            assert 'Ramp OUT 50분 전 ~ Ramp OUT 10분 후' in page.get_text()
            assert 'Ramp IN 20분 전 ~ Ramp IN 30분 후' in page.get_text()
        if interval == 30:
            assert '이 페이지' in page.get_text()
        # Time headings must remain below the panel, including two-line 30-minute labels.
        below = [pymupdf.Rect(span['bbox']) for block in page.get_text('dict')['blocks'] if 'lines' in block
                 for line in block['lines'] for span in line['spans']
                 if span['origin'][1] > panel.y1]
        assert all(rect.y0 > panel.y1 for rect in below)
    document.close()


def test_report_zero_demand_and_clock_crossing():
    from datetime import datetime
    from domain.models import Diagnostics, KST
    from engine.demand import analyze
    from reports.render import build_export
    s=Settings('RKSI',date(2026,12,31),date(2026,12,31),mode='custom',interval=30,day_start=180,airlines=('JJA',))
    at=datetime(2026,12,31,tzinfo=KST)
    result=analyze(s,(),Diagnostics(),at,at)
    reader=PdfReader(BytesIO(build_export(result,'pdf')))
    assert len(reader.pages)==2
    for page in reader.pages:
        text=page.extract_text()
        assert text.count('0개 조')==2 and '발생일' not in text
        assert '12/31' in text and '항공사 : 7C' in text
        assert '일일 분석 시간대' in text and '03:00 ~ 다음 날 03:00' in text
    assert '03:00 ~ 15:00' in reader.pages[0].extract_text()
    assert '15:00 ~ 03:00' in reader.pages[1].extract_text()


def test_download_data_is_lazy_and_reused(monkeypatch):
    import reports.render as render
    calls=[]
    monkeypatch.setattr(render,'build_export',lambda result,kind: calls.append(kind) or b'file')
    cache={}
    download=render.lazy_download(object(),'png',cache)
    assert not calls
    assert download()==download()==b'file'
    assert calls==['png']


@pytest.mark.parametrize('kind',['png','pdf'])
def test_new_exports_block_unconfirmed_results(kind):
    from reports.render import build_export
    r=demo_result(Settings('RKSI',date(2026,10,26),date(2026,10,26),mode='custom'))
    r.exportable=False
    with pytest.raises(ValueError): build_export(r,kind)
