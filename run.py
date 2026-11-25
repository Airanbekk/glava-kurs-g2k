"""Конвейер «Глава → курс». Одна команда на главу:

    python run.py build latyshova            # слой → покрытие → маршрутизация → задания → иллюстрации → курс
    python run.py build latyshova --stage course   # пересобрать только курс из готового слоя (после правки факта)
    python run.py check latyshova            # проверка всех файлов по общим схемам + отчёт о цитатах
    python run.py review inputs/pack/control/package.json --md inputs/pack/control/vendelshtein_gl1.md
    python run.py add-chapter --key test1 --md path.md --pages 10-25 --prefix test1 --lang en --domain geo
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from g2k import domain as D  # noqa: E402
from g2k import llm  # noqa: E402
from g2k.chapter import load_chapter  # noqa: E402

SCHEMAS = {
    "layer.json": "node.schema.json", "coverage.json": "coverage.schema.json", "routing.json": "routing.schema.json",
    "tasks.json": "task.schema.json", "illustrations.json": "illustration.schema.json",
}


def cfg_all() -> dict:
    return {k: v for k, v in json.loads((ROOT / "chapters.json").read_text(encoding="utf-8")).items() if not k.startswith("_")}


def wj(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def rj(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def metric(chapter: str, stage: str, nodes: int, secs: float, extra: dict | None = None):
    p = ROOT / "out" / "metrics.csv"
    new = not p.exists()
    with p.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "chapter", "stage", "nodes", "llm_calls", "llm_cached", "tokens_in", "tokens_out", "usd",
                        "wall_seconds", "person_minutes", "model", "note"])
        u = llm.USAGE
        w.writerow([dt.datetime.now().isoformat(timespec="minutes"), chapter, stage, nodes, u["calls"], u["cached"],
                    u["in"], u["out"], round(u["usd"], 3), round(secs), 0, llm.describe(), json.dumps(extra or {}, ensure_ascii=False)])
    llm.reset_usage()


def apply_patches(key: str, layer: dict) -> int:
    """Ручные правки факта — только через patches/<key>.json, чтобы они пережили пересборку и попали в журнал."""
    p = ROOT / "patches" / f"{key}.json"
    if not p.exists():
        return 0
    patches = rj(p)
    claims = {c["id"]: c for n in layer["nodes"] for c in n["claims"]}
    nodes = {n["id"]: n for n in layer["nodes"]}
    k = 0
    for pt in patches:
        tgt = claims.get(pt["target"]) or nodes.get(pt["target"])
        if tgt is None:
            print(f"[правки] не найдена цель {pt['target']}")
            continue
        obj = tgt
        path = pt["field"].split(".")
        for part in path[:-1]:
            obj = obj[int(part)] if isinstance(obj, list) else obj[part]
        last = path[-1]
        if isinstance(obj, list):
            obj[int(last)] = pt["value"]
        else:
            obj[last] = pt["value"]
        k += 1
        _log_edit(key, pt)
    return k


def _log_edit(key: str, pt: dict):
    """Каждая правка из patches/ один раз попадает в журнал manual_edits.csv с минутами."""
    j = ROOT / "manual_edits.csv"
    tag = f"{pt['target']}.{pt['field']}"
    rows = j.read_text(encoding="utf-8") if j.exists() else ""
    if tag in rows:
        return
    with j.open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([pt.get("time") or dt.datetime.now().isoformat(timespec="minutes"), cfg_all()[key]["chapter"],
                                f"patches/{key}.json", f"{tag}: {str(pt['value'])[:80]}", pt.get("minutes", 1), 1,
                                pt.get("run_no", 1), pt.get("reason", "")])


def cmd_build(a):
    from g2k import course, illus, layer as L, route_tasks as RT
    cfg = cfg_all()[a.key]
    ch = load_chapter(a.key, cfg, ROOT)
    dom = D.load(cfg.get("domain", "geo"))
    out = ROOT / "out" / a.key
    stages = ["layer", "tasks", "course"]
    start = stages.index(a.stage)
    t0 = time.time()
    if start <= 0:
        layer, coverage, plan = L.build_layer(ch, dom, workers=a.workers)
        wj(out / "layer.raw.json", layer)
        wj(out / "coverage.json", coverage)
        wj(out / "plan.json", plan)
        v = {k: sum(n["verification"][k] for n in layer["nodes"]) for k in ("exact", "moved", "repaired", "dropped", "number_flags")}
        print(f"[слой] цитаты: {v}; покрытие: {coverage['summary']}")
        metric(ch.chapter_id, "layer", len(layer["nodes"]), time.time() - t0, {"quotes": v, "coverage": coverage["summary"]})
    layer = rj(out / "layer.raw.json")
    n_p = apply_patches(a.key, layer)
    if n_p:
        print(f"[правки] применено правок: {n_p}")
    wj(out / "layer.json", layer)
    routing = RT.route(layer)
    wj(out / "routing.json", routing)
    t1 = time.time()
    if start <= 1 or not (out / "tasks.json").exists():
        tasks = RT.make_tasks(layer, dom, workers=a.workers)
        wj(out / "tasks.json", tasks)
        metric(ch.chapter_id, "course", len(layer["nodes"]), time.time() - t1, {"tasks": len(tasks["tasks"])})
    tasks = rj(out / "tasks.json")
    tasks["tasks"] = [RT.normalize_task(t) for t in tasks["tasks"]]
    wj(out / "tasks.json", tasks)
    cdir = out / "course"
    ills = illus.build(layer, dom["style"], cdir / "assets")
    wj(out / "illustrations.json", ills)
    media = rj(out / "media.json") if (out / "media.json").exists() else {}
    page = course.build(ch, layer, tasks, routing, ills, cdir, media=media)
    print(f"[курс] {page}  ({page.stat().st_size / 1e6:.2f} МБ)")
    cmd_check(argparse.Namespace(key=a.key))


def cmd_check(a):
    import jsonschema
    out = ROOT / "out" / a.key
    ok = True
    for f, s in SCHEMAS.items():
        p = out / f
        if not p.exists():
            print(f"  {f}: нет файла")
            ok = False
            continue
        schema = rj(ROOT / "schemas" / s)
        errs = list(jsonschema.Draft202012Validator(schema).iter_errors(rj(p)))
        print(f"  {f}: {'OK' if not errs else f'{len(errs)} ошибок схемы'}")
        for e in errs[:5]:
            print(f"     {'/'.join(map(str, e.path))}: {e.message[:160]}")
        ok &= not errs
    if (out / "layer.json").exists():
        from g2k.quotes import PageIndex
        cfg = cfg_all()[a.key]
        ch = load_chapter(a.key, cfg, ROOT)
        pi = PageIndex(ch.pages)
        layer = rj(out / "layer.json")
        claims = [c for n in layer["nodes"] for c in n["claims"]]
        bad = [c["id"] for c in claims if not pi.verify(c["quote"], c["page_pdf"])]
        tasks = rj(out / "tasks.json")["tasks"] if (out / "tasks.json").exists() else []
        cov = rj(out / "coverage.json")["rows"] if (out / "coverage.json").exists() else []
        print(f"  узлов {len(layer['nodes'])}, утверждений {len(claims)}, цитат не по правилу жюри: {len(bad)}")
        print(f"  заданий {len(tasks)}, типов {len({t['type'] for t in tasks})}; единиц главы {len(cov)}, без узла и без причины: "
              f"{sum(1 for r in cov if not r['node_ids'] and (not r['reason'] or 'не распределена' in r['reason']))}")
        ok &= not bad
    print("ИТОГ:", "OK" if ok else "есть замечания")


def cmd_review(a):
    from g2k import review
    pkg = Path(a.package)
    md = Path(a.md) if a.md else pkg.parent / rj(pkg)["chapter_file"]
    out = Path(a.out) if a.out else ROOT / "out" / "review" / f"{rj(pkg)['package_id']}.answer.json"
    t0 = time.time()
    ans = review.run(pkg, md, D.load(a.domain), workers=a.workers)
    wj(out, ans)
    print(f"[проверка] замечаний: {len(ans['remarks'])} → {out}")
    metric(rj(pkg)["package_id"], "review", 0, time.time() - t0, {"remarks": len(ans["remarks"])})


def cmd_video(a):
    from g2k import video
    cfg = cfg_all()[a.key]
    dom = D.load(cfg.get("domain", "geo"))
    out = ROOT / "out" / a.key
    layer, routing = rj(out / "layer.json"), rj(out / "routing.json")
    t0 = time.time()
    res = video.build(layer, routing, dom, out / "course" / "media", aspect=a.aspect, node_id=a.node)
    media = rj(out / "media.json") if (out / "media.json").exists() else {}
    media[res["node_id"]] = {k: res[k] for k in ("src", "vtt", "title")}
    wj(out / "media.json", media)
    metric(layer["chapter"], "video", 1, time.time() - t0, {"seconds": res["passport"]["audio_check"]["duration_s"]})
    cmd_build(argparse.Namespace(key=a.key, stage="course", workers=a.workers))


def cmd_domain(a):
    from g2k import bootstrap
    cfg = cfg_all()[a.from_chapter]
    ch = load_chapter(a.from_chapter, cfg, ROOT)
    t0 = time.time()
    bootstrap.bootstrap(a.name, ch, base=a.base)
    metric(ch.chapter_id, "domain", 0, time.time() - t0, {"domain": a.name})
    c = rj(ROOT / "chapters.json")
    c[a.from_chapter]["domain"] = a.name
    wj(ROOT / "chapters.json", c)
    print(f"глава {a.from_chapter} теперь собирается с доменом {a.name}")


def cmd_glossary(a):
    from g2k import bootstrap
    layers = [rj(p) for p in sorted((ROOT / "out").glob("*/layer.json"))
              if cfg_all().get(p.parent.name, {}).get("domain", "geo") == a.domain]
    p = bootstrap.export_glossary(layers, ROOT / "domain" / a.domain)
    print(f"глоссарий: {p} ({len(rj(p))} терминов)")


def cmd_slides(a):
    from g2k import slides
    print(f"презентация: {slides.build()}")


def cmd_add(a):
    p = ROOT / "chapters.json"
    cfg = rj(p)
    pages = []
    for part in a.pages.split(","):
        x, y = part.split("-")
        pages.append([int(x), int(y)])
    cfg[a.key] = {"chapter": a.chapter or a.key, "md": a.md, "pages": pages, "prefix": a.prefix or a.key,
                  "book": a.book or a.key, "language": a.lang, "domain": a.domain, "split": a.split}
    wj(p, cfg)
    print(f"добавлена глава {a.key}")


def main():
    ap = argparse.ArgumentParser(description="Конвейер «Глава → курс»")
    sp = ap.add_subparsers(dest="cmd", required=True)
    b = sp.add_parser("build"); b.add_argument("key"); b.add_argument("--stage", default="layer", choices=["layer", "tasks", "course"]); b.add_argument("--workers", type=int, default=None)
    c = sp.add_parser("check"); c.add_argument("key")
    r = sp.add_parser("review"); r.add_argument("package"); r.add_argument("--md"); r.add_argument("--out"); r.add_argument("--domain", default="geo"); r.add_argument("--workers", type=int, default=None)
    v = sp.add_parser("video"); v.add_argument("key"); v.add_argument("--aspect", default="9:16", choices=["9:16", "16:9"]); v.add_argument("--node"); v.add_argument("--workers", type=int, default=None)
    db = sp.add_parser("domain-bootstrap"); db.add_argument("name"); db.add_argument("--from-chapter", required=True); db.add_argument("--base", default="geo")
    gl = sp.add_parser("glossary"); gl.add_argument("--domain", default="geo")
    sp.add_parser("slides")
    d = sp.add_parser("add-chapter")
    for k in ("key", "md", "pages"):
        d.add_argument(f"--{k}", required=True)
    for k in ("chapter", "prefix", "book"):
        d.add_argument(f"--{k}")
    d.add_argument("--lang", default="ru"); d.add_argument("--domain", default="geo"); d.add_argument("--split", default="test")
    a = ap.parse_args()
    if getattr(a, "workers", 1) is None:
        a.workers = llm.DEFAULT_WORKERS
    print(f"[модель] {llm.describe()}; параллельных запросов: {getattr(a, 'workers', '-')}")
    {"build": cmd_build, "check": cmd_check, "review": cmd_review, "video": cmd_video, "domain-bootstrap": cmd_domain, "glossary": cmd_glossary, "slides": cmd_slides, "add-chapter": cmd_add}[a.cmd](a)


if __name__ == "__main__":
    main()
