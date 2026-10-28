from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_ANALYSIS_DAYS = 31
MAX_QUERY_DAYS = 100
MAX_QUERY_TASKS = 400
MAX_PAGES = 200
MAX_OFFSET_MINUTES = 7 * 24 * 60
AIRPORTS = {
    'RKSI': ('인천', 'ICN'), 'RKSS': ('김포', 'GMP'), 'RKTU': ('청주', 'CJJ'),
    'RKNY': ('양양', 'YNY'), 'RKJK': ('군산', 'KUV'), 'RKNW': ('원주', 'WJU'),
    'RKPC': ('제주', 'CJU'), 'RKPK': ('김해', 'PUS'), 'RKTN': ('대구', 'TAE'),
    'RKJJ': ('광주', 'KWJ'), 'RKJY': ('여수', 'RSU'), 'RKPU': ('울산', 'USN'),
    'RKTH': ('포항', 'KPO'), 'RKPS': ('사천', 'HIN'), 'RKJB': ('무안', 'MWX'),
    'RKTL': ('울진', ''),
}
PALETTE = ['#f3f4f6', '#c9ead6', '#75c69a', '#f5df88', '#f8b375', '#e66b55', '#a92727']
PALETTE_TEXT = ['#242424'] * 6 + ['#ffffff']


def color_index(value, maximum):
    if value == 0:
        return 0
    if maximum <= 1:
        return len(PALETTE) - 1
    return min(len(PALETTE)-1, 1 + (value-1)*(len(PALETTE)-2)//(maximum-1))


def legend_ranges(maximum):
    groups = {}
    for value in range(maximum + 1):
        groups.setdefault(color_index(value, maximum), []).append(value)
    return [(PALETTE[i], str(v[0]) if v[0] == v[-1] else f'{v[0]}~{v[-1]}') for i,v in groups.items()]

