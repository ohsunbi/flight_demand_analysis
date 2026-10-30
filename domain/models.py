from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from config import AIRPORTS, MAX_ANALYSIS_DAYS, MAX_OFFSET_MINUTES

KST = ZoneInfo('Asia/Seoul')
Direction = Literal['dep', 'arr']


@dataclass(frozen=True)
class Offsets:
    start: int
    end: int
    reusable: int

    def validate(self, *, active=True):
        if any(type(v) is not int for v in asdict(self).values()):
            raise ValueError('조업 오프셋은 정수 분으로 입력하세요.')
        if any(abs(v) > MAX_OFFSET_MINUTES for v in (self.start, self.end)) or not 0 <= self.reusable-self.end <= 2*MAX_OFFSET_MINUTES:
            raise ValueError('조업 시간 입력이 허용 범위를 벗어났습니다.')
        if active and not self.start <= self.end <= self.reusable:
            raise ValueError('조업 시작 ≤ 조업 종료 ≤ 재투입 가능 순서여야 합니다.')
        if active and abs(self.reusable) > MAX_OFFSET_MINUTES:
            raise ValueError('조업 오프셋은 ±7일 이내 정수 분으로 입력하세요.')


@dataclass(frozen=True)
class Settings:
    airport: str
    start: date
    end: date
    mode: str = 'month'
    airlines: tuple[str, ...] = ()  # Empty means a genuinely unfiltered request.
    basis: str = 'scheduled'
    day_start: int = 0
    interval: int = 60
    dep: Offsets = field(default_factory=lambda: Offsets(-50, 10, 20))
    arr: Offsets = field(default_factory=lambda: Offsets(-20, 30, 40))
    directions: tuple[Direction, ...] = ('dep', 'arr')
    quick_turn: bool = False
    turn_limit: int = 100

    def validate(self):
        if self.airport not in AIRPORTS:
            raise ValueError('지원 목록에서 공항을 선택하세요.')
        if not 2000 <= self.start.year <= self.end.year <= 2100:
            raise ValueError('분석 연도는 2000~2100년 범위로 선택하세요.')
        if not 1 <= self.days <= MAX_ANALYSIS_DAYS:
            raise ValueError('분석 기간은 시작일·종료일을 포함해 1~31일이어야 합니다.')
        if self.mode not in ('month', 'custom') or self.basis not in ('scheduled', 'actual'):
            raise ValueError('조회 방식 또는 시간 기준이 잘못되었습니다.')
        if self.mode == 'month':
            import calendar
            if self.start.day != 1 or self.end != date(self.start.year, self.start.month, calendar.monthrange(self.start.year, self.start.month)[1]):
                raise ValueError('월별 모드는 해당 월의 전체 날짜를 포함해야 합니다.')
        if type(self.day_start) is not int or not 0 <= self.day_start < 1440 or self.interval not in (30, 60):
            raise ValueError('운영일 시작 또는 셀 간격이 잘못되었습니다.')
        if len(self.airlines) > 30 or len(set(self.airlines)) != len(self.airlines):
            raise ValueError('항공사는 중복 없이 최대 30개를 선택하세요.')
        if any(not re.fullmatch(r'[A-Z]{3}', code) for code in self.airlines):
            raise ValueError('항공사 코드는 영문 대문자 3자리로 입력하세요.')
        if self.directions not in (('dep',), ('arr',), ('dep', 'arr')):
            raise ValueError('출발편 또는 도착편을 하나 이상 선택하세요.')
        self.dep.validate(active='dep' in self.directions)
        self.arr.validate(active='arr' in self.directions)
        if type(self.quick_turn) is not bool or type(self.turn_limit) is not int or not 1 <= self.turn_limit <= 360:
            raise ValueError('퀵턴 제한시간은 1~360분의 정수로 입력하세요.')

    @property
    def quick_turn_active(self):
        return self.quick_turn and self.basis == 'actual' and self.directions == ('dep', 'arr')

    @property
    def direction_label(self):
        return '·'.join(name for code, name in (('dep', '출발편'), ('arr', '도착편')) if code in self.directions)

    @property
    def days(self):
        return (self.end - self.start).days + 1

    @property
    def window(self):
        a = datetime.combine(self.start, time(), KST) + timedelta(minutes=self.day_start)
        return a, a + timedelta(days=self.days)

    @property
    def signature(self):
        return hashlib.sha256(json.dumps(asdict(self), default=str, sort_keys=True).encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Contract:
    """Only evidence-backed mappings belong here. Default live contract is unverified."""
    timezone_verified: bool = False
    query_date_verified: bool = False
    airline_prefix_verified: bool = False
    cancelled_statuses: tuple[str, ...] = ()
    known_statuses: tuple[str, ...] = ('DEP', 'ARR', 'DLA')
    actual_same_day_verified: bool = False
    evidence: str = ''
    actual_query_padding_days: int | None = None
    actual_date_policy: str = 'explicit_only'

    @property
    def verified(self):
        return self.timezone_verified and self.query_date_verified and bool(self.cancelled_statuses)


@dataclass(frozen=True)
class Flight:
    key: str
    direction: Direction
    flight_id: str
    airport: str
    route: str
    scheduled: datetime | None
    actual: datetime | None
    reference: datetime
    reference_source: str
    queried_dates: tuple[date, ...]
    query_airlines: tuple[str, ...]
    status: str
    raw_dates: tuple[str, str]
    start: datetime
    end: datetime
    reusable: datetime
    warnings: tuple[str, ...] = ()
    flight_pk: str = ''
    source_metadata: tuple[tuple[str, str], ...] = ()
    actual_clock: str = ''
    registration: str = ''
    spot: str = ''


@dataclass(frozen=True)
class Movement:
    key: str
    airport: str
    direction: Direction
    registration: str
    spot: str
    time: datetime
    actual: bool


@dataclass(frozen=True)
class HandlingJob:
    key: str
    kind: str
    flights: tuple[Flight, ...]
    start: datetime
    end: datetime
    reusable: datetime
    note: str = ''


@dataclass(frozen=True)
class Segment:
    start: datetime
    end: datetime
    dep: int
    arr: int
    turn: int = 0

    @property
    def total(self):
        return self.dep + self.arr + self.turn


@dataclass(frozen=True)
class Cell:
    index: int
    operating_day: date
    start: datetime
    end: datetime
    maximum: int
    peak: datetime | None
    dep_active: int
    arr_active: int
    dep_count: int
    arr_count: int
    peak_intervals: tuple[tuple[datetime, datetime], ...]
    turn_active: int = 0


@dataclass
class Diagnostics:
    raw: int = 0
    duplicates: int = 0
    cancelled: int = 0
    quarantined: int = 0
    conflicts: int = 0
    zero_length: int = 0
    actual_used: int = 0
    scheduled_used: int = 0
    date_unresolved: int = 0
    actual_date_inferred: int = 0
    unknown_status: int = 0
    quick_turn_pairs: int = 0
    quick_turn_unpaired: int = 0
    messages: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Batch:
    query_date: date
    direction: Direction
    airline: str
    records: tuple[dict, ...]
    fetched_at: datetime
    cached: bool = False


@dataclass
class Analysis:
    settings: Settings
    flights: tuple[Flight, ...]
    segments: tuple[Segment, ...]
    cells: tuple[Cell, ...]
    daily_max: tuple[int, ...]
    histogram_minutes: dict[int, float]
    daily_crew_minutes: tuple[float, ...]
    diagnostics: Diagnostics
    collected_from: datetime
    collected_until: datetime
    created_at: datetime
    result_id: str
    exportable: bool
    blockers: tuple[str, ...] = ()
    synthetic: bool = False
    data_version: str = ''
    jobs: tuple[HandlingJob, ...] = ()

    @property
    def maximum(self):
        return max(self.daily_max, default=0)

    @property
    def peak_cell(self):
        return next((c for c in self.cells if c.maximum == self.maximum and c.peak is not None), None)

