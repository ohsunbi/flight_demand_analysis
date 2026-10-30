from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta

from domain.models import Batch, Contract, Diagnostics, Flight, KST, Settings


def parse_datetime(raw_date, raw_time):
    d, t = str(raw_date or '').strip(), str(raw_time or '').strip()
    if not re.fullmatch(r'\d{8}', d) or not re.fullmatch(r'\d{4}', t):
        return None
    try:
        return datetime.strptime(d + t, '%Y%m%d%H%M').replace(tzinfo=KST)
    except ValueError:
        return None


def actual_datetime(record, direction, scheduled, contract):
    stem = 'blockOff' if direction == 'dep' else 'blockOn'
    value = str(record.get(stem + 'Time') or '').strip()
    if not value:
        return None, None
    if re.fullmatch(r'\d{12}', value):
        actual = parse_datetime(value[:8], value[8:])
        return actual, None if actual else '주기장 실제시각 형식 오류'
    explicit = parse_datetime(record.get(stem + 'Date'), value)
    if explicit:
        return explicit, None
    if record.get(stem + 'Date'):
        return None, '주기장 실제날짜 형식 오류'
    if re.fullmatch(r'\d{4}', value) and parse_datetime('20000101', value) is None:
        return None, '주기장 실제시각 형식 오류'
    if re.fullmatch(r'\d{4}', value) and scheduled and contract.actual_date_policy == 'nearest_scheduled':
        candidates = [parse_datetime((scheduled + timedelta(days=delta)).strftime('%Y%m%d'), value) for delta in (-1,0,1)]
        candidates = [c for c in candidates if c is not None]
        if candidates:
            # The user-approved model assumption, not a verified date from the provider.
            actual = min(candidates, key=lambda c: (abs((c-scheduled).total_seconds()), abs((c.date()-scheduled.date()).days), c))
            return actual, '실제 날짜 추정 (예정시각에 가장 가까운 날짜)'
    if re.fullmatch(r'\d{4}', value) and contract.actual_same_day_verified and scheduled:
        actual = parse_datetime(scheduled.strftime('%Y%m%d'), value)
        return actual, None if actual else '주기장 실제시각 형식 오류'
    # Never infer the day from the nearest clock time: delays can exceed a day.
    return None, '주기장 실제일자 미확인' if re.fullmatch(r'\d{4}', value) else '주기장 실제시각 형식 오류'


def normalize(batches: tuple[Batch, ...], settings: Settings, contract: Contract):
    diag = Diagnostics()
    groups = defaultdict(list)
    for batch in batches:
        if batch.direction not in settings.directions:
            continue
        for raw in batch.records:
            diag.raw += 1
            date_key = 'schDate' if batch.direction == 'dep' else 'staDate'
            pk = str(raw.get('flightPk') or '')
            if not pk:
                diag.quarantined += 1
                continue
            groups[(batch.direction, pk, str(raw.get(date_key) or ''))].append((raw, batch))
    flights = []
    for (direction, pk, _), entries in groups.items():
        hashes = defaultdict(list)
        for raw, batch in entries:
            canonical = json.dumps(raw, sort_keys=True, ensure_ascii=False, default=str)
            hashes[canonical].append((raw, batch))
        diag.duplicates += len(entries) - len(hashes)
        if len(hashes) > 1:
            diag.conflicts += 1
            diag.quarantined += 1
            continue
        raw, batch = entries[0]
        status = str(raw.get('depStatus' if direction == 'dep' else 'arrStatus') or '').strip().upper()
        if status and status in contract.cancelled_statuses:
            diag.cancelled += 1
            continue
        warnings = []
        if status and status not in contract.known_statuses:
            diag.unknown_status += 1
            warnings.append('상태 의미 미확인: ' + status[:12])
        date_key, time_key = ('schDate', 'schTime') if direction == 'dep' else ('staDate', 'sta')
        scheduled = parse_datetime(raw.get(date_key), raw.get(time_key))
        actual, warning = actual_datetime(raw, direction, scheduled, contract)
        if warning:
            warnings.append(warning)
            if warning == '주기장 실제일자 미확인':
                diag.date_unresolved += 1
        reference = actual if settings.basis == 'actual' and actual else scheduled
        if reference is None:
            diag.quarantined += 1
            continue
        flight_id = str(raw.get('fpId') or '').strip().upper()
        if settings.airlines:
            selected_queries = {b.airline for _, b in entries if b.airline}
            if not selected_queries.intersection(settings.airlines):
                continue
        source = ('actual_inferred' if warning and warning.startswith('실제 날짜 추정') else 'actual') if settings.basis == 'actual' and actual else ('fallback' if settings.basis == 'actual' else 'scheduled')
        offsets = settings.dep if direction == 'dep' else settings.arr
        start = reference + timedelta(minutes=offsets.start)
        end = reference + timedelta(minutes=offsets.end)
        reusable = reference + timedelta(minutes=offsets.reusable)
        if start == reusable:
            diag.zero_length += 1
        stable = '|'.join([settings.airport, direction, pk, str(raw.get(date_key))])
        key = hashlib.sha256(stable.encode()).hexdigest()[:20]
        flights.append(Flight(key, direction, flight_id, settings.airport,
                              str(raw.get('apArr' if direction == 'dep' else 'apIcao') or ''),
                              scheduled, actual, reference, source,
                              tuple(sorted({b.query_date for _, b in entries})),
                              tuple(sorted({b.airline for _, b in entries if b.airline})), status,
                              (str(raw.get(date_key) or ''), str(raw.get(time_key) or '')),
                              start, end, reusable, tuple(warnings), flight_pk=pk,
                              source_metadata=tuple((k, str(raw.get(k) or '')) for k in ['amsRecPk','amsRecPkCha','chaYn']),
                              actual_clock=str(raw.get('blockOffTime' if direction == 'dep' else 'blockOnTime') or '')))
    if diag.quarantined:
        diag.messages.append(f'식별자·시각 결측 또는 충돌로 {diag.quarantined}건 격리했습니다.')
    if diag.date_unresolved:
        diag.messages.append(f'주기장 시각에 날짜가 없어 {diag.date_unresolved}건은 실제일자를 확정할 수 없습니다.')
    if diag.unknown_status:
        diag.messages.append(f'의미를 확인하지 못한 상태가 {diag.unknown_status}건 있습니다.')
    return tuple(sorted(flights, key=lambda f: (f.reference, f.key))), diag

