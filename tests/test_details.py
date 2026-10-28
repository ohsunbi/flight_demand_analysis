from dataclasses import replace
from datetime import date

import pytest

from config.airport_codes import icao_to_iata
from domain.models import Settings
from tests.fixtures import demo_result
from ui.details import frame, flight_label


@pytest.mark.parametrize('code,expected', [
    ('ZSJN', 'TNA'), ('RJAA', 'NRT'), ('RKSI', 'ICN'), ('RKPC', 'CJU'),
    (' zsjn ', 'TNA'), ('ICN', 'ICN'), ('ZZZZ', 'ZZZZ'), ('', ''), (None, ''),
])
def test_airport_code_display(code, expected):
    assert icao_to_iata(code) == expected


@pytest.mark.parametrize('original,expected', [
    ('JJA524M','7C524M'), ('TTW123','IT123'), ('AXM12A','AK12A'),
    ('HKE123','UO123'), ('CQH123','9C123'), ('CDC123','GJ123'),
    ('CSC123','3U123'), ('RLH123','DR123'), ('7C524M','7C524M'),
    ('ZZZ123','ZZZ123'), ('ASA123','ASA123'), ('',''), ('JJA','JJA'),
])
def test_flight_label_preserves_suffix_and_unmapped_codes(original, expected):
    assert flight_label(original) == expected


def test_detail_frame_uses_iata_without_query_airline_column():
    result = demo_result(Settings('RKSI', date(2026, 10, 25), date(2026, 10, 25), mode='custom'))
    flights = tuple(replace(result.flights[0], route=route) for route in ('ZSJN', 'RJAA', 'ZZZZ'))
    table = frame(flights)
    assert '조회 항공사' not in table.columns
    assert table.columns.tolist() == ['방향', '편명', '출도착지', 'STA/STD', 'RAMP I/O', '조업 시작', '조업 종료', '후속 조업 가능']
    assert table.iloc[0]['STA/STD'] == flights[0].scheduled.strftime('%H:%M')
    assert table.iloc[0]['RAMP I/O'] == (flights[0].actual.strftime('%H:%M') if flights[0].actual else '—')
    for column, attribute in [('조업 시작', 'start'), ('조업 종료', 'end'), ('후속 조업 가능', 'reusable')]:
        assert table.iloc[0][column] == getattr(flights[0], attribute).strftime('%H:%M')
    assert table['출도착지'].tolist() == ['TNA', 'NRT', 'ZZZZ']
    assert [f.route for f in flights] == ['ZSJN', 'RJAA', 'ZZZZ']
    original=replace(flights[0],flight_id='JJA524M')
    assert frame((original,)).iloc[0]['편명']=='7C524M'
    assert original.flight_id=='JJA524M'
