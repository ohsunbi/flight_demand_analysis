import json
import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields
from datetime import datetime
from threading import Event, Lock

from config import ROOT
from domain.models import Contract, Diagnostics, KST
from engine.demand import analyze
from normalization.flights import movement_context, normalize
from services.collection import collect
from services.excel_schedule import merge_excel
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


def run_analysis(settings, client, contract, *, refresh=False, cancel=None, progress=None,
                 source_mode='site', excel_flights=(), excel_duplicates=0, upload_digest=''):
    uses_site = source_mode in ('site', 'site_excel')
    if source_mode not in ('site', 'site_excel', 'excel') or (source_mode != 'site' and not upload_digest):
        raise ValueError('자료 수집 방식 또는 업로드 파일을 확인하세요.')
    if source_mode == 'excel' and settings.basis != 'scheduled':
        raise ValueError('엑셀만 사용하면 STA/STD 기준으로 분석해야 합니다.')
    snapshots = [] if uses_site and settings.quick_turn_active else None
    batches, flights, diag = (), (), Diagnostics()
    blockers = []
    if uses_site:
        batches, queries, unclassifiable_rows = collect(settings, client, contract, refresh=refresh,
                                                        cancel=cancel, progress=progress, context=snapshots)
        check_cancel(cancel)
        if progress:
            progress(queries, queries, '수요 계산 중')
        flights, diag = normalize(batches, settings, contract)
        if unclassifiable_rows:
            diag.messages.append(f'ICAO 접두어를 판별할 수 없는 {unclassifiable_rows}건은 항공사 선별에서 제외했습니다.')
        if not contract.verified:
            blockers.append('원본 시간대·조회 날짜·결항 규칙이 미검증되어 잠정 결과입니다. 정식 보고서 출력은 보류됩니다.')
        if not contract.airline_prefix_verified:
            diag.messages.append('항공사는 원본 편명의 ICAO 접두어로 선별하며 접두어를 판별할 수 없는 행은 제외합니다. 실제 운항사·공동운항 연결을 추정하지 않습니다.')
        if settings.basis == 'actual' and (not contract.query_date_verified or contract.actual_query_padding_days is None):
            blockers.append('실제일자가 달라진 지연편의 조회 범위를 확인하지 못했습니다.')
    elif progress:
        progress(1, 1, '엑셀 운항편 수요 계산')
    check_cancel(cancel)
    if source_mode != 'site':
        flights, replaced = merge_excel(flights, excel_flights)
        diag.raw += len(excel_flights) + excel_duplicates
        diag.duplicates += excel_duplicates
        if source_mode == 'site_excel':
            diag.messages.append(f'같은 편인 UBIKAIS 기록 {replaced:,}건을 엑셀 자료로 대체했습니다.')
    if diag.conflicts or diag.quarantined:
        blockers.append('격리·충돌 자료가 있어 정식 결과로 확정할 수 없습니다.')
    context = movement_context(snapshots, settings.airport, contract, check=lambda: check_cancel(cancel)) if snapshots is not None else ()
    check_cancel(cancel)
    now = datetime.now(KST)
    result = analyze(settings, flights, diag, min((b.fetched_at for b in batches), default=now),
                     max((b.fetched_at for b in batches), default=now),
                     blockers=blockers, context=context, check=lambda: check_cancel(cancel))
    digest = hashlib.sha256(b'collection-v3/normalization-v2/engine-v2/turnaround-v1')
    if uses_site:
        digest.update(contract.actual_date_policy.encode())
    if source_mode != 'site':
        digest.update(f'excel-v1/{source_mode}/{upload_digest}'.encode())
        result.source_mode = source_mode
        result.upload_digest = upload_digest
        excel_count = sum(f.key.startswith('excel:') for f in result.flights)
        diag.messages.append(f'분석 범위 관련 엑셀 운항편 {excel_count:,}편을 STA/STD 기준으로 반영했습니다.')
    for batch in batches:
        digest.update(json.dumps([str(batch.query_date),batch.direction,batch.airline,batch.records],sort_keys=True,default=str).encode())
    if snapshots is not None:
        for batch in snapshots:
            digest.update(json.dumps([str(batch.query_date),batch.direction,batch.records],sort_keys=True,default=str).encode())
    result.data_version = digest.hexdigest()[:16]
    a, b = settings.window
    eligible = [f for f in result.flights if a <= f.reference < b]
    diag.actual_used = sum(f.reference_source in ('actual','actual_inferred') for f in eligible)
    diag.actual_date_inferred = sum(f.reference_source == 'actual_inferred' for f in eligible)
    diag.scheduled_used = len(eligible) - diag.actual_used
    check_cancel(cancel)
    return result


class Job:
    def __init__(self, settings, client, contract, refresh=False, **source):
        self.settings = settings
        self.source_mode = source.get('source_mode', 'site')
        self.cancel = Event()
        self.lock = Lock()
        self.done, self.total, self.message = 0, 1, '분석 준비' if self.source_mode == 'excel' else '조회 준비'
        self.future = _POOL.submit(run_analysis, settings, client, contract, refresh=refresh,
                                   cancel=self.cancel, progress=self.progress, **source)

    def progress(self, done, total, message):
        with self.lock:
            self.done, self.total, self.message = done, total, message

    def status(self):
        with self.lock:
            return self.done / self.total, self.message
