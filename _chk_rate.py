import asyncio, json, os, time
from playwright.async_api import async_playwright
URL = "http://127.0.0.1:8765/"
LAB = "G:/_setup/_mt_labels_live.json"

async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True, args=["--autoplay-policy=no-user-gesture-required","--mute-audio"])
        pg = await b.new_page(viewport={"width":1100,"height":900})
        errs=[]
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append("CONSOLE "+m.text) if m.type=="error" else None)
        await pg.goto(URL, wait_until="load"); await pg.wait_for_timeout(900)

        n_card = await pg.locator(".card").count()
        n_pl   = await pg.locator("button.pl").count()
        n_sel  = await pg.locator("button.sel2").count()
        total  = await pg.locator("#tt").inner_text()
        print(f"卡片 {n_card} | 播放键 {n_pl} | 选择键 {n_sel} | 总数 {total}")

        # 1) 播放第一个
        await pg.locator("button.pl").first.click()
        await pg.wait_for_timeout(1200)
        st = await pg.evaluate("""() => {
          const b=document.querySelector('button.pl');
          return {btn:b.innerHTML.trim(), on:b.classList.contains('on')};
        }""")
        print("点播放后按钮:", st)

        # 检查 Audio 对象真的在播（不是 DOM audio 元素，是 new Audio）
        # 用 window.Audio 拦截不到，改为看按钮状态 + 无报错
        await pg.locator("button.pl").nth(1).click()   # 切到第二个，第一个应复位
        await pg.wait_for_timeout(700)
        st2 = await pg.evaluate("""() => {
          const bs=[...document.querySelectorAll('button.pl')].slice(0,3);
          return bs.map(x=>({t:x.innerHTML.trim(), on:x.classList.contains('on')}));
        }""")
        print("切到第二个后:", st2)

        # 2) 点「选它」（第 1 条的第 2 个候选）
        first_uid = await pg.locator(".card").first.get_attribute("data-uid")
        seeds = await pg.evaluate("""() => {
          const c=document.querySelector('.card');
          return [...c.querySelectorAll('.opt')].map(o=>o.dataset.seed);
        }""")
        print("第一条", first_uid, "候选", seeds)
        await pg.locator(".card").first.locator("button.sel2").nth(1).click()
        await pg.wait_for_timeout(900)
        ok1 = await pg.evaluate("""() => {
          const c=document.querySelector('.card');
          return {done:c.classList.contains('done'), picked:document.getElementById('p-'+c.dataset.uid).textContent,
                  dn:document.getElementById('dn').textContent};
        }""")
        print("选第2个候选后:", ok1)
        print("  磁盘:", json.load(open(LAB,encoding="utf-8")) if os.path.exists(LAB) else "无")

        # 3) 键盘 3 选第 3 个候选（当前 active 应已跳到下一条未标）
        act = await pg.evaluate("""() => {const c=document.querySelector('.card.active'); return c?c.dataset.uid:null;}""")
        print("当前 active:", act)
        await pg.keyboard.press("3")
        await pg.wait_for_timeout(800)
        d = json.load(open(LAB,encoding="utf-8"))
        print("按 3 后磁盘条数:", len(d), "| 新增:", {k:v for k,v in d.items() if k!=first_uid})

        # 4) 都不行
        await pg.keyboard.press("0")
        await pg.wait_for_timeout(800)
        d = json.load(open(LAB,encoding="utf-8"))
        none_uid = [k for k,v in d.items() if v["pick"]=="none"]
        print("按 0 后 都不行 的条目:", none_uid)

        # 5) 刷新后恢复
        await pg.reload(wait_until="load"); await pg.wait_for_timeout(1200)
        rec = await pg.evaluate("""() => ({dn:document.getElementById('dn').textContent,
            done:document.querySelectorAll('.card.done').length})""")
        print("刷新后:", rec)

        await pg.screenshot(path="_chk_rate.png", clip={"x":0,"y":0,"width":1100,"height":780})
        print("pageerror:", errs[:4] or "none")
        await b.close()

asyncio.run(main())
