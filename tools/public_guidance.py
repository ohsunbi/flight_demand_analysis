"""Inspect public UI guidance and lookup metadata, without flight payloads."""
import re
from pathlib import Path
from urllib.request import urlopen,Request

if __name__=='__main__':
    for name,url in [
        ('dep.html','https://ubikais.fois.go.kr:8030/sysUbikais/biz/fpl/dep'),
        ('com.js','https://ubikais.fois.go.kr:8030/sysUbikais/biz/pib/com.js'),
        ('content.js','https://ubikais.fois.go.kr:8030/sysCommon/ubikais/html/js/content.js?ver=1.5')]:
        with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=15) as r:body=r.read().decode('utf-8')
        Path('artifacts/public_source').mkdir(parents=True,exist_ok=True)
        Path('artifacts/public_source',name).write_text(body,encoding='utf-8')
        for term in ['UTC','KST','시간','시각','기준','CNL','srchAl','dateObj','srchAd']:
            print(name,term,[body[max(0,m.start()-100):m.end()+140] for m in list(re.finditer(term,body))[:3]])
