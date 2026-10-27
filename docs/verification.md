# 검증 기록

기준일 2026-10-27. 실제 API·가상 자료·로컬 브라우저·Cloud 검증을 구분한다.

## 자동 테스트

```powershell
uv sync --locked --group dev
.venv\Scripts\python.exe -m pytest -q
```

63개 통과 확인. 이벤트 경계·동시 재사용·비동시 방향별 최대·이월·0 수요·동률·윤년/연말·임의 운영일 시작,
독립 기준 계산과 무작위 비교·적분 불변식, 실제/예정 편수 귀속, 결측·충돌·중복·결항,
페이지 반복·total 불일치·비정상 빈 페이지·재시도·깨진 캐시·중단·TTL,
URL 복원·잘못된 설정·초기 자동 조회 금지·PDF 전체 시간 열을 검사한다.

## 실제 API

```powershell
$env:PYTHONPATH = '.'
.venv\Scripts\python.exe tools/live_smoke.py
```

RKSI 2026-10-26 예정 분석, 경계 날짜 24~27의 출발·도착 8개 조회 단위.
원본 5,069행, 네트워크/캐시 혼합 약 3.8초였다. 전체 신규 네트워크 수집 시간으로 해석하면 안 된다.
CNL 제외 후 기간 편수는 출발 619, 도착 624였다.
`tools/live_smoke.py --actual`은 날짜 추정 보충까지 23~28일의 12개 조회 단위, 7,584행을 사용했다.
혼합 수집 약 5.48초, 실제 우선 출발 620/도착 621, 실제 사용 1,240편(날짜 추정 1,240), 예정 대체 1편이었다.
시간대와 실제 날짜 추정은 사용자 결정이다. 실제 원본 날짜를 대조 완료한 수치라는 뜻은 아니다.
`tools/validate_query_window.py`로 RKSI 3일, RKSS/RKPC 하루 양방향의 예정일-조회일 0~1일을 관측했다.
`tools/verify_airlines.py`로 APJ+ESR 복수 항공사 하루를 조회해 출발/도착 각각 31편을 확인했다.
31일 전체 API 수집은 불필요한 반복 요청을 피하기 위해 수행하지 않았다.

## 브라우저

가상 검증 서버:

```powershell
$env:CREW_DEMO = '1'
uv run --no-sync streamlit run app.py --server.port 8501
```

다른 터미널:

```powershell
.venv\Scripts\python.exe -m playwright install chromium
.venv\Scripts\python.exe tools/verify_browser.py
```

실제 Chromium에서 31일·24열 클릭, 선택 상태와 오른쪽 상세 갱신, 30분 URL 변경,
적용 전 입력과 이전 결과 분리, PDF 다운로드, 새 페이지의 48열 복원을 확인했다.
가상 자료이므로 실자료 정확도 검증으로 계산하지 않는다.

실자료 서버는 별도 터미널에서 `CREW_DEMO`를 제거하고 포트 8502로 실행한다.

```powershell
Remove-Item Env:CREW_DEMO -ErrorAction SilentlyContinue
uv run --no-sync streamlit run app.py --server.port 8502
```

```powershell
.venv\Scripts\python.exe tools/verify_live_browser.py
```

설정 URL 최초 열기에서 자동 조회가 없고, 명시적 조회 후 실자료 결과와 보고서를 생성하는 것을 확인했다.
인천 하루의 편수 표시와 실제 우선의 실제+예정 대체=전체 편수, 날짜 추정 건수 표시를 검사한다.
실자료는 조회 시점에 수정될 수 있으므로 브라우저 검사는 예시 숫자를 고정 정답으로 사용하지 않는다.
미확정 프로필의 정식 내보내기 차단은 별도 자동 테스트로 확인한다.
독립 브라우저 컨텍스트에는 다른 사용자의 분석 결과가 노출되지 않았다.

## 보고서

```powershell
$env:PYTHONPATH = '.'
.venv\Scripts\python.exe tools/verify_reports.py
```

31일 가상 결과를 생성하고 PDF를 PNG로 렌더링했다. PyMuPDF를 사용했으며 Poppler는 설치하지 않았다.
각 페이지와 전체 PNG에서 한글·시간 머리글·첫/마지막 날짜·범례·페이지 분할을 시각 확인한다.
시간 머리글은 45도로 배치해 겹침을 해소했다.

| 모드 | 전체 PNG | PDF |
|---|---|---|
| 60분 | 2880×2428 픽셀 | A4 가로 2페이지 |
| 30분 | 4320×2428 픽셀 | A4 가로 4페이지, 12시간씩 열 분할 |

모든 날짜 및 마지막 시간 열은 PDF 텍스트 추출 검사로도 확인했다. 글꼴은 Nanum Gothic이다.
가상 데이터 표시가 화면과 보고서에 들어간다. 검증 산출물은 `artifacts/`에 저장하고 Git에서 제외한다.
`tools/verify_live_reports.py`로 실제 우선 하루 보고서의 날짜 추정 표시, A4 치수, 글꼴 임베딩도 확인했다.
보고서에서는 한글·마지막 시간·다음날 종료시각 표기를 렌더링으로 점검했다.

## 성능

```powershell
$env:PYTHONPATH = '.'
.venv\Scripts\python.exe tools/benchmark_engine.py
```

31일·38,750개 가상 점유구간·30분 1,488셀을 계산했다.
로컬 엔진 약 0.844초, fixture 생성 포함 Python 추적 메모리 최대 28.64 MiB.
이는 API 수집·PDF 생성·Cloud 전체 프로세스 메모리를 포함하지 않는 수치다.

## 남은 검증

- 시간대는 사용자 확인에 따라 KST. 주기장 실제 날짜 추정은 사용자 합의한 가정이며 하루 이상 지연에 한계가 있다.
- 조회 날짜는 관측한 0~1일 차이를 적용하며 모든 날짜의 공식 보장 문서를 확보한 것은 아니다.
- 공동운항·실제 운항사·스케줄 변경 처리의 근거 및 수작업 대조.
- 나머지 공항과 과거·미래 자료의 가용 범위.
- 31일 실자료 성능, 실제 Cloud 배포와 네트워크·동시 사용 부하.
- 실제 Cloud에서의 다운로드·새 세션·캐시 소실 후 재조회.
