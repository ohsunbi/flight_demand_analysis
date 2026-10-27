# 인수인계 스냅샷 — 2026-10-27

이 문서는 작성 시점의 인수인계 기록입니다. 현재 상태는 `project_context.md`와 실제 코드를 우선 확인하세요.

## 완료

사용자와 상세 계획을 합의하고 독립적인 Streamlit 앱을 구현했다.
31일 제한, 예정/실제 주기장 우선, 공통 오프셋, CNL 제외, 00:00 운영일, 60/30분 셀,
실제 클릭과 오른쪽 상세, 설정 URL 복원, 전체/복수 항공사, PNG/A4 PDF를 구현했다.
기존 프로젝트는 읽기 전용으로 취급했고 기준 커밋은 `a041c93`이다.
이 문서의 최초 작성은 Git 초기화 전이었다. 이후 공개 저장소 `ohsunbi/flight_demand_analysis`의 main 브랜치 업로드를 준비했다.

## 중요한 사용자 결정

KST는 사용자가 기존 운영 기준으로 확인했다.
날짜 없는 실제 HHMM은 예정일 전후 가장 가까운 날짜로 추정해 사용하고 추정 건수를 표시하기로 했다.
하루 이상 지연은 이 모델로 날짜를 복원할 수 없을 수 있다. 원본 확정 날짜로 기록하면 안 된다.
로그인·영구 저장 없이 URL 설정 복원, 자동 조회 없음. 전체 항공사 조회 필수.

## 마지막 검증

자동 테스트, 실제 Chromium, 실자료 하루 및 복수 항공사, 31일 가상 보고서 검증을 수행했다.
최종 테스트 개수와 명령은 `docs/verification.md`에 있다.
실제 API는 인천·김포·제주 표본 범위다. 모든 공항/기간 또는 실제 Cloud를 검증한 것은 아니다.
가상 산출물과 실자료 산출물은 `artifacts/` 안에서 분리하며 Git에 넣지 않는다.

## 다음 작업

1. 로컬 화면을 사용자와 검토하고 필요한 UX 수정을 반영한다.
2. GitHub `ohsunbi/flight_demand_analysis`의 main 브랜치를 Streamlit Cloud 배포 대상으로 선택한다.
3. Python 3.12로 배포하고 Secrets가 필요한지 확인한다. CREW_DEMO를 운영에서 설정하지 않는다.
4. Cloud 네트워크/새 세션/동시 사용/다운로드와 나머지 공항·미래 가용성을 확인한다.
5. 원본 날짜 차이가 0~1일을 벗어나면 `docs/data_contract.md`와 실제 응답을 조사한다. 조용히 날짜를 보정하지 않는다.

실행: `uv sync --locked`, `uv run --no-sync streamlit run app.py`.
검증: `uv sync --locked --group dev`, `.venv\Scripts\python.exe -m pytest -q`.
