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
    assert '이동 10분' in text and '오전 최대 수요' in text and '오후 최대 수요' in text
    assert '일별 최대 평균' not in text and '대표 피크' not in text
    with ZipFile(BytesIO(data['png'])) as archive:
        assert len(archive.namelist()) == 2
        assert all(Image.open(BytesIO(archive.read(name))).height > 2000 for name in archive.namelist())


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
    assert 'STD 50분 전부터 10분 후까지 · 이동 10분' in text
    assert 'STA 20분 전부터 30분 후까지 · 이동 10분' in text
    assert all(value not in text for value in ('발생일', '전체 기간 요약', '구간 최대', '조 개수', '수집', '생성', '자료 UBIKAIS', '일별 최대 평균', '대표 피크'))
    assert '+1' not in text
    assert '23' in text and ('30' in text if interval==30 else True)
    report=chart
    assert len(report.pages)==report_pages
    assert '이동 10분' in report.pages[0].extract_text()
    for page in report.pages:
        assert abs(float(page.mediabox.width)-595.28)<1
        assert abs(float(page.mediabox.height)-841.89)<1
        page_text=page.extract_text()
        assert all(f'10/{day:02d}' in page_text for day in range(1,32))
        assert '오전 최대 수요' in page_text and '오후 최대 수요' in page_text
        assert r.result_id not in page_text
    assert '00:00' in report.pages[0].extract_text() if interval==60 else '00' in report.pages[0].extract_text()


def test_chart_split_respects_non_midnight_operating_day():
    from reports.render import build_export
    r=demo_result(Settings('RKSI',date(2026,10,26),date(2026,10,26),mode='custom',interval=30,day_start=360,airlines=('JJA','KAL')))
    chart=PdfReader(BytesIO(build_export(r,'pdf')))
    assert len(chart.pages)==2
    assert '06:00 ~ 18:00' in chart.pages[0].extract_text()
    assert '18:00 ~ 06:00' in chart.pages[1].extract_text()
    assert all('+1' not in page.extract_text() for page in chart.pages)
    assert all('램프조업 수요 분석 (ICN)' in page.extract_text() and '항공사 : 7C, KE' in page.extract_text() for page in chart.pages)


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
        assert '하루 03:00 ~ 다음 날 03:00' in text
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
