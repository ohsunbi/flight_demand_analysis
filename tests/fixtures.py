from datetime import datetime, timedelta

from domain.models import Batch, Contract, KST, Settings
from engine.demand import analyze
from normalization.flights import normalize

VERIFIED = Contract(True, True, True, ('CNL',), ('DEP','ARR','DLA'), False, 'Synthetic fixture contract only', actual_query_padding_days=0)


def demo_result(settings):
    batches = []
    a,b = settings.window
    start = a.date() - timedelta(days=8)
    end = b.date() + timedelta(days=8)
    day = start
    while day <= end:
        for direction in ('dep','arr'):
            rows = []
            for i in range(16):
                ref = datetime.combine(day, datetime.min.time(), KST) + timedelta(minutes=6*60+i*48+(day.day%5)*7)
                code = (settings.airlines or ('ESR','KAL','AAR'))[i % len(settings.airlines or ('ESR','KAL','AAR'))]
                raw = dict(flightPk=f'SYN-{direction}-{day}-{i}', fpId=f'{code}{100+i}',
                           apArr='RKPC', apIcao='RKPC', schDate=ref.strftime('%Y%m%d'), schTime=ref.strftime('%H%M'),
                           staDate=ref.strftime('%Y%m%d'), sta=ref.strftime('%H%M'))
                if i % 3:
                    actual = ref + timedelta(minutes=(i%4)*11)
                    raw['blockOffTime' if direction=='dep' else 'blockOnTime'] = actual.strftime('%Y%m%d%H%M')
                rows.append(raw)
            if settings.airlines:
                for code in settings.airlines:
                    batches.append(Batch(day,direction,code,tuple(r for r in rows if r['fpId'].startswith(code)),datetime(2026,10,27,9,tzinfo=KST)))
            else:
                batches.append(Batch(day,direction,'',tuple(rows),datetime(2026,10,27,9,tzinfo=KST)))
        day += timedelta(days=1)
    flights,diag = normalize(tuple(batches),settings,VERIFIED)
    result = analyze(settings,flights,diag,batches[0].fetched_at,batches[-1].fetched_at,synthetic=True)
    eligible = [f for f in result.flights if a <= f.reference < b]
    diag.actual_used = sum(f.reference_source in ('actual','actual_inferred') for f in eligible)
    diag.actual_date_inferred = sum(f.reference_source == 'actual_inferred' for f in eligible)
    diag.scheduled_used = len(eligible)-diag.actual_used
    return result

