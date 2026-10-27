"""Read-only contract probe; prints only public code and aggregate flight metadata."""
import json
import re
from collections import Counter
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = 'https://ubikais.fois.go.kr:8030/sysUbikais/biz/fpl/'

def read(url):
    with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}), timeout=15) as response:
        return response.read().decode('utf-8')

if __name__ == '__main__':
    for endpoint in ['selectDep.fois', 'selectArr.fois']:
        try:
            body = read(BASE + endpoint)
            print(endpoint, 'length', len(body), 'scripts', re.findall(r'<script[^>]*src=["\x27]([^"\x27]+)', body))
            for pattern in ['UTC', 'KST', '한국', '취소', '결항', 'blockOffTime', 'blockOnTime', 'srchAl', 'CNL', 'staDate']:
                hits = [body[max(0, m.start()-100):m.end()+140] for m in list(re.finditer(pattern, body))[:5]]
                if hits:
                    print(pattern, json.dumps(hits, ensure_ascii=False))
        except Exception as exc:
            print(type(exc).__name__)
    for direction in ['dep', 'arr']:
        params = dict(srchDate='2026-10-26', srchDatesh='20261026', srchAl='', srchFln='',
                      srchDep='RKSI' if direction == 'dep' else '', srchArr='RKSI' if direction == 'arr' else '',
                      cmd='get-records', limit=5, offset=0, downloadYn=1)
        rows = json.loads(read(BASE + ('selectDep.fois' if direction == 'dep' else 'selectArr.fois') + '?' + urlencode(params)))['records']
        print(direction, 'status', dict(Counter(str(x.get(direction+'Status')) for x in rows)),
              'dates', dict(Counter(str(x.get('schDate' if direction == 'dep' else 'staDate')) for x in rows)))
        print('ids', len(rows), len(set(x.get('flightPk') for x in rows)), 'changed', dict(Counter(str(x.get('chaYn')) for x in rows)))
        print('odd dates', [{k: x.get(k) for k in ['fpId', 'staDate', 'sta', 'arrStatus', 'blockOnTime']}
                           for x in rows if direction == 'arr' and x.get('staDate') != '20261026'][:8])
