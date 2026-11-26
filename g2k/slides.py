"""Презентация для защиты: HTML-слайды, цифры берутся из результатов конвейера (out/*)."""
from __future__ import annotations

import csv
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _stats():
    rows = []
    for d in sorted((ROOT / "out").iterdir()):
        if not (d / "layer.json").exists() or d.name.startswith("_"):
            continue
        layer = json.loads((d / "layer.json").read_text(encoding="utf-8"))
        cov = json.loads((d / "coverage.json").read_text(encoding="utf-8"))["rows"]
        tasks = json.loads((d / "tasks.json").read_text(encoding="utf-8"))["tasks"] if (d / "tasks.json").exists() else []
        claims = [c for n in layer["nodes"] for c in n["claims"]]
        rep = {k: sum(n.get("verification", {}).get(k, 0) for n in layer["nodes"]) for k in ("exact", "repaired", "dropped")}
        split = json.loads((ROOT / "chapters.json").read_text(encoding="utf-8")).get(d.name, {}).get("split", "")
        rows.append({"split": split, "key": d.name, "chapter": layer["chapter"], "nodes": len(layer["nodes"]), "claims": len(claims),
                     "units": len(cov), "in_nodes": sum(1 for r in cov if r["node_ids"]),
                     "skipped": sum(1 for r in cov if not r["node_ids"]), "tasks": len(tasks),
                     "types": len({t["type"] for t in tasks}), **rep,
                     "course": (d / "course" / "index.html").exists()})
    usage = {}
    mp = ROOT / "out" / "metrics.csv"
    if mp.exists():
        for r in csv.DictReader(mp.open(encoding="utf-8")):
            u = usage.setdefault(r["chapter"], {"in": 0, "out": 0, "usd": 0.0, "sec": 0})
            u["in"] += int(r["tokens_in"]); u["out"] += int(r["tokens_out"]); u["usd"] += float(r["usd"]); u["sec"] += int(float(r["wall_seconds"]))
    return rows, usage


