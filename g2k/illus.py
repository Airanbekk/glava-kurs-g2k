"""Иллюстрации курса: детерминированные SVG-схемы из учебного слоя, один шаблон на тип трудности.

Никакой генерации картинок: кадр рисует код из утверждений узла, на самой картинке стоит метка происхождения.
"""
from __future__ import annotations

import html
import textwrap

W, H = 960, 540


def _wrap(s: str, width: int) -> list[str]:
    return textwrap.wrap(s or "", width=width, break_long_words=True)[:6]


def _box(x, y, w, h, title, body, color, style, small=False):
    fs = 17 if small else 19
    lines = _wrap(body, int(w / (fs * 0.52)))
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{style["panel"]}" stroke="{color}" stroke-width="3"/>']
    if title:
        out.append(f'<text x="{x + 16}" y="{y + 30}" fill="{color}" font-size="18" font-weight="700">{html.escape(title)}</text>')
    ty = y + (58 if title else 34)
    for ln in lines:
        if ty > y + h - 10:
            break
        out.append(f'<text x="{x + 16}" y="{ty}" fill="{style["text"]}" font-size="{fs}">{html.escape(ln)}</text>')
        ty += fs + 7
    return "\n".join(out)


def _arrow(x1, y1, x2, y2, color):
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="4" marker-end="url(#ah)"/>')


def _frame(inner: str, title: str, label: str, style: dict, src: str) -> str:
    prov = style.get("provenance", {}).get(label, "#8E44AD")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" font-family="Segoe UI, Arial, sans-serif">
