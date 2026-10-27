# Flight Crew Demand Analysis

UBIKAIS 운항자료에서 공항별·운영일별·시간대별 동시 조업조 수요를 계산하는 Streamlit 앱입니다.
출발·도착 1편당 각각 1개 조를 점유하며, 결과 단위는 **개 조**입니다.

소스 저장소: [ohsunbi/flight_demand_analysis](https://github.com/ohsunbi/flight_demand_analysis)

## 현재 상태

계산 엔진, URL 설정 복원, 클릭 히트맵·오른쪽 상세, PNG·A4 PDF 출력을 구현했습니다.
인천·김포·제주 표본 수집, 인천 하루의 예정/실제 우선 계산과 보고서 출력을 확인했습니다. Cloud 배포는 아직 수행하지 않았습니다.
시간대는 사용자의 기존 운영 확인에 따라 한국시간으로 처리합니다.
**실제 날짜가 없는 HHMM은 사용자 합의에 따라 예정시각에 가장 가까운 날짜로 계산합니다. 날짜 추정 편수를 표시하며, 하루 이상 지연된 편은 날짜가 부정확할 수 있습니다.**
가상 테스트 통과와 실제 표본 검증, 아직 검증하지 않은 범위를 구분합니다. 상세 현황은 `project_context.md`와 `docs/data_contract.md`를 참고하세요.

## Windows 설치와 실행

Python 3.12와 [uv](https://docs.astral.sh/uv/getting-started/installation/)를 사용합니다.
프로젝트 루트에서 실행하세요.

```powershell
uv sync --locked
uv run --no-sync streamlit run app.py
```

참조 프로젝트 폴더는 필요하지 않습니다. 최초 접속은 설정만 표시하며 자동 API 조회하지 않습니다.

## 사용 방법

1. 공항과 월별/사용자 지정 기간을 선택합니다. 양 끝 날짜를 포함해 최대 31개 운영일입니다.
2. 전체 항공사 또는 쉼표로 구분한 복수 ICAO 3자리 코드를 선택합니다.
3. 예정 또는 실제 주기장 우선 기준을 선택합니다.
4. 필요하면 운영일 시작과 조업시간을 변경한 뒤 **조회 · 분석 실행**을 누릅니다.
5. 히트맵 셀을 클릭하면 오른쪽에 피크·점유 겹침·기준시각 운항편 목록이 표시됩니다.
6. 수집·품질 검사를 통과한 결과에서 보고서를 생성하고 PNG/PDF를 다운로드합니다.

실제 우선은 출발 주기장 출발·도착 주기장 도착시각을 사용하고 없으면 STD/STA를 사용합니다.
이륙·착륙·예상시각을 중간 대체값으로 사용하지 않습니다. 편수도 선택한 기준시각으로 집계합니다.
날짜 추정은 예정일 전날·당일·다음날 중 예정시각에 가장 가까운 시각을 선택합니다. 정확히 12시간 동률이면 예정일 당일을 선택합니다.
확인된 결항 CNL은 제외합니다. 특정 항공사는 API의 조회 코드 기준이며 검증된 실제 운항사 필드로 가장하지 않습니다.

기본값: 운영일 00:00, 셀 60분(30분 선택 가능), 출발 -50/+10/+20분, 도착 -20/+30/+40분.
조업 시작·종료·재투입 순서이며, 조업 종료 후 대기시간도 점유에 포함합니다.

편수는 해당 시간대의 기준시각을 가진 운항편 수입니다. 필요 조업조 수는 그 시간대의 **최대 동시 점유 수**이므로 서로 다릅니다.
인접 날짜 편이 점유에 기여할 수 있어 수집에는 31일 외의 보충 날짜가 필요할 수 있습니다.

## 설정 URL

유효한 설정 변경은 주소창 URL에 반영됩니다. URL을 복사해 다시 열면 조건을 복원합니다.
자동 수집하지 않으며 조회 버튼을 눌러야 합니다. 같은 URL도 자료 변경에 따라 결과가 달라질 수 있습니다.
입력 조건과 적용 결과는 구분하며 조회 실패 시 이전 결과를 유지합니다.
자료·사용자 설정의 영구 DB는 없습니다. 서버 캐시는 일시적인 성능 최적화입니다.

## 인증정보

필요한 경우에만 `UBIKAIS_COOKIE` 환경변수 또는 `.streamlit/secrets.toml`의 같은 키로 주입합니다.
실제 값을 코드·URL·Git에 넣지 마세요. 비밀값 없는 설정 예시는 다음과 같습니다.

```toml
UBIKAIS_COOKIE = "여기에_본인_세션값을_로컬에서만_입력"
```

## 개발 검증

```powershell
uv sync --locked --group dev
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m playwright install chromium
```

브라우저·보고서 기능을 가상 데이터로 확인하려면:

```powershell
$env:CREW_DEMO = '1'
uv run --no-sync streamlit run app.py
```

화면과 보고서에 가상 데이터 표시가 붙습니다. 이 환경변수를 실제 운영에 설정하지 마세요.
가상 모드를 해제하려면 서버를 종료한 뒤 다음과 같이 실행합니다.

```powershell
Remove-Item Env:CREW_DEMO -ErrorAction SilentlyContinue
uv run --no-sync streamlit run app.py
```

상세 검증 명령은 `docs/verification.md`를 참고하세요.

## Streamlit Community Cloud

실제 Cloud 배포는 아직 수행하지 않았습니다. 표본 범위 밖 검증과 운영 설정을 확인한 뒤 다음과 같이 배포합니다.

1. GitHub 저장소 `ohsunbi/flight_demand_analysis`의 `main` 브랜치를 사용합니다. 캐시·비밀값·가상 검증 산출물은 제외되어 있습니다.
2. Community Cloud에서 저장소·브랜치를 지정하고 실행 파일을 `app.py`로 선택합니다.
3. Advanced settings에서 Python **3.12**를 선택합니다.
4. 필요한 경우 Secrets에 인증정보를 설정합니다. `CREW_DEMO`는 설정하지 않습니다.
5. 공개 접근 설정과 신규 세션, 전체/복수 항공사, 다운로드를 실제 Cloud에서 확인합니다.

`pyproject.toml`과 `uv.lock`이 의존성 기준이고 `requirements.txt`는 동일 lock에서 생성한 보조 파일입니다.
개발용 브라우저/PDF 검사 패키지는 기본 설치 그룹에서 제외했습니다.

공식 안내: [배포](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy),
[Python 선택](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/upgrade-python).

개발을 이어갈 때는 `project_context.md`부터 확인하세요.

