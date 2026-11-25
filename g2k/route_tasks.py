"""Шаг 2. Маршрутизация (детерминированно, по типу трудности и видеоёмкости) и задания курса (модель + проверка кодом)."""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import domain as D
from .llm import ask_json
from .quotes import norm

ROOT = Path(__file__).resolve().parent.parent
TASK_SCHEMA = json.loads((ROOT / "schemas" / "task.schema.json").read_text(encoding="utf-8"))

TEMPLATES = {  # шаблон сцены по типу трудности: один шаблон на тип, а не уникальное решение на узел
    "М": "tpl_mechanism_chain", "В": "tpl_timeline", "И": "tpl_signal_response_property",
    "Ф": "tpl_formula_sliders", "П": "tpl_section_views", "Пр": "tpl_procedure_flow",
    "Н": "tpl_decision_range", "Р": "tpl_feature_cards",
}


def route(layer: dict) -> dict:
    routes = []
    for n in layer["nodes"]:
        vs = n.get("video_scores") or {}
        vs = {k: int(max(0, min(2, vs.get(k, 0)))) for k in ("time", "invisible", "scale", "counterintuitive", "cause_effect")}
        s = sum(vs.values())
        t = n["difficulty"]["primary"]
        sec = None
        if n.get("decision_on_data"):
            fmt, sec = "практикум на данных", ("шортс" if s >= 6 else None)
        elif t in ("М", "В"):
            fmt = "длинное видео" if s >= 8 else ("шортс" if s >= 5 else "интерактив")
        elif t == "И":
            fmt, sec = ("шортс", "практикум на данных") if s >= 5 else ("интерактив", None)
        elif t in ("Ф", "П"):
            fmt, sec = "интерактив", ("шортс" if s >= 6 else None)
        elif t in ("Пр", "Н"):
            fmt = "интерактив"
        elif t == "Р":
            fmt = "карточки"
        else:
            fmt = "текст"
        why = (f"Тип трудности {t}" + (f"/{n['difficulty'].get('secondary')}" if n['difficulty'].get('secondary') else "")
               + f"; видеоёмкость {s}/10 (время {vs['time']}, невидимое {vs['invisible']}, масштаб {vs['scale']}, "
               f"контринтуитивность {vs['counterintuitive']}, причина→следствие {vs['cause_effect']})"
               + ("; есть решение на данных" if n.get("decision_on_data") else "") + f" → {fmt}.")
        routes.append({"node_id": n["id"], "format": fmt, "secondary_format": sec, "video_scores": vs,
                       "hook_short": False, "template": TEMPLATES.get(t), "why": why})
    return {"chapter": layer["chapter"], "routes": routes}


# ---------------------------------------------------------------- задания

def step_text(n: dict) -> str:
    c = n.get("course") or {}
    parts = [c.get("novice_title", ""), n.get("title", "")] + list(c.get("essence") or [])
    for sec in ("explain", "procedure", "numbers"):
        parts += [x.get("text", "") for x in c.get(sec) or []]
    parts += [f"{g.get('term')} — {g.get('definition')}" for g in c.get("glossary") or []]
    for w in n.get("worked_examples") or []:
        parts += [w.get("condition", "")] + list(w.get("steps") or []) + [w.get("result", "")]
    if n.get("misconception"):
        parts.append(n["misconception"].get("text", ""))
    dm = n.get("data_meaning") or {}
    parts += [dm.get("from_chapter", {}).get("text", ""), dm.get("breaks", {}).get("text", "")]
    parts += [c2.get("text", "") for c2 in n.get("claims") or []]
    return "\n".join(p for p in parts if p)


def _types_for(n: dict, k: int, rot: int) -> list[str]:
    c = n.get("course") or {}
    pool = ["single", "multiple", "gap"]
    if len(c.get("procedure") or []) >= 3 or any(len(w.get("steps") or []) >= 3 for w in n.get("worked_examples") or []):
        pool.insert(0, "order")
    if n.get("worked_examples") or c.get("formulas") or c.get("numbers"):
        pool.insert(0, "calc" if (n.get("worked_examples") or c.get("formulas")) else "single")
    out = []
    for j in range(k):
        out.append(pool[(rot + j) % len(pool)])
    return out


