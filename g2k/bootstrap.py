"""Сборка доменного пакета для нового домена (сдвиг: бурение, разработка…) по главе — за минуты, код движка не меняется.

    python run.py domain-bootstrap drilling --from-chapter test_shift
Берёт за основу domain/geo (стайлгайд, типы трудности, зрителя), а предметное (конвенции, заблуждения,
чек-лист, ИТ-мосты, словарь произношений) модель выписывает из главы нового домена.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from .chapter import Chapter
from .llm import ask_json

ROOT = Path(__file__).resolve().parent.parent


def bootstrap(name: str, chapter: Chapter, base: str = "geo", log=print) -> Path:
    t0 = time.time()
    src, dst = ROOT / "domain" / base, ROOT / "domain" / name
    dst.mkdir(parents=True, exist_ok=True)
    for f in ("styleguide.json", "viewer_portraits.md"):
        if (src / f).exists():
            shutil.copy(src / f, dst / f)
    text = chapter.text_with_units()
    base_md = (src / "domain.md").read_text(encoding="utf-8")
    user = f"""Есть доменный пакет для геологии (образец структуры):
{base_md}

Новая глава из другого домена нефтегаза: {chapter.book}
{text[:60000]}

Собери доменный пакет для домена этой главы. Зритель тот же (айтишники без отраслевого образования). Восемь типов трудности те же.
Верни JSON:
{{"domain_title": "название домена",
 "conventions": ["конвенции изображения и обозначений этого домена (направления, порядок, единицы, школа обозначений)"],
 "it_bridges": [{{"concept": "...", "analogy": "...", "breaks_where": "..."}}],
 "misconceptions": [{{"id": "misc.латиница", "text": "типичное заблуждение неспециалиста"}}],
 "physics_checklist": [{{"id": "pc.латиница", "group": "...", "item": "что должно выполняться в кадре и тексте"}}],
 "pronunciation": [{{"written": "аббревиатура", "spoken": "как читать", "meaning": "расшифровка"}}],
 "glossary": [{{"term": "...", "en": "...", "definition": "..."}}]}}
Заблуждений 10–20, пунктов чек-листа 10–20, ИТ-мостов 5–10, только то, что относится к домену главы."""
    o = ask_json("Ты — методист и отраслевой эксперт. Отвечай только JSON.", user, effort="medium", max_tokens=24000,
                 tag=f"domain_{name}_{chapter.key}")
    md = [f"# Доменный пакет: {o['domain_title']}", "",
          "Собран командой `domain-bootstrap` по главе нового домена; структура и зритель взяты из пакета geo.", "",
          base_md.split("## Конвенции")[0].split("\n", 2)[2].strip(), "", "## Конвенции"]
    md += [f"- {c}" for c in o["conventions"]]
    md += ["", base_md[base_md.index("## Восемь типов"):base_md.index("## Мосты в ИТ")].strip(), "", "## Мосты в ИТ (у каждой обязательна граница)"]
    md += [f"- {b['concept']} ↔ {b['analogy']}. Граница: {b['breaks_where']}" for b in o["it_bridges"]]
    (dst / "domain.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (dst / "misconceptions.json").write_text(json.dumps(o["misconceptions"], ensure_ascii=False, indent=1), encoding="utf-8")
    (dst / "physics_checklist.json").write_text(json.dumps(o["physics_checklist"], ensure_ascii=False, indent=1), encoding="utf-8")
    (dst / "glossary.json").write_text(json.dumps(o["glossary"], ensure_ascii=False, indent=1), encoding="utf-8")
    st = ["# Словарь произношений", "", "| Пишется | Читается | Расшифровка |", "| --- | --- | --- |"]
    st += [f"| {p['written']} | {p['spoken']} | {p['meaning']} |" for p in o["pronunciation"]]
    (dst / "stress_dict.md").write_text("\n".join(st) + "\n", encoding="utf-8")
    secs = time.time() - t0
    (dst / "BUILD.md").write_text(f"Пакет собран автоматически за {secs / 60:.1f} мин по главе {chapter.key}; ручных правок: 0.\n"
                                  f"Шаблоны сцен по типам трудности использованы без изменений.\n", encoding="utf-8")
    log(f"[домен] domain/{name} собран за {secs:.0f} с")
    return dst


def export_glossary(layers: list[dict], dom_dir: Path) -> Path:
    """Глоссарий RU/EN доменного пакета пополняется из курсов: термин → определение → стр."""
    path = dom_dir / "glossary.json"
    gl = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    seen = {g["term"].lower() for g in gl}
    for layer in layers:
        for n in layer["nodes"]:
            for g in (n.get("course") or {}).get("glossary") or []:
                if g.get("term") and g["term"].lower() not in seen:
                    seen.add(g["term"].lower())
                    gl.append({"term": g["term"], "en": g.get("en"), "definition": g.get("definition"), "source": layer["chapter"]})
    path.write_text(json.dumps(gl, ensure_ascii=False, indent=1), encoding="utf-8")
    md = ["# Глоссарий RU/EN", "", "| Термин | English | Определение | Глава |", "| --- | --- | --- | --- |"]
    md += [f"| {g['term']} | {g.get('en') or ''} | {(g.get('definition') or '').replace('|', '/')} | {g.get('source', '')} |" for g in gl]
    (dom_dir / "glossary.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return path
