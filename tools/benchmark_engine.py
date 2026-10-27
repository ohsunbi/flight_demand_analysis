"""31-day synthetic load benchmark, deliberately makes no API requests."""
import json
import time
import tracemalloc
from datetime import date,datetime,timedelta
from pathlib import Path
import random

from domain.models import Diagnostics,Flight,KST,Settings
from engine.demand import analyze

if __name__=='__main__':
    settings=Settings('RKSI',date(2026,10,1),date(2026,10,31),interval=30)
    a,b=settings.window
    rng=random.Random(219)
    tracemalloc.start()
    flights=[]
    for i in range(31*1250):
        ref=a+timedelta(minutes=rng.randrange(31*1440))
        start=ref-timedelta(minutes=50)
        end=ref+timedelta(minutes=20)
        flights.append(Flight(str(i),'dep' if i%2 else 'arr','SYN'+str(i),'RKSI','RKPC',ref,None,ref,'scheduled',(),(),'',('',''),start,end,end))
    began=time.perf_counter()
    result=analyze(settings,tuple(flights),Diagnostics(),a,a)
    elapsed=time.perf_counter()-began
    _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    report=dict(synthetic=True,flights=len(flights),days=31,cells=len(result.cells),
                seconds=round(elapsed,3),peak_python_allocated_mib=round(peak/1024**2,2),
                note='Engine only; tracemalloc includes fixture construction. Not network or Cloud benchmark.')
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/benchmark.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
