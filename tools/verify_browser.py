"""Real browser check against a CREW_DEMO=1 local server."""
from pathlib import Path
import re
from playwright.sync_api import sync_playwright


def main():
    target=Path('artifacts/browser');target.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1700,'height':1100},device_scale_factor=1)
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto('http://127.0.0.1:8501',wait_until='networkidle')
        page.get_by_text('시간대 상세',exact=True).wait_for(timeout=30000)
        assert page.locator('[data-testid="stException"]').count()==0
        buttons=page.locator('button[data-cell]')
        assert buttons.count()==31*24
        buttons.nth(10).click()
        page.wait_for_timeout(1300)
        assert page.locator('button[data-cell="10"]').get_attribute('aria-pressed')=='true'
        assert '10:00' in page.get_by_text(re.compile('^운영일 2026-10-01')).inner_text()
        page.screenshot(path=target/'desktop.png',full_page=True)
        # Interval changes update URL, but the applied analysis stays unchanged.
        page.get_by_text('30분',exact=True).click()
        page.wait_for_timeout(1000)
        assert 'interval=30' in page.url
        assert page.get_by_text('입력 조건이 변경되었습니다.',exact=False).count()>0
        page.get_by_role('button',name='현재 적용 결과의 PNG · PDF 생성').click()
        page.get_by_role('button',name='PDF 다운로드',exact=True).wait_for(timeout=30000)
        assert page.locator('[data-testid="stException"]').count()==0
        with page.expect_download() as download:
            page.get_by_role('button',name='PDF 다운로드',exact=True).click()
        file=download.value
        file.save_as(target/'browser_download.pdf')
        assert (target/'browser_download.pdf').stat().st_size>10000
        restored=browser.new_page(viewport={'width':1700,'height':1100})
        restored.goto(page.url,wait_until='networkidle')
        restored.get_by_text('시간대 상세',exact=True).wait_for(timeout=30000)
        assert restored.locator('button[data-cell]').count()==31*48
        assert restored.locator('[data-testid="stException"]').count()==0
        restored.screenshot(path=target/'restored_30min.png',full_page=True)
        assert not errors,errors
        print('Browser: true cell selection, URL restore, pending inputs, report download passed')
        browser.close()

if __name__=='__main__':main()
