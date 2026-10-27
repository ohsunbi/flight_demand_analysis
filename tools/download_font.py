"""Fetch unmodified redistributable Nanum Gothic and its SIL OFL license."""
from pathlib import Path
from urllib.request import urlopen

if __name__ == '__main__':
    target = Path(__file__).resolve().parents[1] / 'assets' / 'fonts'
    target.mkdir(parents=True, exist_ok=True)
    base = 'https://raw.githubusercontent.com/google/fonts/main/ofl/nanumgothic/'
    for name in ['NanumGothic-Regular.ttf', 'OFL.txt']:
        with urlopen(base + name, timeout=30) as response:
            data = response.read()
        (target / name).write_bytes(data)
        print(name, len(data))
