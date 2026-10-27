import json
import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields
from datetime import datetime
from threading import Event, Lock

from config import ROOT
from domain.models import Contract, KST
from engine.demand import analyze
from normalization.flights import normalize, parse_datetime
from services.planner import plan
from adapters.ubikais_client import check_cancel

_POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix='ubikais')


def load_contract():
    data = json.loads((ROOT / 'config' / 'ubikais_contract.json').read_text(encoding='utf-8'))
    allowed = {f.name for f in fields(Contract)}
    data = {k: v for k, v in data.items() if k in allowed}
    for k in ('cancelled_statuses', 'known_statuses'):
        if k in data:
            data[k] = tuple(data[k])
    return Contract(**data)


def run_analysis(settings, client, contract, *, refresh=False, cancel=None, progress=None):
    padding = contract.actual_query_padding_days if settings.basis == 'actual' else 0
    tasks = plan(settings, actual_query_padding_days=padding or 0)
    batches = []
    for i, task in enumerate(tasks):
        check_cancel(cancel)
        if progress:
            progress(i, len(tasks), f'{task.day} {"출발" if task.direction == "dep" else "도착"} 수집')
        batch = client.fetch(settings.airport, task, refresh=refresh, cancel=cancel)
        if contract.query_date_verified:
            for record in batch.records:
                dkey,tkey=('schDate','schTime') if task.direction=='dep' else ('staDate','sta')
                dt=parse_datetime(record.get(dkey),record.get(tkey))
                if dt and (dt.date()-task.day).days not in (0,1):
                    from adapters.ubikais_client import CollectionError
                    raise CollectionError('원본 조회일과 예정일의 차이가 검증 범위를 벗어났습니다. 조회 날짜 규칙을 다시 확인해야 합니다.')
        batches.append(batch)
    check_cancel(cancel)
    if progress:
        progress(len(tasks), len(tasks), '정규화·수요 계산')
    flights, diag = normalize(tuple(batches), settings, contract)
    blockers = []
    if not contract.verified:
        blockers.append('원본 시간대·조회 날짜·결항 규칙이 미검증되어 잠정 결과입니다. 정식 보고서 출력은 보류됩니다.')
    if not contract.airline_prefix_verified:
        diag.messages.append('항공사 필터는 UBIKAIS 조회 코드 기준입니다. 운항사·공동운항 연결 정보가 없어 유사편을 추정 통합하지 않습니다.')
    if settings.basis == 'actual' and (not contract.query_date_verified or contract.actual_query_padding_days is None):
        blockers.append('실제일자가 달라진 지연편의 조회 범위를 확인하지 못했습니다.')
    if diag.conflicts or diag.quarantined:
        blockers.append('격리·충돌 자료가 있어 정식 결과로 확정할 수 없습니다.')
    result = analyze(settings, flights, diag, min(b.fetched_at for b in batches), max(b.fetched_at for b in batches), blockers=blockers)
    digest = hashlib.sha256(b'normalization-v1/engine-v1')
    for batch in batches:
        digest.update(json.dumps([str(batch.query_date),batch.direction,batch.airline,batch.records],sort_keys=True,default=str).encode())
    result.data_version = digest.hexdigest()[:16]
    a, b = settings.window
    eligible = [f for f in result.flights if a <= f.reference < b]
    diag.actual_used = sum(f.reference_source in ('actual','actual_inferred') for f in eligible)
    diag.actual_date_inferred = sum(f.reference_source == 'actual_inferred' for f in eligible)
    diag.scheduled_used = len(eligible) - diag.actual_used
    check_cancel(cancel)
    return result


class Job:
    def __init__(self, settings, client, contract, refresh=False):
        self.settings = settings
        self.cancel = Event()
        self.lock = Lock()
        self.done, self.total, self.message = 0, 1, '조회 준비'
        self.future = _POOL.submit(run_analysis, settings, client, contract, refresh=refresh,
                                   cancel=self.cancel, progress=self.progress)

    def progress(self, done, total, message):
        with self.lock:
            self.done, self.total, self.message = done, total, message

    def status(self):
        with self.lock:
            return self.done / self.total, self.message
