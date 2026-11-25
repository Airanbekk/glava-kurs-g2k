"""Шаг 1. Учебный слой: план узлов (с покрытием по единицам) → узлы с утверждениями → проверка цитат кодом."""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import jsonschema

from . import domain as D
from .chapter import Chapter
from .llm import ask_json, describe
from .quotes import PageIndex, unsupported_numbers

ROOT = Path(__file__).resolve().parent.parent
NODE_SCHEMA = json.loads((ROOT / "schemas" / "node.schema.json").read_text(encoding="utf-8"))
DIFF = ["М", "В", "И", "Ф", "П", "Пр", "Н", "Р"]

SYSTEM = """Ты — методист и предметный редактор. Ты превращаешь главу технической книги в учебный слой для новичка.
Главные правила:
1. Только то, что есть в главе. Всё, чего нет в главе, помечается by_model=true и hypothesis=true.
2. Цитата (quote) — ДОСЛОВНЫЙ непрерывный фрагмент текста главы (можно отличаться только пробелами и регистром), 8–40 слов, с той страницы, что указана в page_pdf (метка <!-- page N -->). Не склеивай куски, не исправляй опечатки и OCR, не переводи.
3. Ничего не пропускай как «непоказуемое»: каждая мысль, условие, оговорка, число, пример и задача автора должны попасть в утверждения.
4. Сохраняй условия применимости и оговорки автора, не обобщай («всегда», «любой») там, где у автора есть условия. Различай измеренное (observation) и выведенное (inference).
5. Пиши по-русски, ясно, фразы до 20 слов, термины объясняй при первом появлении.
Отвечай только JSON без пояснений."""


# ---------------------------------------------------------------- план узлов

def _expand(chapter: Chapter, items: list[str]) -> list[str]:
    ids = [u.unit_id for u in chapter.units]
    pos = {u: i for i, u in enumerate(ids)}
    out = []
    for it in items:
        it = it.strip()
        if ".." in it:
            a, b = [x.strip() for x in it.split("..", 1)]
            if a in pos and b in pos and pos[a] <= pos[b]:
                out.extend(ids[pos[a]: pos[b] + 1])
        elif it in pos:
            out.append(it)
    return out


def plan(chapter: Chapter, dom: dict) -> dict:
    n_units = len(chapter.units)
    target = max(6, min(22, round(len(chapter.pages) * 0.8)))
    user = f"""Доменный контекст:
{dom['domain_md']}

Глава: {chapter.book}
Ниже текст главы; каждая единица (абзац, формула, таблица, рисунок) помечена id вида [p095.03].

{chapter.text_with_units()}

Задача: разбей главу на учебные узлы (примерно {target}, допустимо {max(4, target - 4)}–{target + 6}). Узел — одна идея, которую новичок осваивает за один шаг 3–7 минут. Порядок узлов — порядок изучения (предпосылки раньше).
Каждая единица главы должна попасть ровно в один узел (поле units) ИЛИ в skipped с конкретной причиной (колонтитул, номер страницы, оглавление, повтор, библиография, мусор OCR). «Непоказуемо» — не причина: формулы, таблицы, рисунки, примеры и задачи входят в узлы.
В units можно писать диапазоны подряд идущих единиц: "p090.03..p091.02".

Типы трудности: М механизм, В геологическое время, И косвенное измерение, Ф формализм/модель, П пространство, Пр процедура, Н неопределённость/решение, Р распознавание.

Верни JSON:
{{"nodes": [{{"slug": "латиница_через_подчёркивание", "title": "название по книге", "novice_title": "заголовок для новичка, 3–7 слов", "units": ["p090.01..p090.05"], "difficulty": {{"primary": "И", "secondary": "Н" или null}}, "threshold": true/false (пороговая идея, без которой дальше непонятно), "prerequisites": ["slug"]}}],
 "skipped": [{{"unit_id": "p090.01", "reason": "колонтитул"}}]}}"""

    def validate(obj):
        errs = []
        seen = {}
        for nd in obj.get("nodes", []):
            if not re.fullmatch(r"[a-z0-9_]+", nd.get("slug", "")):
                errs.append(f"slug {nd.get('slug')!r} должен быть [a-z0-9_]")
            if nd.get("difficulty", {}).get("primary") not in DIFF:
                errs.append(f"узел {nd.get('slug')}: неверный тип трудности")
            for u in _expand(chapter, nd.get("units", [])):
                seen.setdefault(u, nd.get("slug"))
        for s in obj.get("skipped", []):
            if s.get("unit_id") and "непоказуем" not in (s.get("reason") or ""):
                seen.setdefault(s["unit_id"], "_skip")
        missing = [u.unit_id for u in chapter.units if u.unit_id not in seen]
        if len(missing) > max(2, n_units * 0.02):
            errs.append(f"не распределены единицы ({len(missing)}): {', '.join(missing[:60])}")
        slugs = [nd.get("slug") for nd in obj.get("nodes", [])]
        if len(set(slugs)) != len(slugs):
            errs.append("slug узлов повторяются")
        return errs

    obj = ask_json(SYSTEM, user, validate=validate, effort="high", max_tokens=48000, tag=f"plan_{chapter.key}")
    for nd in obj["nodes"]:
        nd["units"] = _expand(chapter, nd["units"])
        nd["id"] = f"{chapter.prefix}.{nd['slug']}"
    return obj


