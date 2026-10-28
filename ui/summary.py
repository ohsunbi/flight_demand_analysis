"""Compact calendar-date labels for the on-screen summary cards."""
from itertools import groupby


def occurrence_dates(dates):
    days=sorted(set(dates))
    if not days:
        content='없음'
    else:
        weekdays=('월','화','수','목','금','토','일')
        show_year=days[0].year != days[-1].year
        rows=[]
        for (year,month), values in groupby(days,key=lambda d:(d.year,d.month)):
            month_label=f'{year}년 {month}월' if show_year else f'{month}월'
            labels=', '.join(f'<span class="summary-day">{d.day}<span class="summary-weekday">({weekdays[d.weekday()]})</span></span>' for d in values)
            rows.append(f'<div class="summary-month-row"><span class="summary-month">{month_label}</span><span>{labels}</span></div>')
        content=''.join(rows)
    return f'<div class="summary-dates"><span class="summary-date-label">발생일 |</span><div>{content}</div></div>'
