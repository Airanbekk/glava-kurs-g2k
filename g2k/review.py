"""Модуль проверки: чужой пакет в общей схеме → замечания с исправлением и страницей.

Против ложных тревог три барьера:
 1) обвинение должно опираться на ДОСЛОВНУЮ цитату главы, которая противоречит элементу (проверяется кодом);
 2) второй, «скептический» проход пересматривает каждое замечание и снимает недоказанные;
 3) порог уверенности.
"""
from __future__ import annotations

import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import domain as D
from .chapter import load_md_pages
from .llm import ask_json
from .quotes import PageIndex, unsupported_numbers

CATS = ["overgeneralization", "sign_flip", "measured_vs_inferred", "lost_condition", "missing_caveat", "wrong_scaling",
        "wrong_mechanism", "outdated_as_current", "analogy_without_limit", "frame_error", "other"]
NO_QUOTE_CATS = {"analogy_without_limit", "frame_error"}

SYSTEM = """Ты — строгий научный редактор. Проверяешь черновик учебного материала по главе книги и ищешь заложенные ошибки.
Принципы:
- Эталон — только текст главы. Утверждение верно, если оно следует из главы, даже если звучит неожиданно или контринтуитивно. В пакете специально есть верные, но странно звучащие утверждения: не трогай их.
- Ошибка — это расхождение с главой: сверхобобщение («всегда», «любой» при условиях у автора), переворот знака/направления, измеренное выдано за выведенное и наоборот, потеряно условие применимости, пропущена оговорка автора, неверная зависимость/степень/масштаб, неверный механизм, устаревшее выдано за текущее, ИТ-аналогия без границы или с неверной границей, ошибка кадра/сцены.
- Обвинение доказывается дословной цитатой из главы (evidence_quote), которая показывает, как правильно. Нет такой цитаты — нет замечания (кроме аналогий и кадров).
- Ошибок около пятой части. Если сомневаешься — помечай как верное.
Отвечай только JSON."""

ITEM_FORMAT = """{"verdicts": [{"id": "C001", "ok": true}, {"id": "C002", "ok": false, "category": "lost_condition", "severity": "critical|significant|minor",
 "problem": "что не так, кратко", "fix": "исправленная формулировка", "page_pdf": 12, "evidence_quote": "дословная цитата главы, подтверждающая исправление", "confidence": 0.0-1.0}]}"""


def _pages_text(pages: dict[int, str], nums) -> str:
    return "\n\n".join(f"<!-- page {n} -->\n{pages[n].strip()}" for n in sorted(set(nums)) if n in pages)


