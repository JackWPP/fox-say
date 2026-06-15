"""Visual verification for the upgraded Q&A tab.

- Navigates to a known course's Q&A tab
- Captures the empty state (suggested question cards)
- Sends a question, waits for streaming, captures mid-stream and final
"""
import asyncio
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from playwright.async_api import async_playwright

OUT = Path("D:/fox-say/.screenshots/playwright")
OUT.mkdir(parents=True, exist_ok=True)

COURSE_ID = "53a76de7-ba7a-498a-ba70-955b4d5203b2"  # 中登数学
QUESTION = "请用一段话介绍下这门课最重要的两个概念,并给出一个简单的 Python 代码示例。"


async def main() -> int:
    findings = []
    page_errors = []
    console_msgs = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()
        page.on("console", lambda m: console_msgs.append(f"[{m.type}] {m.text}"))
        page.on("pageerror", lambda e: page_errors.append(str(e)))

        # 1. Bypass onboarding
        await page.goto("http://127.0.0.1:5173/", wait_until="domcontentloaded", timeout=20000)
        await page.evaluate("() => localStorage.setItem('foxsay_onboarding_done', 'true')")
        await page.reload(wait_until="networkidle")
        await page.wait_for_timeout(800)

        # 2. Go directly to course page
        await page.goto(f"http://127.0.0.1:5173/courses/{COURSE_ID}", wait_until="networkidle", timeout=20000)
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(OUT / "qa-01-course-landing.png"), full_page=True)
        print("  captured: qa-01-course-landing.png")

        # 3. Click the 问答 tab
        try:
            tab = page.get_by_role("button", name="问答")
            await tab.wait_for(state="visible", timeout=5000)
            await tab.click()
            print("  clicked 问答 tab")
        except Exception as e:
            print(f"  WARN: could not click 问答 tab: {e}")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(OUT / "qa-02-empty-state.png"), full_page=True)
        print("  captured: qa-02-empty-state.png")

        # 4. Click a suggested question (or start a new session if not on empty state)
        clicked = False
        # First, try to start a fresh session so we don't see stale DSML from earlier runs
        try:
            new_session_btn = page.get_by_title("新会话")
            if await new_session_btn.count() > 0:
                await new_session_btn.first.click()
                print("  started a new session to avoid stale data")
                await page.wait_for_timeout(800)
        except Exception:
            pass
        for label in ["这门课最核心的几个概念是什么?", "出一道能考我的题目并讲解一下"]:
            try:
                btn = page.get_by_role("button", name=label)
                if await btn.count() > 0:
                    await btn.first.click()
                    clicked = True
                    print(f"  clicked suggested: {label}")
                    break
            except Exception:
                continue
        if not clicked:
            print("  WARN: no suggested button found, falling back to textarea")
            try:
                ta = page.locator("textarea").first
                await ta.fill(QUESTION)
                await ta.press("Enter")
            except Exception as e:
                print(f"  FAIL: cannot send question: {e}")
                findings.append(f"send question failed: {e}")

        # 5. Mid-stream
        await page.wait_for_timeout(2000)
        try:
            await page.screenshot(path=str(OUT / "qa-03-mid-stream.png"), full_page=True)
            print("  captured: qa-03-mid-stream.png")
        except Exception as e:
            print(f"  WARN: mid-stream screenshot failed: {e}")

        # 6. Final answer
        try:
            await page.wait_for_function(
                "() => !document.querySelector('.fox-breathe') || document.body.innerText.includes('基于') || document.body.innerText.includes('参考了')",
                timeout=25000,
            )
        except Exception:
            print("  WARN: wait_for_function timed out — capturing anyway")
        await page.wait_for_timeout(2500)
        await page.screenshot(path=str(OUT / "qa-04-final.png"), full_page=True)
        print("  captured: qa-04-final.png")

        # Report
        if page_errors:
            print("\nPAGE ERRORS:")
            for e in page_errors:
                print(f"  PAGE ERROR: {e[:300]}")
        print("\nconsole messages (last 10):")
        for m in console_msgs[-10:]:
            print(f"  {m}")

        await browser.close()

    if findings:
        print("\nFINDINGS:")
        for f in findings:
            print(f"  - {f}")
    return 0 if not findings else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
