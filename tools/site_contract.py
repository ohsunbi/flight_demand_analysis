import json
import re
from urllib.request import Request, urlopen

if __name__ == '__main__':
    for url in ['https://ubikais.fois.go.kr:8030/sysUbikais/biz/fpl/dep.js?ver=1.2', 'https://ubikais.fois.go.kr:8030/sysUbikais/biz/fpl/arr.js?ver=1.2']:
        try:
            with urlopen(Request(url, headers={'User-Agent':'Mozilla/5.0'}), timeout=10) as r:
                body = r.read().decode('utf-8'); final = r.url
            print(json.dumps({'url':url, 'final':final, 'length':len(body),
                 'title':re.findall(r'<title>(.*?)</title>',body,re.S),
                 'links':re.findall(r'(?:src|href)=["\x27]([^"\x27]+)',body)[:35],
                 'locations':re.findall(r'location[^;]{0,120}',body)[:3]},ensure_ascii=False))
            print('routes', sorted(set(re.findall(r'[/\w.]+\.fois', body)))[:45])
            from pathlib import Path
            target=Path('artifacts/public_source'); target.mkdir(parents=True,exist_ok=True)
            (target/('arr.js' if '/arr.js' in url else 'dep.js')).write_text(body,encoding='utf-8')
            for term in ['UTC', 'KST', '한국시간', 'CNL', 'blockOff', 'blockOn', 'staDate', 'schDate', 'depStatus', 'arrStatus', 'srchDate', 'amsRecPkCha']:
                print(term,[body[max(0,m.start()-160):m.end()+220] for m in list(re.finditer(term,body))[:5]])
        except Exception as e:
            print(type(e).__name__)
