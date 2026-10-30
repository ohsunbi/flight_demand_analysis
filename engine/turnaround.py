"""Deterministic one-to-one turns from airport/registration chronology. No I/O."""
from collections import defaultdict
from bisect import bisect_left
from datetime import timedelta

from domain.models import HandlingJob, Movement


def individual(flight, note=''):
    return HandlingJob(flight.key, flight.direction, (flight,), flight.start,
                       flight.end, flight.reusable, note)


def build_jobs(settings, flights, *, context=(), check=None):
    if not settings.quick_turn_active:
        return tuple(individual(f) for f in flights)
    selected = {f.key: f for f in flights}
    versions = defaultdict(set)
    for movement in context:
        versions[movement.key].add(movement)
    notes = {}
    for f in flights:
        if check:
            check()
        actual = f.actual is not None and f.reference_source in ('actual', 'actual_inferred')
        if not actual:
            notes[f.key] = 'RAMP 없음 · 예정시각 대체'
        elif not f.registration or not f.spot:
            notes[f.key] = 'REG 또는 SPOT 누락'
        if f.registration:
            versions[f.key].add(Movement(f.key, f.airport, f.direction, f.registration,
                                         f.spot, f.actual if actual else f.reference, actual))
    conflicts = {key for key, values in versions.items() if len(values) > 1}
    groups = defaultdict(list)
    for values in versions.values():
        for m in values:
            groups[m.airport, m.registration].append(m)
    paired = set()
    jobs = []
    for group in groups.values():
        if check:
            check()
        group.sort(key=lambda m: (m.time, m.key, m.direction, m.spot))
        times = defaultdict(int)
        for m in group:
            times[m.time] += 1
        uncertain = sorted((m.time-timedelta(hours=3), m.time+timedelta(hours=21)) for m in group if not m.actual)
        starts = [a for a, _ in uncertain]
        ends = []
        for _, end in uncertain:
            ends.append(max(end, ends[-1]) if ends else end)
        for index, (arrival, departure) in enumerate(zip(group, group[1:])):
            if arrival.direction != 'arr' or departure.direction != 'dep':
                continue
            keys = (arrival.key, departure.key)
            reason = None
            uncertain_index = bisect_left(starts, departure.time)-1
            if any(key in conflicts for key in keys) or times[arrival.time] > 1 or times[departure.time] > 1:
                reason = '운항 순서 또는 중복 후보가 불명확'
            elif (index > 0 and group[index-1].direction == 'arr'
                  and arrival.time-group[index-1].time <= timedelta(minutes=settings.turn_limit)) or (
                  index+2 < len(group) and group[index+2].direction == 'dep'
                  and group[index+2].time-departure.time <= timedelta(minutes=settings.turn_limit)):
                reason = '연속된 동방향 운항으로 연결 후보가 불명확'
            elif any(key in notes for key in keys):
                reason = '선택 편의 REG·SPOT 또는 RAMP 부족'
            elif uncertain_index >= 0 and ends[uncertain_index] > arrival.time:
                reason = 'RAMP 미확정 중간 운항 가능성 있음'
            elif not arrival.actual or not departure.actual:
                reason = 'RAMP 미확정 운항기록 있음'
            elif any(key not in selected for key in keys):
                reason = '상대편이 분석 대상 아님'
            elif not arrival.spot or not departure.spot:
                reason = 'REG 또는 SPOT 누락'
            elif arrival.spot != departure.spot:
                reason = 'SPOT 불일치'
            elif not timedelta(0) < departure.time-arrival.time <= timedelta(minutes=settings.turn_limit):
                reason = '제한시간 초과 또는 시각 순서 불일치'
            if reason:
                for key in keys:
                    if key in selected:
                        notes.setdefault(key, reason)
                continue
            if any(key in paired for key in keys):
                continue
            arr, dep = (selected[key] for key in keys)
            end = max(arr.end, dep.end)
            jobs.append(HandlingJob('turn:'+arr.key+':'+dep.key, 'turn', (arr, dep),
                                    min(arr.start, dep.start), end,
                                    end+timedelta(minutes=settings.dep.reusable-settings.dep.end),
                                    'REG·SPOT 일치 · 연속 도착→출발'))
            paired.update(keys)
    jobs.extend(individual(f, notes.get(f.key, '명확한 연결 상대편 없음'))
                for f in flights if f.key not in paired)
    return tuple(sorted(jobs, key=lambda job: (job.start, job.key)))
