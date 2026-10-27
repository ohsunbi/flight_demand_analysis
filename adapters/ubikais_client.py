"""Independent urllib client, adapted from the read-only reference client.

Atomic completed-snapshot cache, bounded pagination/retry, shared request pacing.
No response body, server message, cookie, or request URL appears in exceptions.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from config import MAX_PAGES, ROOT
from domain.models import Batch, KST
from services.planner import Task

_NETWORK_LOCK = threading.Lock()
_LAST_REQUEST = 0.0


class CollectionError(RuntimeError):
    pass


class Cancelled(CollectionError):
    pass


def check_cancel(cancel):
    if cancel and cancel.is_set():
        raise Cancelled('조회가 중단되었습니다. 완료된 날짜의 캐시는 다음 조회에 재사용됩니다.')


def ttl_seconds(day, fetched_at, now):
    delta = (day - now.date()).days
    if delta in (0, 1):
        return 1800
    if delta >= 2:
        return 86400
    cutoff = datetime.combine(day + timedelta(days=1), datetime.min.time(), KST) + timedelta(hours=6)
    if now < cutoff:
        return 1800
    return 604800 if fetched_at >= cutoff else 0


class UbikaisClient:
    def __init__(self, *, cache_dir=None, cookie=None, opener=None, retries=2, pace=0.35, timeout=15):
        self.cache_dir = Path(cache_dir) if cache_dir is not None else ROOT / 'cache' / 'raw_v1'
        self.cookie = cookie
        self.opener = opener or urlopen
        self.retries, self.pace, self.timeout = retries, pace, timeout

    def _path(self, airport, task):
        digest = hashlib.sha256(json.dumps([airport, str(task.day), task.direction, task.airline, '', 1]).encode()).hexdigest()
        return self.cache_dir / (digest + '.json')

    def fetch(self, airport: str, task: Task, *, refresh=False, cancel=None):
        check_cancel(cancel)
        path = self._path(airport, task)
        now = datetime.now(KST)
        if not refresh:
            try:
                saved = json.loads(path.read_text(encoding='utf-8'))
                at = datetime.fromisoformat(saved['fetched_at']).astimezone(KST)
                if (saved.get('complete') is True and saved['total'] == len(saved['records'])
                        and all(isinstance(r, dict) for r in saved['records'])
                        and 0 <= (now-at).total_seconds() < ttl_seconds(task.day, at, now)):
                    return Batch(task.day, task.direction, task.airline, tuple(saved['records']), at, True)
            except (OSError, ValueError, KeyError, TypeError):
                pass
        records = []
        expected = None
        seen = set()
        for _ in range(MAX_PAGES):
            payload = self._page(airport, task, len(records), cancel)
            if payload.get('status') != 'success':
                raise CollectionError('UBIKAIS가 조회 성공을 반환하지 않았습니다.')
            page = payload.get('records')
            total = payload.get('total')
            if not isinstance(page, list) or any(not isinstance(r, dict) for r in page):
                raise CollectionError('UBIKAIS 운항편 응답 형식이 잘못되었습니다.')
            if isinstance(total, bool) or not str(total).isdigit() or int(total) < 0:
                raise CollectionError('UBIKAIS 전체 건수 정보가 잘못되었습니다.')
            total = int(total)
            if expected is not None and total != expected:
                raise CollectionError('페이지 수집 중 전체 건수가 변경되었습니다. 새로고침 후 다시 조회하세요.')
            expected = total
            digest = hashlib.sha256(json.dumps(page, sort_keys=True).encode()).hexdigest()
            if page and digest in seen:
                raise CollectionError('동일한 페이지가 반복되어 수집을 중단했습니다.')
            seen.add(digest)
            records.extend(page)
            if len(records) > total or (not page and len(records) < total):
                raise CollectionError('페이지 수집 건수와 전체 건수가 일치하지 않습니다.')
            if len(records) == total:
                break
        else:
            raise CollectionError('안전한 최대 페이지 수를 초과했습니다.')
        check_cancel(cancel)
        at = datetime.now(KST)
        saved = dict(complete=True, total=expected, fetched_at=at.isoformat(), records=records)
        temp = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as f:
                temp = f.name; json.dump(saved, f, ensure_ascii=False)
            os.replace(temp, path)
        except OSError:
            # A cache write failure must not discard an otherwise complete collection.
            pass
        finally:
            if temp and os.path.exists(temp):
                os.unlink(temp)
        return Batch(task.day, task.direction, task.airline, tuple(records), at)

    def _page(self, airport, task, offset, cancel):
        params = dict(srchDate=task.day.isoformat(), srchDatesh=task.day.strftime('%Y%m%d'),
                      srchAl=task.airline, srchFln='', srchDep=airport if task.direction == 'dep' else '',
                      srchArr=airport if task.direction == 'arr' else '', cmd='get-records',
                      limit=5, offset=offset, downloadYn=1)
        endpoint = 'selectDep.fois' if task.direction == 'dep' else 'selectArr.fois'
        url = 'https://ubikais.fois.go.kr:8030/sysUbikais/biz/fpl/' + endpoint + '?' + urlencode(params)
        headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
        if self.cookie:
            headers['Cookie'] = self.cookie
        for attempt in range(self.retries + 1):
            check_cancel(cancel)
            try:
                global _LAST_REQUEST
                with _NETWORK_LOCK:
                    while time.monotonic() - _LAST_REQUEST < self.pace:
                        check_cancel(cancel); time.sleep(0.05)
                    _LAST_REQUEST = time.monotonic()
                    with self.opener(Request(url, headers=headers), timeout=self.timeout) as response:
                        body = response.read(50_000_001)
                        if len(body) > 50_000_000:
                            raise CollectionError('단일 응답의 안전한 크기를 초과했습니다.')
                        payload = json.loads(body.decode('utf-8'))
                        if not isinstance(payload, dict):
                            raise CollectionError('UBIKAIS 응답 형식이 잘못되었습니다.')
                        return payload
            except HTTPError as exc:
                if exc.code in (401, 403):
                    raise CollectionError('UBIKAIS 접근 인증이 필요하거나 접근이 제한되었습니다.') from None
                if exc.code not in (429, 500, 502, 503, 504) or attempt == self.retries:
                    raise CollectionError(f'UBIKAIS HTTP 오류 ({exc.code})') from None
            except (URLError, TimeoutError, OSError, ValueError, UnicodeError):
                if attempt == self.retries:
                    raise CollectionError('UBIKAIS 응답을 확인할 수 없습니다. 통신·인증·서버 상태를 확인하세요.') from None
            for _ in range(2 ** attempt * 5):
                check_cancel(cancel); time.sleep(0.1)
        raise CollectionError('UBIKAIS 조회 재시도 횟수를 초과했습니다.')

