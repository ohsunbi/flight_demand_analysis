"""Complete date/direction snapshots and local airline selection."""
import re
from dataclasses import replace

from adapters.ubikais_client import CollectionError, check_cancel
from config import MAX_QUERY_TASKS
from normalization.flights import parse_datetime
from services.planner import Task, plan


_FLIGHT_ID = re.compile(r'([A-Z]{3})[0-9]+[A-Z]?')


def _validate_query_date(batch, contract):
    if not contract.query_date_verified:
        return
    dkey, tkey = ('schDate', 'schTime') if batch.direction == 'dep' else ('staDate', 'sta')
    for record in batch.records:
        dt = parse_datetime(record.get(dkey), record.get(tkey))
        if dt and (dt.date()-batch.query_date).days not in (0, 1):
            raise CollectionError('원본 조회일과 예정일의 차이가 검증 범위를 벗어났습니다. 조회 날짜 규칙을 다시 확인해야 합니다.')


def collect(settings, client, contract, *, refresh=False, cancel=None, progress=None, context=None):
    padding = contract.actual_query_padding_days if settings.basis == 'actual' else 0
    tasks = plan(settings, actual_query_padding_days=padding or 0)
    total, completed = len(tasks), 0
    batches = []
    unclassifiable_rows = 0

    def fetch(task):
        nonlocal completed
        check_cancel(cancel)
        if completed >= MAX_QUERY_TASKS:
            raise CollectionError('원본 조회 단위가 운영 제한을 초과했습니다.')
        if progress:
            direction = '출발' if task.direction == 'dep' else '도착'
            progress(completed, total, f'{task.day} {direction} 데이터 수집 중')
        batch = client.fetch(settings.airport, task, refresh=refresh, cancel=cancel)
        completed += 1
        check_cancel(cancel)
        _validate_query_date(batch, contract)
        return batch

    for task in tasks:
        snapshot = fetch(task)
        if context is not None:
            context.append(snapshot)
        if not settings.airlines:
            batches.append(snapshot)
            continue
        selected = {code: [] for code in settings.airlines}
        for record in snapshot.records:
            check_cancel(cancel)
            match = _FLIGHT_ID.fullmatch(str(record.get('fpId') or '').strip().upper())
            if match is None:
                unclassifiable_rows += 1
                continue
            if match.group(1) in selected:
                selected[match.group(1)].append(record)
        # These labels identify the local selection, not additional HTTP requests.
        batches.extend(replace(snapshot, airline=code, records=tuple(selected[code]))
                       for code in settings.airlines)

    check_cancel(cancel)
    return tuple(batches), completed, unclassifiable_rows
