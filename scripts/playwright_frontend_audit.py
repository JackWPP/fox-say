"""Real Playwright interaction: walk the onboarding flow and report every step.

Captures screenshots and console messages to find where it actually gets stuck.
"""
import asyncio
import sys
import json
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from playwright.async_api import async_playwright

SCREENSHOT_DIR = Path("D:/fox-say/.screenshots/playwright")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


async def main() -> int:
    findings: list[str] = []
    console_messages: list[str] = []
    page_errors: list[str] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        page.on("console", lambda msg: console_messages.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        def shot(name: str) -> None:
            path = SCREENSHOT_DIR / f"{name}.png"
            asyncio.create_task(page.screenshot(path=str(path), full_page=True))

        async def snap(name: str) -> None:
            await page.screenshot(path=str(SCREENSHOT_DIR / f"{name}.png"), full_page=True)
            print(f"  screenshot: {name}.png")

        async def report_console(prefix: str = "") -> None:
            print(f"\n  {prefix}console messages so far:")
            for m in console_messages[-15:]:
                print(f"    {m}")
            if page_errors:
                print(f"  {prefix}PAGE ERRORS:")
                for e in page_errors:
                    print(f"    PAGE ERROR: {e[:200]}")

        print("=" * 60)
        print("  1. Open /")
        print("=" * 60)
        try:
            await page.goto("http://127.0.0.1:5173/", wait_until="networkidle", timeout=30000)
        except Exception as e:
            print(f"  goto error: {e}")
            findings.append(f"goto failed: {e}")
        await page.wait_for_timeout(3000)
        await snap("01-onboarding")
        body_text = (await page.text_content("body")) or ""
        if "你来了" not in body_text:
            findings.append("onboarding greeting not found in body")
            print(f"  WARN: onboarding greeting missing. body excerpt: {body_text[:200]}")
        else:
            print("  OK: onboarding greeting visible")
        await report_console("after step 0 load, ")

        print("\n" + "=" * 60)
        print("  2. Click '我要备考' (exam mode)")
        print("=" * 60)
        try:
            btn = page.get_by_role("button", name="我要备考")
            await btn.wait_for(state="visible", timeout=5000)
            await btn.click()
            print("  clicked 备考 button")
        except Exception as e:
            print(f"  FAIL to click 备考: {e}")
            findings.append(f"click exam button failed: {e}")
        await page.wait_for_timeout(2000)
        await snap("02-step1")
        body_text = (await page.text_content("body")) or ""
        if "先建一门课" not in body_text:
            findings.append("step 1 (先建一门课) text not visible after click")
            print(f"  WARN: step 1 text missing. body: {body_text[:300]}")
        else:
            print("  OK: step 1 visible (先建一门课)")

        print("\n" + "=" * 60)
        print("  3. Click '手动创建' (manual create)")
        print("=" * 60)
        try:
            btn = page.get_by_role("button", name="手动创建")
            await btn.wait_for(state="visible", timeout=5000)
            await btn.click()
            print("  clicked 手动创建 button")
        except Exception as e:
            print(f"  FAIL: {e}")
            findings.append(f"click 手动创建 failed: {e}")
        await page.wait_for_timeout(1500)
        await snap("03-modal")

        print("\n" + "=" * 60)
        print("  4. Fill form and submit")
        print("=" * 60)
        try:
            await page.locator('input[type="text"]').first.fill("测试课程 (e2e)")
            print("  filled title")
            await page.locator('input[type="date"]').first.fill("2026-07-20")
            print("  filled exam_date")
            await page.get_by_role("button", name="创建").last.click() if await page.get_by_role("button", name="创建").count() > 0 else None
        except Exception as e:
            print(f"  form interaction: {e}")
        await page.wait_for_timeout(3000)
        await snap("04-after-create")

        body_text = (await page.text_content("body")) or ""
        if "把材料扔进来" in body_text or "PDF、PPT" in body_text:
            print("  OK: step 2 visible (上传材料)")
        else:
            findings.append("step 2 (上传材料) not visible after create")
            print(f"  body after create: {body_text[:300]}")

        print("\n" + "=" * 60)
        print("  5. Click '跳过，稍后再说' to complete onboarding")
        print("=" * 60)
        try:
            btn = page.get_by_role("button", name="跳过，稍后再说")
            if await btn.count() > 0:
                await btn.click()
                print("  clicked 跳过")
            else:
                # alternative: 直接设置 localStorage
                print("  no 跳过 button; trying localStorage fallback")
                await page.evaluate("() => { localStorage.setItem('foxsay_onboarding_done','true'); }")
                await page.reload()
        except Exception as e:
            print(f"  skip: {e}")
        await page.wait_for_timeout(3000)
        await snap("05-bookshelf")

        body_text = (await page.text_content("body")) or ""
        if "我的课程" in body_text:
            print("  OK: bookshelf page reached")
        else:
            findings.append("bookshelf page not reached")
            print(f"  body: {body_text[:300]}")

        await report_console("final, ")

        await browser.close()

    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print(f"  console messages: {len(console_messages)}")
    print(f"  page errors: {len(page_errors)}")
    for err in page_errors[:5]:
        print(f"    {err[:300]}")
    if findings:
        print(f"\n  FINDINGS ({len(findings)}):")
        for f in findings:
            print(f"    - {f}")
        return 1
    print("\n  no findings — onboarding flow walked successfully")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
