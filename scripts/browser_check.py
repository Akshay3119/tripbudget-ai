import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright, expect


async def main():
    out = Path("deliverables/evidence/ui")
    out.mkdir(parents=True, exist_ok=True)
    values = dict(line.split("=", 1) for line in Path(".secrets/organizer.txt").read_text().splitlines())
    errors = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 1100}, device_scale_factor=1)
        page = await context.new_page()
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        await page.goto("http://127.0.0.1:8084/", wait_until="networkidle")
        await page.screenshot(path=str(out / "desktop-initial.png"), full_page=True)
        await page.locator("#account").click()
        await page.locator("#username").fill(values["username"])
        await page.locator("#password").fill(values["password"])
        await page.locator("#login-form button[type=submit]").click()
        await expect(page.locator("#account")).to_contain_text("connected")
        await page.locator("#estimate-consent").check()
        async with page.expect_response(
            lambda response: response.url.endswith("/api/episodes") and response.request.method == "POST"
        ) as admitted:
            await page.locator("#plan-button").click()
        episode = (await (await admitted.value).json())["id"]
        await expect(page.locator("#state-badge")).to_have_text("PENDING APPROVAL", timeout=290000)
        await page.screenshot(path=str(out / "desktop-pending.png"), full_page=True)
        await page.locator("#approve").click()
        await expect(page.locator("#ledger-banner")).to_be_visible(timeout=60000)
        await page.screenshot(path=str(out / "desktop-committed.png"), full_page=True)
        await page.locator("#sources-open").click()
        await page.wait_for_selector("#sources-dialog[open] .source-record")
        await page.screenshot(path=str(out / "evidence-library.png"))
        await page.locator("#close-sources").click()
        await page.locator("#budget").fill("50")
        await page.locator("#estimate-consent").check()
        await page.locator("#plan-button").click()
        await expect(page.locator("#state-badge")).to_have_text("PROVEN INFEASIBLE", timeout=60000)
        await expect(page.locator("#trip-results")).to_have_class("hidden")
        await expect(page.locator("#ledger-banner")).not_to_be_visible()
        await expect(page.locator("#approval-card")).not_to_be_visible()
        await page.screenshot(path=str(out / "edge-infeasible-cleared.png"), full_page=True)
        mobile = await browser.new_context(
            viewport={"width": 390, "height": 844}, device_scale_factor=1, is_mobile=True
        )
        phone = await mobile.new_page()
        await phone.goto("http://127.0.0.1:8084/", wait_until="networkidle")
        assert await phone.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
            "Mobile horizontal overflow"
        )
        await phone.screenshot(path=str(out / "mobile-initial.png"), full_page=True)
        result = {
            "actual_browser_run": True,
            "episode": episode,
            "end_state": "COMMITTED",
            "javascript_errors": errors,
            "desktop": [1440, 1100],
            "mobile": [390, 844],
            "mobile_horizontal_overflow": False,
            "infeasible_new_request_clears_previous_result": True,
        }
        (out / "browser-results.json").write_text(json.dumps(result, indent=2))
        assert not errors, errors
        await browser.close()
        print(json.dumps(result))


asyncio.run(main())
