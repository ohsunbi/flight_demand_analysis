"""Read the six input columns of an uploaded XLSX without evaluating formulas."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from io import BytesIO
from math import isfinite
from pathlib import PurePosixPath
import re
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from domain.models import KST

HEADERS = ('출발일', '항공편명', '출발지', '도착지', 'STD', 'STA')
MAX_UPLOAD_MB = 5
MAX_ROWS = 10_000
_NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
_RID = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
_FLIGHT = re.compile(r'(?:[A-Z]{3}|[A-Z0-9]{2})[0-9]{1,6}[A-Z]?')
_AIRPORT = re.compile(r'[A-Z]{3,4}')


@dataclass(frozen=True)
class ScheduleRow:
    number: int
    flight_id: str
    origin: str
    destination: str
    std: datetime
    sta: datetime


def _xml(book, path):
    data = book.read(path).decode('utf-8-sig')
    if '<!DOCTYPE' in data or '<!ENTITY' in data:
        raise ValueError('지원하지 않는 엑셀 XML 형식입니다.')
    return ET.fromstring(data)


def _sheet(book, workbook):
    sheet = next((s for s in workbook.iter(_NS+'sheet') if s.get('name') == 'Schedule'), None)
    if sheet is None:
        raise ValueError('Schedule 시트가 필요합니다. 다운로드한 양식을 사용하세요.')
    for rel in _xml(book, 'xl/_rels/workbook.xml.rels'):
        if rel.get('Id') == sheet.get(_RID) and rel.get('Type', '').endswith('/worksheet'):
            target = rel.get('Target', '')
            path = PurePosixPath(target.lstrip('/') if target.startswith('/') else 'xl/'+target)
            if rel.get('TargetMode') != 'External' and path.parts[:2] == ('xl', 'worksheets') and '..' not in path.parts:
                return _xml(book, str(path))
    raise ValueError('Schedule 시트를 읽을 수 없습니다.')


def _value(cell, strings):
    kind = cell.get('t', 'n')
    if kind == 'inlineStr':
        return ''.join(t.text or '' for t in cell.iter(_NS+'t')).strip()
    value = cell.findtext(_NS+'v', '').strip()
    if not value:
        return ''
    if kind == 's':
        if not value.isascii() or not value.isdecimal():
            raise ValueError('셀 문자열을 읽을 수 없습니다.')
        return strings[int(value)]
    if kind in ('str', 'd'):
        return value
    if kind == 'n':
        try:
            return float(value)
        except ValueError:
            raise ValueError('엑셀 숫자 셀의 형식이 잘못되었습니다.') from None
    raise ValueError('입력 칸에는 날짜, 시각 또는 텍스트 값을 넣으세요.')


def _date(value, epoch):
    if isinstance(value, float):
        if not value.is_integer() or not 0 <= value <= 100_000:
            raise ValueError('출발일은 날짜만 입력하세요.')
        result = epoch+timedelta(days=int(value))
    else:
        match = re.fullmatch(r'([0-9]{4})-([0-9]{1,2})-([0-9]{1,2})(?:T00:00:00(?:\.0+)?)?', value)
        if not match:
            raise ValueError('출발일을 YYYY-M-D 또는 YYYY-MM-DD 형식으로 입력하세요.')
        try:
            result = date(*(int(part) for part in match.groups()))
        except ValueError:
            raise ValueError('출발일이 유효한 날짜가 아닙니다.') from None
    if not 2000 <= result.year <= 2100:
        raise ValueError('출발일은 2000~2100년 범위로 입력하세요.')
    return result


def _clock(value, column):
    """Accept HHMM, Excel time cells and HH:MM, with explicit STA day rollover."""
    if isinstance(value, float) and isfinite(value):
        if 0 < value < 1 and abs(value*1440-round(value*1440)) < 1e-7:
            minutes = round(value*1440)
            value = f'{minutes//60:02d}{minutes%60:02d}'
        elif value.is_integer() and 0 <= value <= 2359:
            value = f'{int(value):04d}'
    pattern = r'([0-9]{2}):?([0-9]{2})(?::00)?(\+1)?'
    match = re.fullmatch(pattern, value) if isinstance(value, str) else None
    if not match:
        raise ValueError(f'{column}는 HHMM 형식으로 입력하세요.' + (' 다음 날 도착은 0050+1처럼 입력하세요.' if column == 'STA' else ''))
    hour, minute = map(int, match.groups()[:2])
    next_day = bool(match[3])
    if hour > 23 or minute > 59 or (next_day and column == 'STD'):
        raise ValueError(f'{column} 시각 또는 +1 표기가 올바르지 않습니다.')
    return time(hour, minute), int(next_day)


def _parse_rows(sheet, strings, epoch):
    rows, errors = [], []
    has_header = False
    for row in sheet.findall(f'{_NS}sheetData/{_NS}row'):
        row_number = row.get('r', '')
        if not re.fullmatch(r'[1-9][0-9]{0,6}', row_number):
            raise ValueError('Schedule 시트의 행 정보를 읽을 수 없습니다.')
        number = int(row_number)
        cells = {c.get('r'): c for c in row.findall(_NS+'c')}
        fields = [cells.get(f'{col}{number}') for col in 'ABCDEF']
        try:
            if any(c is not None and c.find(_NS+'f') is not None for c in fields):
                raise ValueError('입력 칸에 수식 대신 값을 붙여넣으세요.')
            values = tuple(_value(c, strings) if c is not None else '' for c in fields)
            if number == 1:
                has_header = values == HEADERS
                if not has_header:
                    break
                continue
            if not any(v != '' for v in values):
                continue
            if not 2 <= number <= MAX_ROWS+1:
                raise ValueError(f'운항편은 {MAX_ROWS:,}행까지 입력할 수 있습니다.')
            departure, flight, origin, dest, std, sta = values
            day = _date(departure, epoch)
            flight, origin, dest = (str(v).upper() for v in (flight, origin, dest))
            if not _FLIGHT.fullmatch(flight):
                raise ValueError('항공편명을 ZE101 또는 ESR101과 같은 형식으로 입력하세요.')
            if not all(_AIRPORT.fullmatch(v) for v in (origin, dest)):
                raise ValueError('출발지와 도착지에 공항 IATA 3자리 또는 ICAO 4자리 코드를 입력하세요.')
            std_time, _ = _clock(std, 'STD')
            sta_time, days = _clock(sta, 'STA')
            std = datetime.combine(day, std_time, KST)
            sta = datetime.combine(day+timedelta(days=days), sta_time, KST)
            if sta < std:
                raise ValueError('STA가 STD보다 이릅니다. 다음 날 도착이면 STA에 +1을 붙이세요.')
            rows.append(ScheduleRow(number, flight, origin, dest, std, sta))
        except ValueError as exc:
            errors.append(f'{number}행: {exc}')
            if len(errors) == 8:
                break
    if errors:
        raise ValueError(' / '.join(errors))
    if not has_header:
        raise ValueError('첫 행의 열 이름과 순서를 확인하세요: ' + ', '.join(HEADERS))
    if not rows:
        raise ValueError('Schedule 시트에 운항편을 한 행 이상 입력하세요.')
    return tuple(rows)


def read_schedule(data: bytes) -> tuple[ScheduleRow, ...]:
    if len(data) > MAX_UPLOAD_MB*1024**2:
        raise ValueError(f'엑셀 파일은 {MAX_UPLOAD_MB}MB까지 업로드할 수 있습니다.')
    try:
        with ZipFile(BytesIO(data)) as book:
            entries = book.infolist()
            if len(entries) > 200 or sum(e.file_size for e in entries) > 24*1024**2:
                raise ValueError('엑셀 파일의 압축 해제 크기 또는 구성 항목이 제한을 초과합니다.')
            if any('vbaproject' in e.filename.lower() for e in entries):
                raise ValueError('매크로 없는 .xlsx 파일을 사용하세요.')
            workbook = _xml(book, 'xl/workbook.xml')
            props = workbook.find(_NS+'workbookPr')
            epoch = date(1904, 1, 1) if props is not None and props.get('date1904') in ('1', 'true') else date(1899, 12, 30)
            strings = []
            if 'xl/sharedStrings.xml' in book.namelist():
                strings = [''.join(t.text or '' for t in s.iter(_NS+'t')).strip()
                           for s in _xml(book, 'xl/sharedStrings.xml').findall(_NS+'si')]
            return _parse_rows(_sheet(book, workbook), strings, epoch)
    except (BadZipFile, ET.ParseError, UnicodeError, KeyError, IndexError, RuntimeError, NotImplementedError, OSError) as exc:
        raise ValueError('엑셀 파일을 읽을 수 없습니다. 다운로드한 .xlsx 양식을 사용하세요.') from exc
