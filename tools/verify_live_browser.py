"""Check a non-demo server against the sample-validated, user-approved rules."""
from pathlib import Path
import re
from playwright.sync_api import sync_playwright, expect

URL='http://127.0.0.1:8502/?v=1&airport=RKSI&mode=custom&start=2026-10-26&end=2026-10-26&airlines=&basis=scheduled&day_start=0&interval=60&dep=-50,10,20&arr=-20,30,40'

if __name__=='__main__':
    target=Path('artifacts/browser');target.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1700,'height':1100})
        page.goto(URL,wait_until='networkidle')
        page.get_by_role('button',name='조회 · 분석 실행',exact=True).wait_for()
        assert page.locator('button[data-cell]').count()==0
        assert page.locator('[data-testid="stException"]').count()==0
        page.get_by_role('button',name='조회 · 분석 실행',exact=True).click()
        page.get_by_text('시간대 상세',exact=True).wait_for(timeout=60000)
        expect(page.locator('button[data-cell]')).to_have_count(24,timeout=15000)
        count_label=page.get_by_text(re.compile(r'^\d+ / \d+$'))
        expect(count_label).to_be_visible()
        assert sum(int(v) for v in count_label.inner_text().split(' / '))>0
        page.get_by_role('button',name='현재 적용 결과의 PNG · PDF 생성').wait_for()
        page.get_by_role('button',name='현재 적용 결과의 PNG · PDF 생성').click()
        page.get_by_role('button',name='PDF 다운로드',exact=True).wait_for(timeout=30000)
        # An independent browser session restores settings but has no other user's result.
        other=browser.new_context().new_page()
        other.goto(URL,wait_until='networkidle')
        other.get_by_role('button',name='조회 · 분석 실행',exact=True).wait_for()
        assert other.locator('button[data-cell]').count()==0
        assert other.get_by_text('시간대 상세',exact=True).count()==0
        page.get_by_text('시간대별 최대 필요 조업조',exact=True).scroll_into_view_if_needed()
        page.screenshot(path=target/'live_scheduled.png',full_page=True)
        assert page.locator('[data-testid="stException"]').count()==0
        page.goto(URL.replace('basis=scheduled','basis=actual'),wait_until='networkidle')
        page.get_by_role('button',name='조회 · 분석 실행',exact=True).click()
        breakdown=page.get_by_text('기간 편수 기준: 실제시각 사용',exact=False)
        expect(breakdown).to_be_visible(timeout=60000)
        assert page.get_by_text('12개 조회 단위',exact=False).count()==1
        numbers=re.search(r'실제시각 사용 (\d+)편.*날짜 추정 (\d+)편.*예정 대체 (\d+)편',breakdown.inner_text())
        actual,inferred,fallback=map(int,numbers.groups())
        counts=map(int,page.get_by_text(re.compile(r'^\d+ / \d+$')).inner_text().split(' / '))
        assert actual+fallback==sum(counts) and inferred<=actual
        page.get_by_text('시간대별 최대 필요 조업조',exact=True).scroll_into_view_if_needed()
        page.screenshot(path=target/'live_actual.png',full_page=True)
        assert page.locator('[data-testid="stException"]').count()==0
        print('Live browser: explicit query, result, report generation, session isolation passed')
        browser.close()
