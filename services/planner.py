from dataclasses import dataclass
from datetime import date, timedelta

from config import MAX_QUERY_DAYS, MAX_QUERY_TASKS
from domain.models import Settings


@dataclass(frozen=True)
class Task:
    day: date
    direction: str
    airline: str = ''


def plan(settings: Settings, *, actual_query_padding_days=0) -> tuple[Task, ...]:
    settings.validate()
    if type(actual_query_padding_days) is not int or not 0 <= actual_query_padding_days <= 31:
        raise ValueError('검증된 실제일자 보충 범위가 잘못되었습니다.')
    a, b = settings.window
    tasks = []
    for direction, offsets in [('dep', settings.dep), ('arr', settings.arr)]:
        lo = min(a, a - timedelta(minutes=offsets.reusable))
        hi = max(b, b - timedelta(minutes=offsets.start))
        # Broad calendar coverage is deliberately followed by exact datetime filtering.
        # Observed provider contract: a query can include the following scheduled day.
        # Include previous query day even for zero-length / all-zero offsets.
        first = lo.date() - timedelta(days=1 + actual_query_padding_days)
        last = (hi - timedelta(microseconds=1)).date() + timedelta(days=actual_query_padding_days)
        count = (last - first).days + 1
        if count > MAX_QUERY_DAYS:
            raise ValueError('조업 설정에 필요한 보충 조회 날짜가 너무 많습니다.')
        for i in range(count):
            for airline in settings.airlines or ('',):
                tasks.append(Task(first + timedelta(days=i), direction, airline))
    # Selected-airline queries use the provider's filter, never an inferred operator.
    if len(tasks) > MAX_QUERY_TASKS:
        raise ValueError('요청 계획이 운영 제한을 초과했습니다.')
    return tuple(tasks)
