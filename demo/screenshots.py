"""Скриншоты функций курса для презентации (через установленный Edge). Запуск: python demo/screenshots.py asquith"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
key = sys.argv[1] if len(sys.argv) > 1 else "asquith"
url = (ROOT / "out" / key / "course" / "index.html").resolve().as_uri()
out = ROOT / "presentation" / "img"
out.mkdir(parents=True, exist_ok=True)


def shot(page, name, js, full=False, clip_sel=None):
    page.evaluate(js)
    page.wait_for_timeout(500)
    if clip_sel:
        page.locator(clip_sel).first.screenshot(path=str(out / f"{name}.png"))
    else:
        page.screenshot(path=str(out / f"{name}.png"), full_page=full)
    print(name)


with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    pg = b.new_page(viewport={"width": 1000, "height": 640}, device_scale_factor=1.6)
    pg.goto(url)
    pg.evaluate("localStorage.clear()")
    pg.reload()
    pg.evaluate("document.documentElement.dataset.theme='dark'")
    prep = "S.done={};nodes.slice(0,3).forEach(n=>S.done[n.id]=1);S.step=nodes[3].id;save();"
    shot(pg, "01_path", prep + "setView('path')")
    # шаг: верх (суть + иллюстрация)
    i = pg.evaluate("nodes.findIndex(n=>(n.course.formulas||[]).length && (n.worked_examples||[]).length)")
    i = i if i >= 0 else 2
    shot(pg, "02_step_top", f"setView('step', nodes[{i}].id); window.scrollTo(0,0)")
    # «как это работает» со стр. N
    shot(pg, "03_step_explain", "document.querySelectorAll('h2')[1].scrollIntoView({block:'start'}); window.scrollBy(0,-80)")
    # цитата автора по клику на «стр. N»
    shot(pg, "04_quote", "document.querySelector('article p .pill:not(.model)').click()")
    pg.keyboard.press("Escape")
    # формулы, примеры, данные, аналогия
    shot(pg, "05_formulas", "const h=[...document.querySelectorAll('h2')].find(x=>x.textContent.startsWith('Разбор')||x.textContent.startsWith('Понятия')); h&&h.scrollIntoView({block:'start'}); window.scrollBy(0,-80)")
    shot(pg, "06_data_analogy", "const h=[...document.querySelectorAll('h2')].find(x=>x.textContent.startsWith('Что это значит')); h&&h.scrollIntoView({block:'start'}); window.scrollBy(0,-80)")
    # задания: ответить и проверить
    j = pg.evaluate("nodes.findIndex(n=>(tasksBy['step.'+n.id]||[]).some(t=>t.type==='order'))")
    shot(pg, "07_tasks", f"""setView('step', nodes[{max(j, 0)}].id);
      const t=document.querySelectorAll('.task');t[0].scrollIntoView({{block:'start'}});window.scrollBy(0,-90);
      const r=t[0].querySelector('input[type=radio],input[type=checkbox]'); if(r) r.click();
      t[0].querySelector('.btn.primary').click();""")
    shot(pg, "08_order_task", """const t=[...document.querySelectorAll('.task')].find(x=>x.querySelector('.order'))||document.querySelector('.task');
      t.scrollIntoView({block:'start'}); window.scrollBy(0,-90);""")
    shot(pg, "09_cards", "S.cards={};nodes.slice(0,2).forEach(n=>S.cards[n.id]='k');S.cards[nodes[2].id]='r';save();setView('cards'); document.querySelectorAll('.fc .back')[0].hidden=false")
    shot(pg, "10_notes", "setView('notes')")
    shot(pg, "11_map", "setView('map')")
    # ролик внутри курса (если есть)
    has_media = pg.evaluate("Object.keys(D.media).length")
    if has_media:
        shot(pg, "12_video", "setView('step', Object.keys(D.media)[0]); const v=document.querySelector('video'); v.scrollIntoView({block:'center'})")
    # телефон
    m = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    m.goto(url)
    m.evaluate("document.documentElement.dataset.theme='dark'")
    shot(m, "13_mobile_step", f"setView('step', nodes[{i}].id); window.scrollTo(0,0)")
    shot(m, "14_mobile_task", "const t=document.querySelector('.task'); t.scrollIntoView({block:'start'})")
    # светлая тема
    shot(pg, "15_light", f"document.documentElement.dataset.theme='light'; setView('step', nodes[{i}].id); window.scrollTo(0,0)")
    b.close()