def _task_validate(n: dict, step_id: str, dom: dict):
    cids = {c["id"] for c in n["claims"]}
    misc = {m["id"] for m in dom["misconceptions"]}
    text_n = norm(step_text(n))

    def v(obj):
        errs = []
        for t in obj.get("tasks", []):
            tid = t.get("id", "?")
            if t.get("type") not in ("single", "multiple", "order", "gap", "calc"):
                errs.append(f"{tid}: неверный type")
                continue
            if not set(t.get("claim_ids") or []) <= cids or not t.get("claim_ids"):
                errs.append(f"{tid}: claim_ids должны быть из списка утверждений узла")
            opts = {o.get("id") for o in t.get("options") or []}
            for o in t.get("options") or []:
                if o.get("misconception") and o["misconception"] not in misc:
                    errs.append(f"{tid}: неизвестное заблуждение {o['misconception']}")
            a = t.get("answer")
            if t["type"] == "single" and (a not in opts or len(opts) < 3):
                errs.append(f"{tid}: single — answer = id одного из ≥3 вариантов")
            if t["type"] == "multiple" and (not isinstance(a, list) or not set(a) <= opts or len(a) < 2 or len(opts) < 4):
                errs.append(f"{tid}: multiple — answer = список ≥2 id из ≥4 вариантов")
            if t["type"] == "order" and (not isinstance(a, list) or set(a) != opts or len(a) < 3):
                errs.append(f"{tid}: order — answer = все id вариантов в верном порядке (≥3)")
            if t["type"] == "gap":
                gaps = re.findall(r"\{\{(\d+)\}\}", t.get("prompt", ""))
                if not isinstance(a, list) or len(gaps) != len(a) or not gaps:
                    errs.append(f"{tid}: gap — число пропусков {{{{n}}}} должно совпадать с длиной answer")
                else:
                    for w in a:
                        if norm(str(w)) not in text_n:
                            errs.append(f"{tid}: слово «{w}» для пропуска не встречается в тексте шага")
            if t["type"] == "calc":
                try:
                    float(str(a).replace(",", "."))
                except ValueError:
                    errs.append(f"{tid}: calc — answer должен быть числом")
            if not t.get("explanation"):
                errs.append(f"{tid}: нет пояснения")
        return errs[:12]
    return v


def normalize_task(t: dict) -> dict:
    """Приведение к общей схеме: пустые поля — пустые списки/None, а не отсутствие."""
    if not isinstance(t.get("options"), list):
        t["options"] = []
    for o in t["options"]:
        o.setdefault("misconception", None)
    if t.get("kind") not in ("recall", "understanding", "transfer", "data"):
        t.pop("kind", None)
    return t


def make_tasks(layer: dict, dom: dict, workers: int = 8, log=print) -> dict:
    nodes = layer["nodes"]
    per = 3 if len(nodes) < 8 else 2
    misc_txt = D.misconceptions_text(dom)

    def one(i):
        n = nodes[i]
        types = _types_for(n, per, i)
        step_id = f"step.{n['id']}"
        claims = "\n".join(f"{c['id']}: {c['text']}" for c in n["claims"])
        user = f"""Шаг курса для новичка (айтишник без геологии). Ответы на задания ДОЛЖНЫ содержаться в тексте шага.

ТЕКСТ ШАГА:
{step_text(n)}

УТВЕРЖДЕНИЯ (на них ссылается claim_ids):
{claims}

Заблуждения (неверные варианты строй на них, поле misconception):
{misc_txt}

Сделай {per} задания типов: {', '.join(types)}. Требования:
- single: 3–4 варианта, один верный; answer = id варианта.
- multiple: 4–5 вариантов, 2–3 верных; answer = список id.
- order: 3–6 элементов, которые нужно расставить по порядку (шаги процедуры/цепочка причин); answer = id в верном порядке; в options порядок перемешан.
- gap: текст с пропусками {{{{1}}}}, {{{{2}}}}; answer = список слов ровно как в тексте шага.
- calc: расчёт по формуле или числам автора; answer = число; укажи tolerance и unit.
- Неверные варианты правдоподобны, построены на типичных заблуждениях или потере условия.
- explanation — одна фраза: почему верно, со ссылкой на мысль шага.
- kind: recall | understanding | transfer | data.

Верни JSON: {{"tasks": [{{"id": "t1", "type": "...", "kind": "...", "prompt": "...", "options": [{{"id": "a", "text": "...", "misconception": null}}], "answer": ..., "tolerance": null, "unit": null, "explanation": "...", "claim_ids": ["..."]}}]}}"""
        obj = ask_json("Ты — автор проверочных заданий для онлайн-курса. Отвечай только JSON.", user,
                       validate=_task_validate(n, step_id, dom), effort="low", max_tokens=12000, tag=f"tasks_{n['id']}")
        out = []
        for j, t in enumerate(obj["tasks"]):
            t["id"] = f"{n['id']}.t{j + 1}"
            t["step_id"] = step_id
            out.append(normalize_task(t))
        return out

    with ThreadPoolExecutor(workers) as ex:
        tasks = [t for lst in ex.map(one, range(len(nodes))) for t in lst]
    types = {t["type"] for t in tasks}
    log(f"[задания] {len(tasks)} заданий, типов {len(types)}: {sorted(types)}")
    return {"chapter": layer["chapter"], "tasks": tasks}
