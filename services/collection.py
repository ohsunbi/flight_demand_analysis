"""Complete date/direction snapshots, local airline selection and bounded fallback."""
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


def collect(settings, client, contract, *, refresh=False, cancel=None, progress=None):
    padding = contract.actual_query_padding_days if settings.basis == 'actual' else 0
    tasks = plan(settings, actual_query_padding_days=padding or 0)
    total, completed = len(tasks), 0
    batches = []
    fallback_groups = 0

    def fetch(task):
        nonlocal completed
        check_cancel(cancel)
        if completed >= MAX_QUERY_TASKS:
            raise CollectionError('원본 조회 단위가 운영 제한을 초과했습니다.')
        if progress:
            scope = task.airline or '전체'
            progress(completed, total, f'{task.day} {"출발" if task.direction == "dep" else "도착"} {scope} 수집')
        batch = client.fetch(settings.airport, task, refresh=refresh, cancel=cancel)
        completed += 1
        check_cancel(cancel)
        _validate_query_date(batch, contract)
        return batch

    for task in tasks:
        snapshot = fetch(task)
        if not settings.airlines:
            batches.append(snapshot)
            continue
        selected = {code: [] for code in settings.airlines}
        for record in snapshot.records:
            check_cancel(cancel)
            match = _FLIGHT_ID.fullmatch(str(record.get('fpId') or '').strip().upper())
            if match is None:
                break
            if match.group(1) in selected:
                selected[match.group(1)].append(record)
        else:
            # These batch labels identify the selection, not additional HTTP requests.
            batches.extend(replace(snapshot, airline=code, records=tuple(selected[code]))
                           for code in settings.airlines)
            continue

        # A missing/nonstandard identifier cannot safely be excluded. Re-query every
        # selected airline for this complete group; never mix partial local selection.
        total += len(settings.airlines)
        if total > MAX_QUERY_TASKS:
            raise CollectionError('항공사 개별 대조에 필요한 조회 단위가 운영 제한을 초과했습니다.')
        fallback_groups += 1
        for code in settings.airlines:
            batches.append(fetch(Task(task.day, task.direction, code)))

    check_cancel(cancel)
    return tuple(batches), completed, fallback_groups
