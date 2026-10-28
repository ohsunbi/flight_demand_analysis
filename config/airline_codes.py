"""Local, source-attributed airline code reference; no runtime network access."""
import json
import re

from config import ROOT


REFERENCE = json.loads((ROOT / 'config' / 'airlines.json').read_text(encoding='utf-8'))
IATA_TO_ICAO = {}
ICAO_TO_IATA = {}
for record in REFERENCE['records']:
    IATA_TO_ICAO.setdefault(record['iata'], set()).add(record['icao'])
    ICAO_TO_IATA.setdefault(record['icao'], set()).add(record['iata'])
IATA_TO_ICAO = {key: tuple(sorted(values)) for key, values in IATA_TO_ICAO.items()}
ICAO_TO_IATA = {key: tuple(sorted(values)) for key, values in ICAO_TO_IATA.items()}


def parse_iata_codes(text, *, allow_empty=False):
    codes = sorted({code.strip().upper() for code in text.split(',') if code.strip()})
    if not codes and not allow_empty:
        raise ValueError('항공사 코드를 한 개 이상 입력하세요.')
    converted = []
    for code in codes:
        if not re.fullmatch(r'[A-Z0-9]{2}', code):
            raise ValueError(f'항공사 코드는 IATA 영문·숫자 2자리로 입력하세요: {code[:12]}')
        candidates = IATA_TO_ICAO.get(code, ())
        if not candidates:
            raise ValueError(f'등록되지 않은 항공사 코드입니다: {code}')
        if len(candidates) != 1:
            raise ValueError(f'여러 항공사에 연결된 코드입니다. 항공사 확인이 필요합니다: {code}')
        if len(ICAO_TO_IATA.get(candidates[0], ())) != 1:
            raise ValueError(f'조회 코드가 다른 IATA 코드와 중복됩니다. 항공사 확인이 필요합니다: {code}')
        converted.append(candidates[0])
    return tuple(sorted(set(converted)))


def to_iata_codes(icao_codes):
    """Presentation only; unmapped internal records retain their source code."""
    return tuple(sorted({ICAO_TO_IATA[code][0] if len(ICAO_TO_IATA.get(code, ())) == 1 else code
                         for code in icao_codes}))
