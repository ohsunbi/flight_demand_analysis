"""Generate and inspect synthetic report artifacts; no network calls."""
from datetime import date
from pathlib import Path
from io import BytesIO

import pymupdf as fitz
from PIL import Image
from pypdf import PdfReader

from domain.models import Settings
from reports.render import build_downloads
from tests.fixtures import demo_result

def main():
    target=Path('artifacts/reports');target.mkdir(parents=True,exist_ok=True)
    for interval in [60,30]:
        settings=Settings('RKSI',date(2026,10,1),date(2026,10,31),interval=interval,basis='actual')
        result=demo_result(settings)
        output=build_downloads(result)
        png=target/f'month_{interval}.png';pdf=target/f'month_{interval}.pdf'
        png.write_bytes(output['png']);pdf.write_bytes(output['pdf'])
        img=Image.open(BytesIO(output['png'])); reader=PdfReader(BytesIO(output['pdf']))
        text='\n'.join(page.extract_text() for page in reader.pages)
        assert '2026-10-01' in text and '2026-10-31' in text
        assert all(f'2026-10-{i:02d}' in text for i in range(1,32))
        assert '00:00' in text and ('23:00' if interval==60 else '23:30') in text
        assert len(reader.pages)==(2 if interval==60 else 4)
        doc=fitz.open(pdf)
        for i,page in enumerate(doc):
            page.get_pixmap(matrix=fitz.Matrix(1.6,1.6)).save(target/f'month_{interval}_page_{i+1}.png')
        assert len(doc[0].get_fonts())>0
        print(interval,'PNG',img.size,'PDF pages',len(reader.pages),'bytes',len(output['pdf']))

if __name__=='__main__':main()