<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{style["muted"]}"/></marker></defs>
<rect width="{W}" height="{H}" fill="{style["background"]}"/>
<text x="32" y="46" fill="{style["text"]}" font-size="26" font-weight="700">{html.escape(title[:70])}</text>
<rect x="{W - 172}" y="20" width="150" height="36" rx="18" fill="{prov}"/>
<text x="{W - 97}" y="44" fill="#fff" font-size="17" font-weight="700" text-anchor="middle">{html.escape(label)}</text>
{inner}
<text x="32" y="{H - 16}" fill="{style["muted"]}" font-size="14">{html.escape(src[:120])}</text>
</svg>'''


def _pages(claims) -> str:
    ps = sorted({c["page_pdf"] for c in claims})
    return "по главе, стр. " + ", ".join(map(str, ps[:6]))


def node_svg(node: dict, style: dict) -> tuple[str, str]:
    """-> (svg, подпись)"""
    t = node["difficulty"]["primary"]
    c = node.get("course") or {}
    claims = node.get("claims") or []
    title = c.get("novice_title") or node["title"]
    acc = style.get("measurement", {}).get("color", "#F1C40F")
    blue = style["curves"]["NEUTRON"]["color"]
    green = style["fluids"]["oil"]["color"]
    red = style["fluids"]["gas"]["color"]
    src = _pages(claims)
    inner = []
    if t == "Пр" and (c.get("procedure") or node.get("worked_examples")):
        steps = [s["text"] for s in c.get("procedure") or []] or (node["worked_examples"][0].get("steps") or [])
        steps = steps[:5]
        n = max(1, len(steps))
        bw = (W - 64 - (n - 1) * 24) / n
        for i, s in enumerate(steps):
            x = 32 + i * (bw + 24)
            inner.append(_box(x, 110, bw, 330, f"Шаг {i + 1}", s, acc if i == 0 else blue, style, small=True))
            if i < n - 1:
                inner.append(_arrow(x + bw + 2, 275, x + bw + 22, 275, style["muted"]))
        cap = "Порядок действий по главе"
    elif t == "Н" and node.get("decision_on_data"):
        d = node["decision_on_data"]
        inner.append(_box(32, 100, 280, 340, "Признаки", "; ".join(d.get("features") or []), blue, style, small=True))
        inner.append(_arrow(316, 270, 346, 270, style["muted"]))
        inner.append(_box(350, 100, 280, 340, "Правило", d.get("rule", ""), acc, style, small=True))
        inner.append(_arrow(634, 270, 664, 270, style["muted"]))
        inner.append(_box(668, 100, 260, 200, "Вывод", d.get("conclusion", ""), green, style, small=True))
        inner.append(_box(668, 312, 260, 128, "Контрпример", d.get("counterexample", ""), red, style, small=True))
        cap = "Решение на данных: признаки → правило → вывод и где оно ломается"
    elif t == "И":
        obs = [x for x in claims if x.get("kind") == "observation"][:1]
        inf = [x for x in claims if x.get("kind") == "inference"][:1]
        asm = [x for x in claims if x.get("kind") == "assumption"][:1]
        inner.append(_box(32, 100, 280, 300, "Что измеряем", (obs[0]["text"] if obs else node["layers"]["mechanism"]["text"]), acc, style, small=True))
        inner.append(_arrow(316, 250, 346, 250, style["muted"]))
        inner.append(_box(350, 100, 280, 300, "Что выводим", (inf[0]["text"] if inf else node["layers"]["main"]["text"]), green, style, small=True))
        inner.append(_arrow(634, 250, 664, 250, style["muted"]))
        inner.append(_box(668, 100, 260, 300, "При условии", (asm[0]["text"] if asm else node["layers"]["nuances"]["text"]), style["uncertainty"]["color"], style, small=True))
        inner.append(f'<text x="32" y="440" fill="{style["muted"]}" font-size="17">Измерение косвенное: один и тот же отклик могут дать разные пласты.</text>')
        cap = "Цепочка косвенного измерения: сигнал → вывод → условия"
    elif t == "Ф" and c.get("formulas"):
        f = c["formulas"][0]
        inner.append(_box(32, 96, W - 64, 120, "Что считает формула", f.get("meaning", ""), acc, style))
        y = 236
        for v in (f.get("vars") or [])[:6]:
            inner.append(f'<text x="48" y="{y}" fill="{blue}" font-size="20" font-weight="700">{html.escape(v.get("sym", ""))}</text>'
                         f'<text x="210" y="{y}" fill="{style["text"]}" font-size="19">{html.escape((v.get("meaning", "") + (" , " + v["unit"] if v.get("unit") else ""))[:70])}</text>')
            y += 36
        cap = "Смысл формулы и обозначения"
    elif t == "В":
        items = [x["text"] for x in (c.get("explain") or [])][:4]
        n = max(1, len(items))
        inner.append(f'<line x1="40" y1="470" x2="{W - 40}" y2="470" stroke="{style["muted"]}" stroke-width="3" marker-end="url(#ah)"/>')
        inner.append(f'<text x="{W - 160}" y="500" fill="{style["muted"]}" font-size="16">время →</text>')
        bw = (W - 80 - (n - 1) * 20) / n
        for i, s in enumerate(items):
            x = 40 + i * (bw + 20)
            inner.append(_box(x, 100, bw, 340, f"Этап {i + 1}", s, acc if i == 0 else blue, style, small=True))
        cap = "Последовательность событий во времени"
    else:  # М, П, Р и прочее: цепочка «причина → следствие» из механизма и вывода
        a = node["layers"]["mechanism"]["text"]
        b = node["layers"]["main"]["text"]
        cc = node["layers"]["practice"]["text"]
        inner.append(_box(32, 100, 280, 330, "Причина / механизм", a, acc, style, small=True))
        inner.append(_arrow(316, 265, 346, 265, style["muted"]))
        inner.append(_box(350, 100, 280, 330, "Следствие", b, green, style, small=True))
        inner.append(_arrow(634, 265, 664, 265, style["muted"]))
        inner.append(_box(668, 100, 260, 330, "Как используют", cc, blue, style, small=True))
        cap = "Причина → следствие → практика"
    return _frame("\n".join(inner), title, "схема", style, src), cap


def build(layer: dict, style: dict, out_dir) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    ills = []
    for n in layer["nodes"]:
        svg, cap = node_svg(n, style)
        fn = f"{n['id'].replace('.', '_')}.svg"
        (out_dir / fn).write_text(svg, encoding="utf-8")
        ills.append({
            "id": f"ill.{n['id']}", "step_id": f"step.{n['id']}", "node_id": n["id"], "file": f"assets/{fn}",
            "frame_class": "B", "origin": "code_from_model", "label": "схема",
            "caption": f"{cap}. Собрано кодом из утверждений узла.",
            "alt": f"Схема: {cap.lower()} — {(n.get('course') or {}).get('novice_title') or n['title']}",
            "source": _pages(n.get("claims") or []),
            "claim_ids": [c["id"] for c in (n.get("claims") or [])[:3]], "prompt": None,
        })
    return {"chapter": layer["chapter"], "illustrations": ills}
