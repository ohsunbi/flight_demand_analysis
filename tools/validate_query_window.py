"""Bounded live contract observations. Records aggregates, not raw flight data."""
import json
from collections import Counter
from datetime import date,datetime
from pathlib import Path

from adapters.ubikais_client import UbikaisClient
from normalization.flights import parse_datetime
from services.planner import Task

if __name__=='__main__':
    client=UbikaisClient(retries=0,timeout=10)
    evidence=[]
    for airport in ['RKSI','RKSS','RKPC']:
        days=[date(2026,10,25),date(2026,10,26),date(2026,10,27)] if airport=='RKSI' else [date(2026,10,26)]
        for direction in ('dep','arr'):
            offsets=Counter();statuses=Counter();rows=0;identities=set()
            for day in days:
                batch=client.fetch(airport,Task(day,direction))
                for raw in batch.records:
                    key,tkey=('schDate','schTime') if direction=='dep' else ('staDate','sta')
                    dt=parse_datetime(raw.get(key),raw.get(tkey))
                    offsets[str((dt.date()-day).days) if dt else 'invalid']+=1
                    statuses[str(raw.get('depStatus' if direction=='dep' else 'arrStatus'))]+=1
                    identities.add(str(raw.get('flightPk')))
                rows+=len(batch.records)
            record=dict(airport=airport,direction=direction,query_days=len(days),rows=rows,
                        scheduled_date_minus_query_date=dict(offsets),statuses=dict(statuses),unique_ids=len(identities))
            evidence.append(record);print(json.dumps(record,ensure_ascii=False),flush=True)
    Path('artifacts/query_window.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