# ---------------------------------------------------------------- узел

NODE_FORMAT = """{
 "title": "...", "why_here": {"text": "зачем этот шаг именно здесь", "by_model": true},
 "difficulty": {"primary": "И", "secondary": null}, "threshold": false, "pages": [95, 96],
 "layers": {"topic": {"text","by_model"}, "main": {"text": "главное в 1–2 фразах","by_model"}, "mechanism": {...}, "practice": {...}, "nuances": {...}, "deeper": [{"text","by_model"}]},
 "claims": [{"id": "c1", "text": "утверждение своими словами", "kind": "observation|inference|assumption", "page_pdf": 95, "page_print": null, "quote": "дословная цитата", "source_kind": "text|formula|table|task|figure_caption|figure_description_model", "by_model": false}],
 "links": [{"type": "prerequisite|example_of|refutes_misconception|to_data", "target": "id узла / misc.* / data.*", "note": "..."}],
 "misconception": {"ref": "misc.* или null", "text": "заблуждение, которое исправляет шаг", "by_model": true} или null,
 "data_meaning": {"from_chapter": {"text","by_model"}, "breaks": {"text": "где ломается в данных","by_model"}, "hypotheses": [{"text","by_model": true,"hypothesis": true}]},
 "it_analogy": {"text": "аналогия из ИТ/данных", "breaks_where": "где аналогия перестаёт работать", "by_model": true},
 "now_practice": {"text": "как это делают сейчас", "by_model": true, "hypothesis": true} или null,
 "inefficiency_lens": {"inputs","manual_steps","judgment_points","time","typical_errors","by_model": true} или null (обязательно для процедур Пр),
 "terms_introduced": ["..."], "terms_used": ["..."],
 "needs_scan": [{"page": 97, "what": "рис. 41 — без скана смысл теряется"}],
 "decision_on_data": {"features": ["..."], "rule": "...", "conclusion": "...", "counterexample": "..."} или null,
 "worked_examples": [{"page_pdf": 97, "condition": "условие с числами автора", "steps": ["..."], "result": "итог с числами автора", "figure": "рис. N, стр. M" или null}],
 "book_tasks": [{"number": "1", "page_pdf": 98, "text": "формулировка", "figure": null}],
 "video_scores": {"time": 0-2, "invisible": 0-2, "scale": 0-2, "counterintuitive": 0-2, "cause_effect": 0-2},
 "course": {
   "novice_title": "3–7 слов для новичка",
   "essence": ["2–3 фразы; первая — главное"],
   "explain": [{"text": "абзац «как это работает»: фразы до 20 слов, термины объяснены", "claims": ["c1","c2"]}],
   "procedure": [{"text": "шаг процедуры автора", "claims": ["c3"]}],
   "numbers": [{"text": "порог/диапазон/условие применимости с числами автора", "claims": ["c4"]}],
   "formulas": [{"tex": "LaTeX только из главы", "meaning": "что считает", "vars": [{"sym": "\\\\rho_п", "meaning": "...", "unit": "Ом·м"}], "claims": ["c5"]}],
   "glossary": [{"term": "...", "en": "английский термин", "definition": "...", "claims": ["c1"]}],
   "tables": [{"unit_id": "p096.04", "title": "что в таблице"}],
   "figures": [{"page": 97, "ref": "рис. 41", "what": "что изображено и зачем"}]
 }
}"""


