from datetime import date, datetime
from dataclasses import replace
from hashlib import sha256
from io import BytesIO
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from adapters.excel_schedule import read_schedule
from config import ROOT
from domain.models import Batch, Contract, KST, Settings
from services.analysis import run_analysis
from services.excel_schedule import merge_excel, select_excel
from tests.fixtures import VERIFIED

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
TEMPLATE = ROOT/'assets'/'schedule_template.xlsx'
DEPARTURE = ('2026-11-18', 'ZE101', 'ICN', 'NRT', '2330', '0050+1')
ARRIVAL = ('2026-11-17', 'ZE102', 'NRT', 'ICN', '2330', '0050+1')


def filled_template(*rows):
    output = BytesIO()
    with ZipFile(TEMPLATE) as original, ZipFile(output, 'w') as upload:
        for name in original.namelist():
            content = original.read(name)
            if name == 'xl/worksheets/sheet1.xml':
                sheet = ET.fromstring(content)
                sheet_data = sheet.find(NS+'sheetData')
                for row in list(sheet_data)[1:]:
                    sheet_data.remove(row)
                for number, values in enumerate(rows, 2):
                    row = ET.SubElement(sheet_data, NS+'row', r=str(number))
                    for column, value in zip('ABCDEF', values):
                        cell = ET.SubElement(row, NS+'c', r=f'{column}{number}', t='inlineStr')
                        ET.SubElement(ET.SubElement(cell, NS+'is'), NS+'t').text = value
                content = ET.tostring(sheet)
            upload.writestr(name, content)
    return output.getvalue()


def settings(*, airlines=('ESR',), basis='scheduled'):
    return Settings('RKSI', date(2026, 11, 18), date(2026, 11, 18),
                    mode='custom', airlines=airlines, basis=basis)


def test_template_row_order_and_explicit_next_day():
    with pytest.raises(ValueError, match='운항편을 한 행 이상'):
        read_schedule(TEMPLATE.read_bytes())
    departure, arrival = read_schedule(filled_template(DEPARTURE, ARRIVAL))
    assert departure.std == datetime(2026, 11, 18, 23, 30, tzinfo=KST)
    assert departure.sta == datetime(2026, 11, 19, 0, 50, tzinfo=KST)
    flights, duplicates, excluded = select_excel((departure, arrival), settings())
    assert [(f.direction, f.flight_id, f.scheduled.hour) for f in flights] == [
        ('dep', 'ESR101', 23), ('arr', 'ESR102', 0),
    ]
    assert flights[1].scheduled.date() == date(2026, 11, 18)
    assert (duplicates, excluded) == (0, 0)


@pytest.mark.parametrize(('std', 'sta', 'error'), [
    ('2330', '0050', r'2행: .*\+1'),
    ('2330+1', '0050+1', '2행: STD'),
    ('2330', '2460+1', '2행: STA'),
])
def test_invalid_time_is_reported_with_row_number(std, sta, error):
    with pytest.raises(ValueError, match=error):
        read_schedule(filled_template((*DEPARTURE[:4], std, sta)))


def test_excel_airline_filter_and_duplicates():
    rows = read_schedule(filled_template(DEPARTURE, DEPARTURE))
    assert select_excel(rows, settings(airlines=('JJA',))) == ((), 0, 2)
    flights, duplicates, excluded = select_excel(rows, settings())
    assert (len(flights), duplicates, excluded) == (1, 1, 0)
    conflict = (*DEPARTURE[:4], '2300', DEPARTURE[5])
    with pytest.raises(ValueError, match='2행과 3행'):
        select_excel(read_schedule(filled_template(DEPARTURE, conflict)), settings())


class FixtureSite:
    def __init__(self):
        self.requests = []

    def fetch(self, airport, task, *, refresh, **kwargs):
        self.requests.append((task.day, refresh))
        rows = ()
        if task.day == date(2026, 11, 18) and task.direction == 'dep':
            rows = (
                dict(flightPk='site-1', fpId='ESR101', schDate='20261118',
                     schTime='1030', blockOffDate='20261118', blockOffTime='1100',
                     depStatus='DEP', apArr='RJAA'),
                dict(flightPk='site-2', fpId='ESR103', schDate='20261118',
                     schTime='2330', blockOffDate='20261118', blockOffTime='2330',
                     depStatus='DEP', apArr='RJAA'),
            )
        return Batch(task.day, task.direction, '', rows, datetime.now(KST))


def test_three_sources_and_excel_priority():
    upload = filled_template(DEPARTURE, ARRIVAL)
    rows = read_schedule(upload)
    digest = sha256(upload).hexdigest()
    site = FixtureSite()
    site_result = run_analysis(settings(basis='actual'), site, VERIFIED)
    assert site_result.source_mode == 'site'
    assert site_result.flights[0].reference.hour == 11
    assert site_result.maximum == 1

    excel_flights, *_ = select_excel(rows, settings())
    excel_result = run_analysis(settings(), None, Contract(), source_mode='excel',
                                excel_flights=excel_flights, upload_digest=digest)
    assert excel_result.source_mode == 'excel' and excel_result.exportable
    assert excel_result.diagnostics.scheduled_used == 2
    assert excel_result.maximum == 1

    actual_settings = settings(basis='actual')
    excel_flights, *_ = select_excel(rows, actual_settings)
    mixed = run_analysis(actual_settings, site, VERIFIED, refresh=True, source_mode='site_excel',
                         excel_flights=excel_flights, upload_digest=digest)
    assert any(refresh for _, refresh in site.requests)
    assert mixed.source_mode == 'site_excel' and mixed.upload_digest == digest
    assert mixed.diagnostics.actual_used == 1 and mixed.maximum == 2
    assert {(f.flight_id, f.reference.hour, f.reference_source) for f in mixed.flights} == {
        ('ESR101', 23, 'fallback'), ('ESR102', 0, 'fallback'), ('ESR103', 23, 'actual'),
    }
    assert '1건을 엑셀 자료로 대체' in ' '.join(mixed.diagnostics.messages)


def test_mixed_refuses_ambiguous_site_candidates():
    flight, = select_excel(read_schedule(filled_template(DEPARTURE)), settings())[0]
    site = (replace(flight, key='site-one'), replace(flight, key='site-two'))
    with pytest.raises(ValueError, match='UBIKAIS 운항편이 여러 건'):
        merge_excel(site, (flight,))
