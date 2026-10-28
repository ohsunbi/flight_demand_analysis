"""Generate and inspect synthetic report artifacts; no network calls."""
from datetime import date
from pathlib import Path
from io import BytesIO
from zipfile import ZipFile

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
        png=target/f'month_{interval}{".zip" if interval==30 else ".png"}';pdf=target/f'month_{interval}.pdf'
        png.write_bytes(output['png']);pdf.write_bytes(output['pdf'])
        if interval==30:
            with ZipFile(BytesIO(output['png'])) as archive:
                assert len(archive.namelist())==2
                images=[Image.open(BytesIO(archive.read(name))) for name in archive.namelist()]
        else:
            images=[Image.open(BytesIO(output['png']))]
        assert all(image.height>image.width for image in images)
        reader=PdfReader(BytesIO(output['pdf']))
        text='\n'.join(page.extract_text() for page in reader.pages)
        assert '2026.10.01' in text and '2026.10.31' in text
        assert all(f'10/{i:02d}' in text for i in range(1,32))
        assert '00:00' in text and '23' in text
        assert len(reader.pages)==(1 if interval==60 else 2)
        doc=fitz.open(pdf)
        for i,page in enumerate(doc):
            page.get_pixmap(matrix=fitz.Matrix(1.6,1.6)).save(target/f'month_{interval}_page_{i+1}.png')
        assert len(doc[0].get_fonts())>0
        print(interval,'PNG',[image.size for image in images],'PDF pages',len(reader.pages),'bytes',len(output['pdf']))

if __name__=='__main__':main()
