from datetime import date
from pathlib import Path
import pymupdf

from domain.models import Settings
from adapters.ubikais_client import UbikaisClient
from services.analysis import load_contract,run_analysis
from reports.render import build_downloads

if __name__=='__main__':
    target=Path('artifacts/live_reports');target.mkdir(parents=True,exist_ok=True)
    s=Settings('RKSI',date(2026,10,26),date(2026,10,26),mode='custom',basis='actual')
    result=run_analysis(s,UbikaisClient(retries=0,timeout=10),load_contract())
    files=build_downloads(result)
    (target/'actual.png').write_bytes(files['png'])
    (target/'actual.pdf').write_bytes(files['pdf'])
    doc=pymupdf.open(stream=files['pdf'],filetype='pdf')
    text='\n'.join(page.get_text() for page in doc)
    assert '날짜 추정' in text and str(result.diagnostics.actual_date_inferred) in text
    for page in doc:
        assert 840<page.rect.width<843 and 594<page.rect.height<597
        for font in page.get_fonts():
            assert doc.extract_font(font[0])[3], 'Font must be embedded'
    doc[0].get_pixmap(matrix=pymupdf.Matrix(1.6,1.6)).save(target/'actual_page_1.png')
    print('Live actual report: inference count, A4 dimensions, embedded fonts passed')
