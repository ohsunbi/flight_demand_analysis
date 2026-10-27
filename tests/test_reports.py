from datetime import date
from io import BytesIO

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
    assert '00:00' in text and '23:30' in text and '2026-10-26' in text
    assert '가상 데이터' in text
    assert Image.open(BytesIO(data['png'])).width>4000


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
