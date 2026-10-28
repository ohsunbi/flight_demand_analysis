"""Pure event sweep; no UI, plotting, network, or cache dependencies."""
from bisect import bisect_left
from collections import defaultdict
from datetime import timedelta
from uuid import uuid4

from domain.models import Analysis, Cell, Diagnostics, Flight, Segment, Settings, KST


def analyze(settings: Settings, flights: tuple[Flight, ...], diagnostics: Diagnostics,
            collected_from, collected_until, *, blockers=(), synthetic=False) -> Analysis:
    settings.validate()
    a, b = settings.window
    events = defaultdict(lambda: [0, 0])
    events[a]; events[b]
    relevant = []
    for f in flights:
        if not (a <= f.reference < b or (f.start < b and f.reusable > a and f.start < f.reusable)):
            continue
        relevant.append(f)
        if f.start >= f.reusable or f.start >= b or f.reusable <= a:
            continue
        slot = 0 if f.direction == 'dep' else 1
        events[max(f.start, a)][slot] += 1
        events[min(f.reusable, b)][slot] -= 1

    # Cell boundaries allow one linear pass over both timeline and cell aggregates.
    width = timedelta(minutes=settings.interval)
    boundaries = [a + i * width for i in range(settings.days * 1440 // settings.interval + 1)]
    for t in boundaries:
        events[t]
    times = sorted(events)
    dep = arr = 0
    segments = []
    for t, end in zip(times, times[1:]):
        dd, da = events[t]
        dep += dd; arr += da
        if dep < 0 or arr < 0:
            raise AssertionError('Negative occupancy')
        if end > t:
            segments.append(Segment(t, end, dep, arr))

    scheduled = {d: sorted(f.reference for f in relevant if f.direction == d) for d in ('dep', 'arr')}
    cells = []
    hist = defaultdict(float)
    daily_minutes = [0.0] * settings.days
    cursor = 0
    for i, (start, end) in enumerate(zip(boundaries, boundaries[1:])):
        maximum = 0; peak = None; peak_dep = peak_arr = 0; ties = []
        while cursor < len(segments) and segments[cursor].start < end:
            s = segments[cursor]
            minutes = (s.end - s.start).total_seconds() / 60
            hist[s.total] += minutes
            daily_minutes[i // (1440 // settings.interval)] += s.total * minutes
            if s.total > maximum:
                maximum = s.total; peak = s.start; peak_dep = s.dep; peak_arr = s.arr
                ties = [(s.start, s.end)]
            elif s.total == maximum and maximum > 0:
                if ties and ties[-1][1] == s.start:
                    ties[-1] = (ties[-1][0], s.end)
                else:
                    ties.append((s.start, s.end))
            cursor += 1
        counts = [bisect_left(scheduled[d], end) - bisect_left(scheduled[d], start) for d in ('dep', 'arr')]
        day = settings.start + timedelta(days=i // (1440 // settings.interval))
        cells.append(Cell(i, day, start, end, maximum, peak, peak_dep, peak_arr, *counts, tuple(ties)))
    per_day = 1440 // settings.interval
    daily = tuple(max(c.maximum for c in cells[i:i+per_day]) for i in range(0, len(cells), per_day))
    # Compact sweep output independently of display grid boundaries.
    compact = []
    for s in segments:
        if compact and (compact[-1].dep, compact[-1].arr, compact[-1].end) == (s.dep, s.arr, s.start):
            old = compact.pop(); compact.append(Segment(old.start, s.end, s.dep, s.arr))
        else:
            compact.append(s)
    from datetime import datetime
    return Analysis(settings, tuple(relevant), tuple(compact), tuple(cells), daily,
                    dict(sorted(hist.items())), tuple(daily_minutes), diagnostics,
                    collected_from, collected_until, datetime.now(KST), uuid4().hex[:12],
                    not blockers, tuple(blockers), synthetic)


def half_day_peaks(result: Analysis):
    """Return AM/PM maxima and tied calendar dates, split at KST noon/midnight."""
    maxima = [0, 0]
    dates = [set(), set()]
    for segment in result.segments:
        cursor = segment.start.astimezone(KST)
        end = segment.end.astimezone(KST)
        while cursor < end:
            half = int(cursor.hour >= 12)
            boundary = cursor.replace(hour=12 if half == 0 else 0, minute=0, second=0, microsecond=0)
            if half:
                boundary += timedelta(days=1)
            if segment.total > maxima[half]:
                maxima[half] = segment.total
                dates[half] = {cursor.date()}
            elif segment.total == maxima[half] and segment.total > 0:
                dates[half].add(cursor.date())
            cursor = min(end, boundary)
    return tuple((maximum, tuple(sorted(days))) for maximum, days in zip(maxima, dates))


def cell_flights(result: Analysis, index: int, kind: str):
    cell = result.cells[index]
    if kind == 'peak':
        return tuple(f for f in result.flights if cell.peak is not None and f.start <= cell.peak < f.reusable)
    if kind == 'overlap':
        return tuple(f for f in result.flights if f.start < cell.end and f.reusable > cell.start and f.start < f.reusable)
    if kind == 'work':
        return tuple(f for f in result.flights if f.start < cell.end and f.end > cell.start and f.start < f.end)
    if kind == 'reference':
        return tuple(f for f in result.flights if cell.start <= f.reference < cell.end)
    raise ValueError('Unknown detail kind')

