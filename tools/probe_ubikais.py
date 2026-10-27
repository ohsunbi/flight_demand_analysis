"""Small read-only API probe. Never prints raw response bodies or credentials."""
import argparse
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def probe(day, airport, direction, airline):
    params = dict(srchDate=day, srchDatesh=day.replace('-', ''), srchAl=airline,
                  srchFln='', srchDep=airport if direction == 'dep' else '',
                  srchArr=airport if direction == 'arr' else '', cmd='get-records',
                  limit=5, offset=0, downloadYn=1)
    endpoint = 'selectDep.fois' if direction == 'dep' else 'selectArr.fois'
    url = 'https://ubikais.fois.go.kr:8030/sysUbikais/biz/fpl/' + endpoint + '?' + urlencode(params)
    summary = dict(date=day, airport=airport, direction=direction, airline=airline or 'ALL')
    try:
        with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}), timeout=15) as response:
            payload = json.loads(response.read().decode('utf-8'))
        records = payload.get('records') or []
        safe = ['fpId', 'schDate', 'schTime', 'staDate', 'sta', 'depStatus', 'arrStatus',
                'blockOffTime', 'blockOnTime', 'atd', 'ata', 'etd', 'eta', 'chaYn']
        summary.update(status=payload.get('status'), total=payload.get('total'), count=len(records),
                       keys=sorted({k for record in records for k in record}),
                       sample=[{k: r.get(k) for k in safe if k in r} for r in records[:3]])
    except Exception as exc:
        summary.update(error_type=type(exc).__name__)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', default='2026-10-26')
    parser.add_argument('--airport', default='RKSI')
    args = parser.parse_args()
    for direction in ('dep', 'arr'):
        for airline in ('', 'ESR'):
            print(json.dumps(probe(args.date, args.airport, direction, airline), ensure_ascii=False))
