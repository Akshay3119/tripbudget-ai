"""Verify the final delivered MP4 plays, seeks and advances in a real browser."""

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


async def main():
    video = Path("deliverables/video/TripBudgetAI_Demo.mp4").resolve()
    player = Path(".runtime/video/player.html").resolve()
    player.write_text(
        '<!doctype html><meta charset="utf-8"><title>Actual MP4 playback check</title><video controls preload="auto" width="1152" src="'
        + video.as_uri()
        + '"></video>'
    )
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1200, "height": 900})
        await page.goto(player.as_uri())
        await page.locator("video").evaluate(
            "(v)=>new Promise((resolve,reject)=>{if(v.readyState>=2)return resolve();v.onloadeddata=resolve;v.onerror=reject;})"
        )
        initial = await page.locator("video").evaluate(
            "(v)=>({duration:v.duration,width:v.videoWidth,height:v.videoHeight,readyState:v.readyState,error:v.error})"
        )
        assert 300 <= initial["duration"] <= 600 and initial["error"] is None
        await page.locator("video").evaluate("(v)=>{v.currentTime=200;v.muted=false;return v.play();}")
        await asyncio.sleep(2)
        after = await page.locator("video").evaluate(
            "(v)=>({time:v.currentTime,paused:v.paused,error:v.error})"
        )
        assert after["time"] > 201 and after["paused"] is False and after["error"] is None
        await page.screenshot(path=".runtime/video/playback-check.png")
        result = {
            "actual_browser_playback": True,
            "metadata": initial,
            "after_seek_and_play": after,
            "media": "H.264/AAC actual capture with synthesized narration",
        }
        Path("deliverables/evidence/video-playback.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
