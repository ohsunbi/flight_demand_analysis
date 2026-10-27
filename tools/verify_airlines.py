"""One-day, two-airline integration sample (including required boundary queries)."""
from datetime import date
import json
import time
from pathlib import Path

from domain.models import Settings
from adapters.ubikais_client import UbikaisClient
from services.analysis import load_contract,run_analysis

if __name__=='__main__':
    s=Settings('RKSI',date(2026,10,26),date(2026,10,26),mode='custom',airlines=('APJ','ESR'))
    start=time.monotonic()
    result=run_analysis(s,UbikaisClient(retries=0,timeout=10),load_contract())
    assert all(set(f.query_airlines).issubset(set(s.airlines)) for f in result.flights)
    assert len({f.key for f in result.flights})==len(result.flights)
    report=dict(airlines=s.airlines,seconds=round(time.monotonic()-start,2),raw=result.diagnostics.raw,
                dep_count=sum(c.dep_count for c in result.cells),arr_count=sum(c.arr_count for c in result.cells),
                duplicates=result.diagnostics.duplicates,exportable=result.exportable)
    Path('artifacts/airlines.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