def run(pkg_path: Path, md_path: Path, dom: dict, workers: int = 8, min_conf: float = 0.6) -> dict:
    pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    pages = load_md_pages(md_path)
    pidx = PageIndex(pages)
    items = pkg["items"]
    by_id = {it["id"]: it for it in items}
    spec = json.dumps([s.get("spec") for s in pkg.get("scenes", [])], ensure_ascii=False)
    checklist = D.checklist_text(dom)
    conventions = json.dumps(dom["style"].get("conventions", {}), ensure_ascii=False)

    # детерминированные сигналы: цитата не на своей странице, числа без опоры
    signals = {}
    for it in items:
        s = []
        if it.get("quote") and it.get("page_pdf"):
            if not pidx.verify(it["quote"], it["page_pdf"]):
                hits = pidx.exact_pages(it["quote"])
                s.append(f"цитата не найдена дословно на стр. {it['page_pdf']}" + (f" (есть на стр. {hits})" if hits else ""))
            nums = unsupported_numbers(it.get("text", ""), [it["quote"], pages.get(it["page_pdf"], "")])
            if nums:
                s.append(f"числа {sorted(nums)} не встречаются в цитате и на странице")
        if s:
            signals[it["id"]] = "; ".join(s)

    # группы по узлу: контекст = страницы утверждений группы ±1
    groups = defaultdict(list)
    for it in items:
        groups[it.get("node_id", "_")].append(it)

    def item_pages(it):
        ps = set()
        if it.get("page_pdf"):
            ps |= {it["page_pdf"] - 1, it["page_pdf"], it["page_pdf"] + 1}
        ref = by_id.get(it.get("claim_ref") or "")
        if ref and ref.get("page_pdf"):
            ps |= {ref["page_pdf"], ref["page_pdf"] + 1}
        return ps

    node_pages = defaultdict(set)
    for it in items:
        if it.get("page_pdf"):
            node_pages[it.get("node_id")].add(it["page_pdf"])

    def check_group(key):
        grp = groups[key]
        ps = set()
        for it in grp:
            ps |= item_pages(it)
        if not ps:
            for p in node_pages.get(key, []):
                ps |= {p - 1, p, p + 1}
        if not ps:
            ps = set(list(pages)[:4])
        lines = []
        for it in grp:
            d = {k: it[k] for k in ("id", "type", "text", "kind", "page_pdf", "quote", "breaks_where", "claim_ref", "on_screen", "spec_path") if k in it}
            if it.get("claim_ref") in by_id:
                ref = by_id[it["claim_ref"]]
                d["claim_ref_text"] = ref.get("text")
                d["claim_ref_page"] = ref.get("page_pdf")
            if it["id"] in signals:
                d["сигнал_проверки_кода"] = signals[it["id"]]
            lines.append(json.dumps(d, ensure_ascii=False))
        user = f"""ТЕКСТ ГЛАВЫ (страницы по меткам):
{_pages_text(pages, ps)}

Чек-лист физической корректности домена:
{checklist}
Конвенции легенды: {conventions}

{"Спецификация сцены ролика:" + spec if any(it["type"] in ("scene_fact", "script_line") for it in grp) else ""}

ЭЛЕМЕНТЫ ДЛЯ ПРОВЕРКИ (утверждения claim, ИТ-аналогии analogy, фразы закадра script_line, факты сцены scene_fact):
{chr(10).join(lines)}

Для каждого элемента вынеси вердикт. Для script_line сверяй с утверждением claim_ref и главой: голос не должен говорить больше источника и не должен обобщать. Для analogy проверь, что граница названа и верна. Для scene_fact — с главой, чек-листом и конвенциями.
«сигнал_проверки_кода» — подсказка, не приговор: страницу и число проверь сам.
page_pdf в замечании — страница главы, где стоит цитата-доказательство; для script_line — страница утверждения claim_ref.
Формат ответа:
{ITEM_FORMAT}"""
        obj = ask_json(SYSTEM, user, role="review", effort="high", max_tokens=32000, tag=f"rev_{pkg['package_id']}_{key}".replace("/", "_"))
        return obj.get("verdicts", [])

    with ThreadPoolExecutor(workers) as ex:
        verdicts = [v for lst in ex.map(check_group, list(groups)) for v in lst]

    # кадры: по одному запросу с картинкой
    script = [it for it in items if it["type"] == "script_line"]

    def frame_page(fr):
        t = fr.get("t", 0)
        best = min(script, key=lambda s: 0 if s["t_start"] <= t <= s["t_end"] else min(abs(t - s["t_start"]), abs(t - s["t_end"])), default=None)
        if best and best.get("claim_ref") in by_id:
            return by_id[best["claim_ref"]].get("page_pdf"), best
        return None, best

    def check_frame(fr):
        img = pkg_path.parent / fr["file"]
        page, line = frame_page(fr)
        user = f"""Кадр ролика {fr.get('video_id')} в момент t={fr.get('t')} с.
Метаданные кадра: {json.dumps(fr, ensure_ascii=False)}
Фраза закадра в этот момент: {json.dumps(line, ensure_ascii=False) if line else '—'}
Утверждение, которое иллюстрирует кадр (стр. {page}): {json.dumps(by_id.get((line or {}).get('claim_ref'), {}), ensure_ascii=False)}
Спецификация сцены: {spec}
Чек-лист: {checklist}
Конвенции легенды: {conventions}
Правила меток: метка происхождения на каждом кадре («реальные данные», «симуляция», «схема»; сгенерированная картинка — «иллюстрация ИИ»); класс A — данные, B — процесс из расчёта, C — внешний вид, D — атмосфера; преувеличение масштаба подписывается.

Сравни изображение с описанием, спецификацией, главой и конвенциями: глубина растёт вниз, газ над нефтью над водой, верная метка и класс, подписанное преувеличение, кривая согласована с разрезом, подписи не противоречат главе.
Верни JSON: {{"ok": true}} или {{"ok": false, "category": "frame_error", "severity": "...", "problem": "...", "fix": "что должно быть в кадре", "confidence": 0.0-1.0}}"""
        obj = ask_json(SYSTEM, user, role="review", images=[img], effort="high", max_tokens=8000, tag=f"revf_{pkg['package_id']}_{fr['id']}")
        obj["id"] = fr["id"]
        if not obj.get("ok"):
            obj["page_pdf"] = page
        return obj

    frames = pkg.get("frames", [])
    with ThreadPoolExecutor(workers) as ex:
        verdicts += list(ex.map(check_frame, frames))

    # барьер 1: доказательство цитатой
    flagged = []
    for v in verdicts:
        if v.get("ok", True):
            continue
        cat = v.get("category") if v.get("category") in CATS else "other"
        v["category"] = cat
        if float(v.get("confidence", 0.7)) < min_conf:
            continue
        it = by_id.get(v["id"])
        if cat not in NO_QUOTE_CATS and not v["id"].startswith("F"):
            q = v.get("evidence_quote") or ""
            q2, p2, st = pidx.repair(q, v.get("page_pdf"))
            if st == "failed":
                continue
            v["evidence_quote"], v["page_pdf"] = q2, p2
            if it and it.get("type") == "script_line" and it.get("claim_ref") in by_id:
                v["page_pdf"] = by_id[it["claim_ref"]].get("page_pdf") or p2
        flagged.append(v)

    # барьер 2: скептический пересмотр
    def skeptic(v):
        it = by_id.get(v["id"]) or next((f for f in frames if f["id"] == v["id"]), {})
        ps = set()
        if v.get("page_pdf"):
            ps |= {v["page_pdf"] - 1, v["page_pdf"], v["page_pdf"] + 1}
        ps |= item_pages(it) if it else set()
        user = f"""ТЕКСТ ГЛАВЫ:
{_pages_text(pages, ps)}

Элемент: {json.dumps(it, ensure_ascii=False)}
{('Утверждение-источник: ' + json.dumps(by_id.get(it.get('claim_ref')), ensure_ascii=False)) if it.get('claim_ref') else ''}
Предлагаемое замечание: {json.dumps(v, ensure_ascii=False)}

Ты — второй рецензент. Замечание стоит оставлять, только если элемент действительно противоречит главе или теряет её условие/оговорку, и исправление верно. Если элемент верен (пусть и звучит неожиданно), замечание — ложная тревога.
Верни JSON: {{"keep": true/false, "reason": "...", "category": "уточнённая категория из списка {CATS}", "severity": "critical|significant|minor", "fix": "уточнённое исправление"}}"""
        obj = ask_json(SYSTEM, user, role="review", effort="high", max_tokens=6000, tag=f"revs_{pkg['package_id']}_{v['id']}")
        return v, obj

    with ThreadPoolExecutor(workers) as ex:
        reviewed = list(ex.map(skeptic, [v for v in flagged if not v["id"].startswith("F")]))
    remarks = []
    for v, s in reviewed:
        if not s.get("keep"):
            continue
        cat = s.get("category") if s.get("category") in CATS else v["category"]
        remarks.append({"target": v["id"], "category": cat, "severity": s.get("severity") or v.get("severity", "significant"),
                        "problem": v.get("problem", ""), "fix": s.get("fix") or v.get("fix", ""), "page_pdf": v.get("page_pdf"),
                        "quote": v.get("evidence_quote")})
    for v in flagged:
        if v["id"].startswith("F"):
            remarks.append({"target": v["id"], "category": "frame_error", "severity": v.get("severity", "significant"),
                            "problem": v.get("problem", ""), "fix": v.get("fix", ""), "page_pdf": v.get("page_pdf"), "quote": None})
    order = {it["id"]: i for i, it in enumerate(items)}
    remarks.sort(key=lambda r: order.get(r["target"], 10_000))
    return {"package_id": pkg["package_id"], "team": "g2k", "remarks": remarks}