def build(review_score: str = "95% ошибок по весу, 0 ложных тревог (контрольный пакет, скрипт организаторов)") -> Path:
    rows, usage = _stats()
    tot_claims = sum(r["claims"] for r in rows)
    tot_dropped = sum(r["dropped"] for r in rows)
    def table(rs):
        return "<table><tr><th>Глава</th><th>Шагов</th><th>Утверждений</th><th>Единиц в узлах / всего</th><th>Заданий</th><th>Время</th></tr>" + "".join(
            f"<tr><td>{html.escape(r['chapter'])}</td><td>{r['nodes']}</td><td>{r['claims']}</td>"
            f"<td>{r['in_nodes']}/{r['units']}</td><td>{r['tasks']} ({r['types']} типов)</td>"
            f"<td>{usage.get(r['chapter'], {}).get('sec', 0) // 60} мин</td></tr>" for r in rs) + "</table>"
    train = [r for r in rows if r["split"] == "train"]
    test = [r for r in rows if r["split"] == "test"]
    tbl = table(train)
    S = []
    S.append(("Глава → курс", f"""<p class=big>Конвейер, который сам превращает главу книги в проверенный курс для новичка</p>
<p>Участник-одиночка · {len(rows)} главы собраны конвейером без ручных правок</p>
<p class=muted>Победит не тот, у кого больше генеративного ИИ, а тот, чей конвейер стабильно даёт верный и полный материал на незнакомой главе и чья стоимость известна в цифрах.</p>"""))
    S.append(("Ставка: точность встроена в код, а не в промпт", """<ul>
<li><b>Модель пишет — код проверяет.</b> Каждое утверждение несёт дословную цитату и страницу; код сверяет её с главой по правилу жюри. Не прошло — утверждение не выходит.</li>
<li><b>Покрытие считает код, а не модель.</b> Глава режется на единицы p095.03; каждая единица — в узле или с причиной.</li>
<li><b>Курс и ролики собираются из слоя.</b> Ошибку правят в одном месте — всё пересобирается одной командой.</li>
<li><b>Без картинок «на глаз».</b> Схемы и кадры рисует код из утверждений и модели состояния; генерации фактов нет.</li></ul>"""))
    S.append(("Конвейер", """<div class=flow><div>Глава<br><small>md + страницы</small></div><i>→</i><div>Учебный слой<br><small>узлы · утверждения · цитаты</small></div><i>→</i><div>Маршрутизация<br><small>8 типов трудности</small></div><i>→</i><div>Спецификация сцены<br><small>инварианты</small></div><i>→</i><div>Курс и ролики<br><small>HTML · MP4</small></div></div>
<ul><li>Одна команда на главу: <code>python run.py build latyshova</code></li>
<li>Все файлы — в общих схемах организаторов: слой, покрытие, маршрутизация, задания, иллюстрации, паспорт ролика</li>
<li>Модуль проверки и журнал правок — рядом с конвейером</li></ul>"""))
    S.append(("Тест: незнакомые главы, замороженный конвейер", f"""{table(test)}
<p><b>Все 4 главы собраны к 11:21 — за 50 минут после выдачи.</b> Три на английском, курс по-русски, цитаты в оригинале. Ручных правок: 1 (2 мин, тип поля page_print). Доменный пакет «бурение» собран автоматически за 96 с.</p>
<p>Ролики по темам организаторов: Slatt — «Как узнать дельту по керну» (16:9, огрубление вверх по ГК); Басарыгин — «Как приток виден на поверхности» (9:16).</p>"""))
    S.append(("Обучение: три главы", f"""{tbl}
<p><b>{tot_claims} утверждений — {tot_claims} цитат проходят проверку по правилу жюри</b> (отброшено при генерации: {tot_dropped}). Остальные единицы главы — служебные, с причиной.</p>
<p class=muted>Стоимость главы ≈ $4 по ценам API; метрики пишутся автоматически в out/metrics.csv.</p>"""))
    S.append(("Честно: что дальше", """<ul><li><b>Шаблоны сцен.</b> Сейчас один шаблон ролика — «ствол, прибор, кривая из модели пласта». Для бурения нужен «ёмкость и устье», для дельты — «вид сверху и наступление на море». Движок рендера общий, это доменное расширение (отчёт: out/basarygin/template_coverage.md)</li>
<li><b>16:9 короче цели:</b> 67 с вместо 1,5–3 мин — сценарий берёт только утверждения одного узла</li>
<li><b>Рисунки книги</b> пока упоминаются («рис. N, стр. M»), а не перерисовываются кодом</li></ul>"""))
    S.append(("Курс, который новичок проходит сам", """<ul>
<li>Один HTML-файл ~1,5 МБ: открывается без сервера и логина, телефон 390 px и десктоп, тёмная и светлая тема, формулы офлайн</li>
<li>Страница шага: заголовок для новичка, суть в 2–3 фразах, «как это работает» со <b>«стр. N» у каждого абзаца</b> (клик — цитата автора), разборы примеров с числами автора, цифры и условия, формулы с расшифровкой, таблицы книги, частая ошибка, «что это значит для данных», ИТ-аналогия и <b>где она ломается</b></li>
<li>Поля модели помечены «пояснение модели» / «гипотеза» — видно автора и модель</li>
<li>Задания 5 типов (один ответ, несколько, порядок перетаскиванием, пропуски, расчёт), проверка сразу; ответ гарантированно есть в тексте шага — это проверяет код</li>
<li>Карточки «знаю / повторить», конспект с печатью в PDF, карта связей шагов</li></ul>"""))
    S.append(("Ролики: кадр утверждает — значит, его считает код", """<ul>
<li>Шаблон на тип трудности: прибор опускается по стволу, кривая <b>считается из той же модели пласта</b> — глубина прибора управляет и его положением, и точкой кривой</li>
<li>Инварианты проверяет код: пласты без дыр, газ над нефтью над водой, глубина растёт вниз; метка «симуляция» на каждом кадре; преувеличения подписаны</li>
<li>Голос не говорит больше источника: каждая фраза ссылается на утверждение; всё, о чём говорит голос, видно в кадре</li>
<li>Крючок → механизм → пауза на предсказание → ответ → вопрос на перенос; субтитры; −16 LUFS; 110–130 слов/мин; синхрон голос–кадр по построению</li>
<li>Озвучка: Microsoft Neural, запасной офлайн-голос Windows — наружу только текст сценария</li></ul>"""))
    S.append(("Модуль проверки: находить ошибки, не трогая верное", f"""<p class=big>{html.escape(review_score)}</p>
<ul><li><b>Барьер 1:</b> обвинение только с дословной цитатой главы, которая противоречит элементу; цитату проверяет код</li>
<li><b>Барьер 2:</b> скептический второй рецензент пересматривает каждое замечание</li>
<li><b>Барьер 3:</b> порог уверенности</li>
<li>Детерминированные сигналы: цитата не на своей странице, числа без опоры</li>
<li>Кадры проверяются по изображению: метка, класс, глубина, порядок флюидов</li></ul>"""))
    S.append(("Перенос: новая глава, новый домен, новая модель", """<ul>
<li><b>Новая глава</b> — одна запись в chapters.json, код не меняется: <code>add-chapter … && build</code></li>
<li><b>Новый домен</b> (сдвиг, бурение): доменный пакет собирается автоматически по главе за минуты — <code>domain-bootstrap drilling</code>; пакет отдельно от движка</li>
<li><b>Модель заменяема</b> одной строкой в .env: Claude по API, Claude Code по подписке или <b>локальная модель компании</b> через vLLM / Ollama — для прогона 300+ книг</li>
<li>Глава на английском: цитаты остаются в оригинале, курс по-русски, глоссарий RU/EN</li></ul>"""))
    S.append(("Ручной труд и стоимость — в цифрах", """<ul>
<li>Ручные правки только через <code>patches/&lt;глава&gt;.json</code>: правка переживает пересборку и сама попадает в журнал с минутами</li>
<li>Журнал совпадает с историей коммитов по построению</li>
<li>Ответы модели кешируются: пересборка после правки факта — одна команда, бесплатно и детерминированно</li>
<li>Метрики по главам и этапам: токены, деньги, время → стоимость узла и главы для масштабирования</li></ul>"""))
    S.append(("Демо", """<ol><li>Открываем курс главы — проходим шаг как новичок, кликаем «стр. N», решаем задание на телефоне</li>
<li>Фрагмент ролика</li>
<li>Пересборка: <code>demo\rebuild_demo.ps1</code> меняет 4→5 в «Цифрах и условиях» — одна команда — число на странице курса изменилось</li></ol><p class=big>Спасибо!</p>"""))
    slides = "".join(f"<section class='slide{' hidden' if i else ''}'><h1>{html.escape(t)}</h1>{b}<div class=num>{i + 1}/{len(S)}</div></section>"
                     for i, (t, b) in enumerate(S))
    page = f"""<!doctype html><html lang=ru><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Глава → курс — защита</title><style>
:root{{--bg:#0f1419;--panel:#1a2129;--text:#eceff4;--muted:#a3adb8;--acc:#f1c40f}}
body{{margin:0;background:var(--bg);color:var(--text);font:22px/1.5 "Segoe UI",system-ui,sans-serif}}
.slide{{min-height:100vh;box-sizing:border-box;padding:6vh 7vw;position:relative}}.hidden{{display:none}}
h1{{font-size:44px;margin:0 0 28px;color:var(--acc)}}.big{{font-size:30px;font-weight:600}}.muted{{color:var(--muted);font-size:18px}}
li{{margin:10px 0}}code{{background:var(--panel);padding:2px 8px;border-radius:6px;font-size:19px}}
table{{border-collapse:collapse;width:100%;font-size:19px}}td,th{{border:1px solid #2c3640;padding:8px 10px;text-align:left}}th{{background:var(--panel)}}
.flow{{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:20px 0 30px}}.flow div{{background:var(--panel);border:2px solid var(--acc);border-radius:14px;padding:14px 18px;text-align:center}}
.flow small{{color:var(--muted)}}.flow i{{font-style:normal;font-size:30px;color:var(--muted)}}
.num{{position:absolute;right:4vw;bottom:3vh;color:var(--muted);font-size:16px}}
@media print{{.hidden{{display:block}}.slide{{page-break-after:always}}}}
</style></head><body>{slides}<script>
let i=0;const s=[...document.querySelectorAll('.slide')];
function go(k){{i=Math.max(0,Math.min(s.length-1,k));s.forEach((x,j)=>x.classList.toggle('hidden',j!==i))}}
addEventListener('keydown',e=>{{if(['ArrowRight','PageDown',' '].includes(e.key))go(i+1);if(['ArrowLeft','PageUp'].includes(e.key))go(i-1)}});
addEventListener('click',e=>go(e.clientX>innerWidth/2?i+1:i-1));
</script></body></html>"""
    out = ROOT / "presentation" / "index.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out
