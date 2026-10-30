import calendar
from datetime import date

from config import airport_airlines
from domain.models import Offsets, Settings
from config.airline_codes import parse_icao_codes


def defaults(today):
    return Settings('RKSI', today.replace(day=1), today.replace(day=calendar.monthrange(today.year, today.month)[1]),
                    airlines=airport_airlines('RKSI'))


def encode(settings):
    settings.validate()
    return dict(v='3', airport=settings.airport, mode=settings.mode,
                start=settings.start.isoformat(), end=settings.end.isoformat(),
                airlines=','.join(settings.airlines), basis=settings.basis,
                day_start=str(settings.day_start), interval=str(settings.interval), directions=','.join(settings.directions),
                dep=','.join(str(v) for v in (settings.dep.start, settings.dep.end, settings.dep.reusable)),
                arr=','.join(str(v) for v in (settings.arr.start, settings.arr.end, settings.arr.reusable)))


def decode(params, today):
    if not params:
        return defaults(today), None
    try:
        if sum(len(str(k)) + len(str(v)) for k, v in params.items()) > 4096:
            raise ValueError('설정 URL이 너무 깁니다.')
        version = params.get('v', '3')
        if version != '3':
            raise ValueError('지원하지 않는 설정 URL 버전입니다.')
        base = encode(defaults(today))
        base.update({k: str(v) for k, v in params.items() if k in base})
        if 'airlines' not in params:
            base['airlines'] = ','.join(airport_airlines(base['airport']))
        airlines = parse_icao_codes(base['airlines'], allow_empty=True)
        def offsets(key):
            values = [int(v) for v in base[key].split(',')]
            return Offsets(*values)
        result = Settings(base['airport'], date.fromisoformat(base['start']), date.fromisoformat(base['end']),
                          base['mode'], airlines,
                          base['basis'], int(base['day_start']), int(base['interval']), offsets('dep'), offsets('arr'),
                          tuple(base['directions'].split(',')))
        result.validate()
        return result, None
    except (ValueError, TypeError, OverflowError):
        return defaults(today), '설정 URL이 잘못되었거나 지원 범위를 벗어나 기본 설정을 불러왔습니다. 조건을 확인하세요.'