def _node_validate(chapter: Chapter, pidx: PageIndex, node_id: str, all_ids: set[str], dom: dict):
    misc_ids = {m["id"] for m in dom["misconceptions"]}

    def validate(obj):
        errs = []
        claims = obj.get("claims") or []
        if not claims:
            return ["нет утверждений"]
        cids = set()
        bad = []
        for c in claims:
            cids.add(c.get("id"))
            q, p, st = pidx.repair(c.get("quote", ""), c.get("page_pdf"))
            if st == "failed":
                bad.append(f"{c.get('id')} (стр. {c.get('page_pdf')}): «{c.get('quote', '')[:80]}»")
        if len(bad) > max(1, len(claims) * 0.15):
            errs.append("цитаты не найдены в тексте главы дословно: " + " | ".join(bad[:10]))
        course = obj.get("course") or {}
        ess = course.get("essence") or []
        if not 2 <= len(ess) <= 3:
            errs.append("course.essence: нужно 2–3 фразы")
        nt = (course.get("novice_title") or "").split()
        if not 2 <= len(nt) <= 8:
            errs.append("course.novice_title: 3–7 слов")
        if not course.get("explain"):
            errs.append("course.explain пуст")
        for sec in ("explain", "procedure", "numbers", "formulas", "glossary"):
            for item in course.get(sec) or []:
                for r in item.get("claims") or []:
                    if r not in cids:
                        errs.append(f"course.{sec}: ссылка на несуществующее утверждение {r}")
        for l in obj.get("links") or []:
            t = l.get("target", "")
            if l.get("type") == "refutes_misconception" and t not in misc_ids:
                errs.append(f"links: неизвестное заблуждение {t}")
            if l.get("type") in ("prerequisite", "example_of") and t not in all_ids:
                errs.append(f"links: неизвестный узел {t}")
        return errs[:12]

    return validate


def build_node(chapter: Chapter, pidx: PageIndex, dom: dict, plan_obj: dict, i: int) -> dict:
    nd = plan_obj["nodes"][i]
    node_id = nd["id"]
    all_ids = {n["id"] for n in plan_obj["nodes"]}
    outline = "\n".join(f"{k + 1}. {n['id']} — {n['title']}" for k, n in enumerate(plan_obj["nodes"]))
    uids = nd["units"]
    ids = [u.unit_id for u in chapter.units]
    if uids:
        a, b = ids.index(uids[0]), ids.index(uids[-1])
        ctx_before = ids[max(0, a - 3): a]
        ctx_after = ids[b + 1: b + 4]
    else:
        ctx_before = ctx_after = []
    user = f"""Доменный контекст:
{dom['domain_md']}

Известные заблуждения (для misconception.ref, links refutes_misconception и ловушек):
{D.misconceptions_text(dom)}

Глава: {chapter.book}
План всех узлов главы (для связей prerequisite/example_of используй эти id):
{outline}

Текущий узел: {node_id} — «{nd['title']}» (для новичка: «{nd.get('novice_title', '')}»), тип трудности {nd['difficulty']}, пороговый: {nd.get('threshold')}.

Контекст до узла (только для понимания):
{chapter.text_with_units(ctx_before)}

=== ТЕКСТ УЗЛА (всё отсюда должно войти в утверждения) ===
{chapter.text_with_units(uids)}
=== КОНЕЦ ТЕКСТА УЗЛА ===

Контекст после узла (только для понимания):
{chapter.text_with_units(ctx_after)}

Собери узел учебного слоя. Требования:
- claims: покрой КАЖДУЮ мысль, условие, оговорку, число, пример и задачу текста узла; обычно 6–25 утверждений. Цитаты — дословно из ТЕКСТА УЗЛА, с правильной страницей.
- course.explain — полное объяснение всех мыслей автора для новичка-айтишника, каждый абзац со ссылками на утверждения.
- worked_examples и book_tasks — все разобранные примеры и задачи автора из текста узла, с числами автора.
- formulas — только формулы из главы, с расшифровкой всех обозначений.
- Поля, написанные тобой, а не взятые из книги, — by_model: true; догадки — hypothesis: true.
- video_scores — оценка видеоёмкости узла по 5 критериям (0–2).

Формат ответа (JSON одного узла):
{NODE_FORMAT}"""
    obj = ask_json(SYSTEM, user, validate=_node_validate(chapter, pidx, node_id, all_ids, dom), effort="medium",
                   max_tokens=48000, tag=f"node_{node_id}")
    return finalize_node(obj, nd, i + 1, chapter, pidx)


