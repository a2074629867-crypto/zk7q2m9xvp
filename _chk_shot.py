import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True, args=["--autoplay-policy=no-user-gesture-required","--mute-audio"])
        pg = await b.new_page(viewport={"width":1080,"height":1000})
        errs=[]
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8765/", wait_until="load")
        await pg.wait_for_timeout(1000)
        print("已标:", await pg.locator("#dn").inner_text(), "/", await pg.locator("#tt").inner_text())
        # 播第一条第一个候选，确认按钮变❚❚
        await pg.locator("button.pl").first.click()
        await pg.wait_for_timeout(900)
        print("播放按钮:", await pg.evaluate("()=>document.querySelector('button.pl').innerHTML.trim()"))
        # 打开指标显示看排版
        await pg.click("#bm")
        await pg.wait_for_timeout(300)
        await pg.screenshot(path="_chk_shot.png", clip={"x":0,"y":0,"width":1080,"height":760})
        print("pageerror:", errs[:3] or "none")
        await b.close()
asyncio.run(main())
