"""Select Excel movements and apply source precedence before demand calculation."""
from collections import defaultdict
from datetime import timedelta
import re

from config import AIRPORTS
from config.airline_codes import ICAO_TO_IATA
from config.airport_codes import icao_to_iata
from domain.models import Flight
from normalization.flights import identity

_IATA_TO_ICAO = defaultdict(list)
for icao, iata in ICAO_TO_IATA.items():
    _IATA_TO_ICAO[iata].append(icao)


def _icao_flight_id(value, row):
    if re.match(r'[A-Z]{3}[0-9]', value):
        return value
    candidates = _IATA_TO_ICAO.get(value[:2], ())
    if len(candidates) != 1:
        raise ValueError(f'{row}행: 항공편명의 IATA 코드를 한 항공사로 변환할 수 없습니다. ICAO 3자리 접두어가 붙은 편명을 입력하세요.')
    return candidates[0] + value[2:]


def _flight_from_row(row, settings, direction, flight_id, route):
    scheduled = row.std if direction == 'dep' else row.sta
    offsets = settings.dep if direction == 'dep' else settings.arr
    day, clock = scheduled.strftime('%Y%m%d'), scheduled.strftime('%H%M')
    return Flight(
        key='excel:'+identity(settings.airport, direction, f'{flight_id}|{route}', day),
        direction=direction, flight_id=flight_id, airport=settings.airport, route=route,
        scheduled=scheduled, actual=None, reference=scheduled,
        reference_source='fallback' if settings.basis == 'actual' else 'scheduled',
        queried_dates=(), query_airlines=(flight_id[:3],), status='', raw_dates=(day, clock),
        start=scheduled+timedelta(minutes=offsets.start),
        end=scheduled+timedelta(minutes=offsets.end),
        reusable=scheduled+timedelta(minutes=offsets.reusable),
        warnings=('엑셀 입력 · 예정시각',),
    )


def _match_key(flight):
    if flight.scheduled is None:
        return None
    return (flight.direction, flight.scheduled.date(), flight.flight_id, icao_to_iata(flight.route))


def select_excel(rows, settings):
    """Keep adjacent dates so shifts that touch the window and mixed replacements survive."""
    airport_codes = (settings.airport, AIRPORTS[settings.airport][1])
    unique = {}
    duplicates = excluded = 0
    for row in rows:
        directions = []
        if row.origin in airport_codes and 'dep' in settings.directions:
            directions.append(('dep', icao_to_iata(row.destination)))
        if row.destination in airport_codes and 'arr' in settings.directions:
            directions.append(('arr', icao_to_iata(row.origin)))
        if not directions:
            excluded += 1
            continue
        flight_id = _icao_flight_id(row.flight_id, row.number)
        if settings.airlines and flight_id[:3] not in settings.airlines:
            excluded += 1
            continue
        for direction, route in directions:
            flight = _flight_from_row(row, settings, direction, flight_id, route)
            key = _match_key(flight)
            previous = unique.get(key)
            if previous is not None:
                _, previous_row = previous
                if (previous_row.std, previous_row.sta) != (row.std, row.sta):
                    raise ValueError(f'{previous_row.number}행과 {row.number}행: 같은 편의 STD 또는 STA가 서로 다릅니다.')
                duplicates += 1
                continue
            unique[key] = (flight, row)
    return tuple(flight for flight, _ in unique.values()), duplicates, excluded


def excel_overlaps(flight, window):
    start, end = window
    return (start <= flight.reference < end
            or (flight.start < end and flight.reusable > start and flight.start < flight.reusable))


def merge_excel(site_flights, excel_flights):
    keys = {_match_key(f) for f in excel_flights}
    replaced = set()
    remaining = []
    for flight in site_flights:
        key = _match_key(flight)
        if key in keys:
            if key in replaced:
                raise ValueError('같은 엑셀편에 대응하는 UBIKAIS 운항편이 여러 건입니다. 날짜·편명·구간을 확인하세요.')
            replaced.add(key)
        else:
            remaining.append(flight)
    return (*remaining, *excel_flights), len(replaced)
