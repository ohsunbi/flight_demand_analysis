from datetime import date
from html import unescape
import re

from ui.summary import occurrence_dates


def test_occurrences_group_months_and_keep_calendar_weekdays():
    text=occurrence_dates([date(2026,11,2),date(2026,10,30),date(2026,11,1)])
    assert text.count('10월')==1 and text.count('11월')==1
    plain=unescape(re.sub('<[^>]+>','',text))
    assert plain.index('30(금)') < plain.index('1(일)') < plain.index('2(월)')
    assert '10/30' not in text


def test_occurrences_disambiguate_year_boundary():
    text=occurrence_dates([date(2026,12,31),date(2027,1,1)])
    assert '2026년 12월' in text and '2027년 1월' in text
    plain=unescape(re.sub('<[^>]+>','',text))
    assert '31(목)' in plain and '1(금)' in plain


def test_no_occurrences_has_no_month_or_weekday():
    assert '없음' in occurrence_dates([])
    assert 'summary-month-row' not in occurrence_dates([])