def finalize_node(obj: dict, nd: dict, order: int, chapter: Chapter, pidx: PageIndex) -> dict:
    node_id = nd["id"]
    obj["id"] = node_id
    obj["order"] = order
    obj["difficulty"] = obj.get("difficulty") or nd["difficulty"]
    obj.setdefault("threshold", bool(nd.get("threshold")))
    # проверка и ремонт цитат; перенумерация id утверждений
    remap, kept, report = {}, [], {"exact": 0, "moved": 0, "repaired": 0, "dropped": 0, "number_flags": 0}
    for c in obj.get("claims", []):
        q, p, st = pidx.repair(c.get("quote", ""), c.get("page_pdf"))
        if st == "failed":
            report["dropped"] += 1
            continue
        report[st] += 1
        n = len(kept) + 1
        new_id = f"{node_id}#c{n}"
        remap[c.get("id")] = new_id
        c.update(id=new_id, quote=q, page_pdf=p)
        c.setdefault("page_print", None)
        c.setdefault("by_model", False)
        nums = unsupported_numbers(c.get("text", ""), [chapter.page_text(p), q])
        if nums:
            c["number_check"] = f"числа {sorted(nums)} не найдены на стр. {p}"
            report["number_flags"] += 1
        kept.append(c)
    obj["claims"] = kept
    course = obj.setdefault("course", {})
    for sec in ("explain", "procedure", "numbers", "formulas", "glossary"):
        for item in course.get(sec) or []:
            item["claims"] = [remap[r] for r in item.get("claims") or [] if r in remap]
    obj["pages"] = sorted({c["page_pdf"] for c in kept} | set(obj.get("pages") or []))
    obj["units"] = nd["units"]
    obj["verification"] = report
    il = obj.get("inefficiency_lens")
    if isinstance(il, dict):  # схема требует строки: списки склеиваем
        for k in ("inputs", "manual_steps", "judgment_points", "time", "typical_errors"):
            v = il.get(k, "")
            il[k] = "; ".join(map(str, v)) if isinstance(v, list) else str(v)
        il.setdefault("by_model", True)
    for k in ("links", "terms_introduced", "terms_used", "needs_scan", "worked_examples", "book_tasks"):
        obj.setdefault(k, [])
    for k in ("misconception", "now_practice", "inefficiency_lens", "decision_on_data"):
        obj.setdefault(k, None)
    return obj


def build_layer(chapter: Chapter, dom: dict, workers: int = 8, log=print) -> tuple[dict, dict, dict]:
    pidx = PageIndex(chapter.pages)
    log(f"[слой] план узлов: {chapter.key} ({len(chapter.units)} единиц)")
    p = plan(chapter, dom)
    log(f"[слой] узлов: {len(p['nodes'])}; генерирую узлы параллельно ({workers})")
    with ThreadPoolExecutor(workers) as ex:
        nodes = list(ex.map(lambda i: build_node(chapter, pidx, dom, p, i), range(len(p["nodes"]))))
    layer = {
        "chapter": chapter.chapter_id,
        "source": chapter.md,
        "pdf_pages": [str(n) for n in chapter.pages],
        "generated_by": f"g2k pipeline / {describe()}",
        "nodes": nodes,
    }
    errs = [f"{'/'.join(map(str, e.path))}: {e.message}" for e in jsonschema.Draft202012Validator(NODE_SCHEMA).iter_errors(layer)]
    if errs:
        log(f"[слой] ВНИМАНИЕ: {len(errs)} нарушений схемы: {errs[:5]}")
    coverage = build_coverage(chapter, p, nodes)
    return layer, coverage, p


def build_coverage(chapter: Chapter, p: dict, nodes: list[dict]) -> dict:
    owner = {}
    for nd in p["nodes"]:
        for u in nd["units"]:
            owner.setdefault(u, []).append(nd["id"])
    reasons = {s["unit_id"]: s.get("reason") for s in p.get("skipped", [])}
    rows = []
    for u in chapter.units:
        nids = owner.get(u.unit_id, [])
        rows.append({
            "unit_id": u.unit_id, "kind": u.kind, "page_pdf": u.page, "excerpt": u.excerpt,
            "node_ids": nids,
            "reason": None if nids else (reasons.get(u.unit_id) or "не распределена моделью — требует проверки"),
        })
    covered = sum(1 for r in rows if r["node_ids"])
    skipped_ok = sum(1 for r in rows if not r["node_ids"] and r["unit_id"] in reasons)
    return {"chapter": chapter.chapter_id, "rows": rows,
            "summary": {"units": len(rows), "in_nodes": covered, "skipped_with_reason": skipped_ok,
                        "unassigned": len(rows) - covered - skipped_ok}}
