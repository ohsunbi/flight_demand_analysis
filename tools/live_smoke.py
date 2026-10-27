"""Small live integration check; save public aggregates, never raw flight rows."""
import json
import time
import argparse
from datetime import date
from pathlib import Path

from adapters.ubikais_client import UbikaisClient
from domain.models import Settings
from services.analysis import load_contract, run_analysis

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--actual',action='store_true');args=parser.parse_args()
    settings=Settings('RKSI',date(2026,10,26),date(2026,10,26),mode='custom',basis='actual' if args.actual else 'scheduled')
    started=time.monotonic()
    client=UbikaisClient(retries=0,timeout=10)
    def progress(done,total,message):print(f'{done}/{total} {message}',flush=True)
    result=run_analysis(settings,client,load_contract(),progress=progress)
    report=dict(date=str(settings.start),airport=settings.airport,seconds=round(time.monotonic()-started,2),
                raw=result.diagnostics.raw,duplicates=result.diagnostics.duplicates,
                quarantine=result.diagnostics.quarantined,unresolved_actual_dates=result.diagnostics.date_unresolved,
                unknown_status=result.diagnostics.unknown_status,maximum=result.maximum,
                actual_used=result.diagnostics.actual_used,inferred_dates=result.diagnostics.actual_date_inferred,
                scheduled_used=result.diagnostics.scheduled_used,
                dep_count=sum(c.dep_count for c in result.cells),arr_count=sum(c.arr_count for c in result.cells),
                exportable=result.exportable,blockers=result.blockers)
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/live_smoke_actual.json' if args.actual else 'artifacts/live_smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
