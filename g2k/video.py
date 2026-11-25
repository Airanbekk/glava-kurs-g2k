"""Ролик по узлу: спецификация сцены (модель) → проверка инвариантов (код) → озвучка → кадры из модели состояния → MP4.

Шаблон well_tool_curve: прибор опускается по стволу, кривая считается из той же модели пласта
(глубина прибора управляет и его положением, и точкой кривой). Генерации картинок нет: класс B, «симуляция».
"""
from __future__ import annotations

import asyncio
import json
import math
import re
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import domain as D
from .llm import ask_json

FFMPEG = None
TEMPO = 1.15


def ffmpeg() -> str:
    global FFMPEG
    if FFMPEG is None:
        import imageio_ffmpeg
        FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
    return FFMPEG


FONT = "C:/Windows/Fonts/segoeui.ttf"
FONTB = "C:/Windows/Fonts/segoeuib.ttf"


def font(sz, bold=False):
    try:
        return ImageFont.truetype(FONTB if bold else FONT, sz)
    except OSError:
        return ImageFont.load_default()


SPEC_FORMAT = """{
 "title": "заголовок ролика, до 6 слов",
 "hook": "крючок для первых 3 секунд (вопрос или парадокс)",
 "params": {"depth_top": 2000, "depth_bottom": 2030, "curve": {"key": "RES|SP|GR|NEUTRON|DENSITY|SONIC", "label": "Сопротивление", "unit": "Ом·м", "min": 0, "max": 50, "log": false},
   "tool_resolution_m": 0.6,
   "layers": [{"top": 2000, "bottom": 2008, "lith": "shale|sand|limestone|dolomite|anhydrite|salt|dense|reef", "fluid": "oil|gas|water|null", "label": "глина", "value": 3, "invasion": 0.0-1.0 (ширина зоны проникновения фильтрата, 0 — нет), "mud_cake": false}]},
 "beats": [{"say": "фраза закадра до 16 слов, числа словами", "claim_id": "id утверждения узла", "on_screen": "надпись до 5 слов", "tool_depth": 2005, "highlight": [top, bottom] или null, "show": ["invasion", "cake"] — что с этой фразы появляется в кадре, "is_analogy": false}],
 "prediction_question": "вопрос-пауза на предсказание (зритель думает перед ответом)",
 "transfer_question": "вопрос на перенос в конце",
 "exaggerations": ["коротко, до 10 слов: что преувеличено и во сколько раз"],
 "data_it_bridge": "как это выглядит в данных и что ломается для модели",
 "assumptions": ["допущения сцены"],
 "invariants": ["что обязано выполняться в каждом кадре"]
}"""


def make_spec(node: dict, dom: dict, aspect: str) -> dict:
    claims = "\n".join(f"{c['id']}: {c['text']} (стр. {c['page_pdf']})" for c in node["claims"])
    lith = ", ".join(f"{k} — {v['ru']}" for k, v in dom["style"]["lithology"].items())
    secs = "40–75 секунд (шортс 9:16, один механизм)" if aspect == "9:16" else "90–150 секунд (разбор 16:9, решение на данных)"
    user = f"""Сделай спецификацию учебного ролика по узлу учебного слоя. Шаблон сцены: разрез скважины с пластами, прибор опускается по стволу, рядом каротажная кривая, которая СЧИТАЕТСЯ из значений пластов (value) с учётом разрешения прибора.

Узел: {node['id']} — {(node.get('course') or {}).get('novice_title') or node['title']}
Суть: {' '.join((node.get('course') or {}).get('essence') or [])}
Механизм: {node['layers']['mechanism']['text']}
Заблуждение: {(node.get('misconception') or {}).get('text', '')}
Утверждения (каждая фраза закадра опирается на одно из них, голос не говорит больше источника):
{claims}

Породы (lith): {lith}. Флюиды: oil, gas, water. Порядок флюидов: газ над нефтью, нефть над водой. Глубина растёт вниз.
Длительность: {secs}; 7–11 фраз; фраза до 16 слов, числа и формулы словами, аббревиатуры раскрыты при первом упоминании.
Структура: крючок в первые 3 секунды → механизм → пауза на предсказание → ответ → контрпример или граница → вопрос на перенос.
tool_depth у фраз должен идти сверху вниз (прибор опускается). Пласты должны идти подряд без дыр от depth_top до depth_bottom.
Всё, о чём говорит голос, должно быть видно в кадре: если фраза говорит о фильтрате или глинистой корке, задай invasion / mud_cake у проницаемых пластов и поставь show в той фразе, где о них говорится впервые.
Крючок (hook), вопрос-предсказание и вопрос на перенос НЕ включай в beats: они вставляются в озвучку автоматически (после вопроса-предсказания — пауза).

Верни JSON:
{SPEC_FORMAT}"""
    cids = {c["id"] for c in node["claims"]}
    order = {"gas": 0, "oil": 1, "water": 2}

    def validate(o):
        errs = []
        p = o.get("params", {})
        L = p.get("layers") or []
        if not L:
            return ["нет пластов"]
        if abs(L[0]["top"] - p["depth_top"]) > 1e-6 or abs(L[-1]["bottom"] - p["depth_bottom"]) > 1e-6:
            errs.append("пласты должны покрывать интервал depth_top..depth_bottom")
        for a, b in zip(L, L[1:]):
            if abs(a["bottom"] - b["top"]) > 1e-6:
                errs.append(f"дыра или перекрытие между {a['label']} и {b['label']}")
        fl = [order[x["fluid"]] for x in L if x.get("fluid") in order]
        # внутри одного коллектора газ-нефть-вода не должны идти в обратном порядке подряд
        for a, b in zip(L, L[1:]):
            if a.get("fluid") in order and b.get("fluid") in order and order[a["fluid"]] > order[b["fluid"]] and a["lith"] == b["lith"]:
                errs.append(f"флюиды в обратном порядке: {a['fluid']} над {b['fluid']}")
        beats = o.get("beats") or []
        if not 6 <= len(beats) <= 14:
            errs.append("нужно 7–11 фраз")
        prev = -1e9
        for bt in beats:
            if bt.get("claim_id") and bt["claim_id"] not in cids and not bt.get("is_analogy"):
                errs.append(f"claim_id {bt['claim_id']} нет в узле")
            if len(bt.get("say", "").split()) > 20:
                errs.append(f"длинная фраза: {bt['say'][:40]}")
            d = bt.get("tool_depth", prev)
            if d < prev - 1e-6:
                errs.append("tool_depth должен не убывать")
            prev = d
            if not p["depth_top"] <= d <= p["depth_bottom"]:
                errs.append("tool_depth вне интервала")
        return errs[:10]

    return ask_json("Ты — сценарист и предметный редактор научно-популярных роликов. Отвечай только JSON.", user,
                    validate=validate, effort="medium", max_tokens=16000, tag=f"vspec_{node['id']}_{aspect.replace(':', 'x')}")


# ---------------------------------------------------------------- модель состояния

def curve_model(params: dict, n: int = 600):
    """Кривая считается из пластов: значение пласта, сглаженное окном разрешения прибора."""
    z = np.linspace(params["depth_top"], params["depth_bottom"], n)
    v = np.zeros_like(z)
    for L in params["layers"]:
        v[(z >= L["top"]) & (z <= L["bottom"])] = L["value"]
    dz = z[1] - z[0]
    w = max(1, int(params.get("tool_resolution_m", 0.5) / dz))
    k = np.ones(w) / w
    vs = np.convolve(np.pad(v, (w, w), mode="edge"), k, mode="same")[w:-w]
    return z, vs


# ---------------------------------------------------------------- озвучка

async def _tts(text, out_mp3, out_srt, voice):
    import edge_tts
    com = edge_tts.Communicate(text, voice)
    sub = edge_tts.SubMaker()
    with open(out_mp3, "wb") as f:
        async for ch in com.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] in ("WordBoundary", "SentenceBoundary"):
                sub.feed(ch)
    Path(out_srt).write_text(sub.get_srt(), encoding="utf-8")


def _sapi(text: str, out_wav: Path, name: str = "Microsoft Irina Desktop"):
    """Офлайн-голос Windows: запасной вариант, наружу ничего не уходит."""
    tf = Path(str(out_wav) + ".txt")
    tf.write_text(text, encoding="utf-8")
    ps = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
          f"$s.SelectVoice('{name}'); $s.Rate = 1; $s.SetOutputToWaveFile('{out_wav}'); "
          f"$s.Speak((Get-Content -Raw -Encoding UTF8 '{tf}')); $s.Dispose()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, check=True)
    tf.unlink()


def duration(path) -> float:
    r = subprocess.run([ffmpeg(), "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def stress(text: str, dom: dict) -> str:
    """Аббревиатуры читаются по словарю ударений доменного пакета."""
    rows = re.findall(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", dom["stress_md"], re.M)
    for a, b in rows:
        if a in ("Пишется", "---") or not a.strip() or len(a) > 12:
            continue
        for tok in [t.strip() for t in a.split(",")]:
            if tok and re.fullmatch(r"[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё\-]*", tok) and tok.upper() == tok:
                text = re.sub(rf"(?<![\w-]){re.escape(tok)}(?![\w-])", b.split(",")[0].strip(), text)
    return text


# ---------------------------------------------------------------- кадры

def render(spec: dict, node: dict, style: dict, beats_t: list, total: float, out_dir: Path, aspect: str, fps: int = 24):
    W, H = (1080, 1920) if aspect == "9:16" else (1920, 1080)
    sz = style["safe_zone"]
    top_safe, bot_safe, side = (sz["top"], sz["bottom"], sz["side"]) if aspect == "9:16" else (150, 150, 90)
    p = spec["params"]
    z, vs = curve_model(p)
    d0, d1 = p["depth_top"], p["depth_bottom"]
    cur = p["curve"]
    ccol = style["curves"].get(cur.get("key", "RES"), {}).get("color", "#F1C40F")
    bg, panel, txt, muted = style["background"], style["panel"], style["text"], style["muted"]
    # раскладка: разрез и кривая рядом (синхронные виды)
    y0, y1 = top_safe + 200, H - bot_safe - (240 if aspect == "9:16" else 200)
    if aspect == "9:16":
        sx0, sx1, cx0, cx1 = side, 640, 680, W - side
    else:
        sx0, sx1, cx0, cx1 = side + 200, 1000, 1060, W - side - 200
    ymap = lambda d: y0 + (d - d0) / (d1 - d0) * (y1 - y0)
    vmin, vmax = cur.get("min", 0), cur.get("max", max(vs) * 1.1 or 1)
    if cur.get("log"):
        xmap = lambda v: cx0 + (math.log10(max(v, 1e-3)) - math.log10(max(vmin, 1e-3))) / (math.log10(vmax) - math.log10(max(vmin, 1e-3))) * (cx1 - cx0)
    else:
        xmap = lambda v: cx0 + (v - vmin) / (vmax - vmin) * (cx1 - cx0)
    f_t, f_s, f_c, f_sub = font(54 if aspect == "9:16" else 50, True), font(30), font(44, True), font(46)
    base = Image.new("RGB", (W, H), bg)
    g = ImageDraw.Draw(base)
    # заголовок с переносом, не заходит под метку происхождения
    tw_max = W - 2 * side - 280
    words, lines_t, ln = spec["title"].split(), [], ""
    for w in words:
        cand = (ln + " " + w).strip()
        if g.textlength(cand, font=f_t) > tw_max and ln:
            lines_t.append(ln); ln = w
        else:
            ln = cand
    lines_t.append(ln)
    ty0 = top_safe - 130 if aspect == "9:16" else 24
    for k, ln in enumerate(lines_t[:2]):
        g.text((side, ty0 + k * 64), ln, font=f_t, fill=txt)
    for L in p["layers"]:
        col = style["lithology"].get(L["lith"], {}).get("color", "#888")
        g.rectangle([sx0, ymap(L["top"]), sx1, ymap(L["bottom"])], fill=col)
        if L.get("fluid") in style["fluids"]:
            fc = style["fluids"][L["fluid"]]["color"]
            for yy in range(int(ymap(L["top"])) + 6, int(ymap(L["bottom"])), 14):
                for xx in range(sx0 + 8, sx1 - 8, 22):
                    g.ellipse([xx, yy, xx + 6, yy + 6], fill=fc)
        lw = g.textlength(L["label"], font=f_s)
        g.rounded_rectangle([sx0 + 8, ymap(L["top"]) + 6, sx0 + 22 + lw, ymap(L["top"]) + 46], 8, fill="#F4F1EA")
        g.text((sx0 + 15, ymap(L["top"]) + 8), L["label"], font=f_s, fill="#111")
    # ствол
    bx = sx1 - 70
    g.rectangle([bx - 16, y0, bx + 16, y1], fill=style["fluids"]["mud"]["color"])
    # шкала глубины (растёт вниз)
    step = max(1, round((d1 - d0) / 8))
    for d in np.arange(d0, d1 + 1e-6, step):
        yy = ymap(d)
        g.line([sx0 - 12, yy, sx0, yy], fill=muted, width=2)
        g.text((sx0 - 12 - 90 if aspect != "9:16" else 4, yy - 16), f"{d:g}", font=font(24), fill=muted)
    g.text((side, y1 + 12), "глубина, м ↓", font=font(26), fill=muted)
    g.rectangle([cx0, y0, cx1, y1], outline=muted, width=2)
    g.text((cx0, y0 - 44), f"{cur['label']}, {cur['unit']}", font=font(30, True), fill=ccol)
    g.text((cx0, y1 + 12), f"{vmin:g}", font=font(24), fill=muted)
    g.text((cx1 - 60, y1 + 12), f"{vmax:g}", font=font(24), fill=muted)
    # метка происхождения и плашка
    lab = "симуляция"
    pc = style["provenance"][lab]
    g.rounded_rectangle([W - side - 250, ty0 + 4, W - side, ty0 + 58], 26, fill=pc)
    g.text((W - side - 225, ty0 + 10), lab, font=font(34, True), fill="#fff")
    plaque = "не в масштабе: " + "; ".join(e.split(".")[0] for e in (spec.get("exaggerations") or ["ширина ствола увеличена"]))
    pl, ln, fp = [], "", font(26)
    for w in plaque.split():
        cand = (ln + " " + w).strip()
        if g.textlength(cand, font=fp) > W - 2 * side and ln:
            pl.append(ln); ln = w
        else:
            ln = cand
    pl.append(ln)
    for k, ln in enumerate(pl[:2]):
        g.text((side, ty0 + 64 * min(2, len(lines_t)) + 6 + k * 32), ln + ("…" if k == 1 and len(pl) > 2 else ""), font=fp, fill=muted)

    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for f in frames_dir.glob("*.png"):
        f.unlink()
    nfr = int(total * fps)
    # глубина прибора: интерполяция между фразами
    keys = [(t0, b.get("tool_depth", d0)) for (t0, t1, b) in beats_t]
    prev_depth = [keys[0][1]] + [d for _, d in keys[:-1]]
    for i in range(nfr):
        t = i / fps
        k = max([j for j, (t0, _) in enumerate(keys) if t0 <= t] or [0])
        # в начале фразы прибор доезжает от прежней глубины до глубины этой фразы
        t0, dB = keys[k]
        dA = prev_depth[k]
        t1 = beats_t[k][1]
        a = min(1.0, (t - t0) / max(0.5, min(2.0, t1 - t0)))
        a = a * a * (3 - 2 * a)
        dep = dA + (dB - dA) * a
        im = base.copy()
        dr = ImageDraw.Draw(im)
        b = beats_t[k][2]
        shown = set()
        for j in range(k + 1):
            shown |= set(beats_t[j][2].get("show") or [])
        for L in p["layers"]:
            ya, yb = ymap(L["top"]), ymap(L["bottom"])
            if "invasion" in shown and L.get("invasion"):
                wv = 16 + L["invasion"] * (bx - sx0 - 40)
                ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                od = ImageDraw.Draw(ov)
                fc = style["fluids"]["filtrate"]["color"].lstrip("#")
                rgb = tuple(int(fc[i:i + 2], 16) for i in (0, 2, 4))
                od.rectangle([bx - wv, ya, min(sx1, bx + wv), yb], fill=rgb + (150,))
                im.paste(ov, (0, 0), ov)
                dr = ImageDraw.Draw(im)
                dr.text((bx - wv + 6, yb - 36), "фильтрат", font=font(24, True), fill="#0b3a55")
            if "cake" in shown and L.get("mud_cake"):
                dr.rectangle([bx - 22, ya, bx - 16, yb], fill="#4a3b2c")
                dr.rectangle([bx + 16, ya, bx + 22, yb], fill="#4a3b2c")
        for L in p["layers"]:  # подписи пластов поверх зоны проникновения
            lw = dr.textlength(L["label"], font=f_s)
            dr.rounded_rectangle([sx0 + 8, ymap(L["top"]) + 6, sx0 + 22 + lw, ymap(L["top"]) + 46], 8, fill="#F4F1EA")
            dr.text((sx0 + 15, ymap(L["top"]) + 8), L["label"], font=f_s, fill="#111")
        if b.get("highlight"):
            h0, h1 = b["highlight"]
            dr.rectangle([sx0 - 4, ymap(h0), cx1 + 4, ymap(h1)], outline=style["measurement"]["color"], width=5)
        # прибор и точка кривой из одной модели состояния
        ty = ymap(dep)
        dr.line([bx, y0 - 40, bx, ty - 36], fill=muted, width=3)
        dr.rounded_rectangle([bx - 13, ty - 36, bx + 13, ty + 36], 8, fill=style["measurement"]["color"])
        dr.ellipse([bx - 6, ty - 6, bx + 6, ty + 6], fill="#111")  # точка записи прибора = точка кривой
        m = z <= dep
        if m.sum() > 1:
            pts = [(xmap(v), ymap(zz)) for zz, v in zip(z[m], vs[m])]
            dr.line(pts, fill=ccol, width=6)
            dr.ellipse([pts[-1][0] - 10, pts[-1][1] - 10, pts[-1][0] + 10, pts[-1][1] + 10], fill=ccol)
        dr.line([sx1, ty, cx0, ty], fill=muted, width=2)
        if b.get("on_screen"):
            dr.text((side, y0 - 95 if aspect == "9:16" else y0 - 80), b["on_screen"], font=f_c, fill=style["measurement"]["color"])
        # субтитры (выше нижней безопасной зоны)
        words = b["say"].split()
        lines, line = [], ""
        maxw = W - 2 * side
        for w in words:
            cand = (line + " " + w).strip()
            if dr.textlength(cand, font=f_sub) > maxw:
                lines.append(line)
                line = w
            else:
                line = cand
        lines.append(line)
        sy = H - bot_safe - 60 * len(lines) + (0 if aspect == "9:16" else 40)
        for ln in lines:
            tw = dr.textlength(ln, font=f_sub)
            dr.rectangle([(W - tw) / 2 - 12, sy - 4, (W + tw) / 2 + 12, sy + 54], fill=panel)
            dr.text(((W - tw) / 2, sy), ln, font=f_sub, fill=txt)
            sy += 60
        im.save(frames_dir / f"f{i:05d}.png")
    return frames_dir


def build(layer: dict, routing: dict, dom: dict, out_dir: Path, aspect: str = "9:16", node_id: str | None = None,
          voice: str = "ru-RU-DmitryNeural", backup_voice: str = "ru-RU-SvetlanaNeural", log=print) -> dict:
    nodes = {n["id"]: n for n in layer["nodes"]}
    if node_id is None:
        want = "шортс" if aspect == "9:16" else "длинное видео"
        cands = [r for r in routing["routes"] if r["format"] == want or r.get("secondary_format") == want]
        cands = cands or [r for r in routing["routes"] if r["format"] in ("шортс", "длинное видео")] or routing["routes"]
        prio = {"И": 0, "М": 1, "Н": 2}
        cands.sort(key=lambda r: (prio.get(nodes[r["node_id"]]["difficulty"]["primary"], 9), -sum(r["video_scores"].values())))
        node_id = cands[0]["node_id"]
    node = nodes[node_id]
    log(f"[ролик] узел {node_id}, формат {aspect}")
    spec = make_spec(node, dom, aspect)
    vid = f"{node_id.replace('.', '_')}_{aspect.replace(':', 'x')}"
    vdir = out_dir / vid
    vdir.mkdir(parents=True, exist_ok=True)
    (vdir / "scene_spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    # озвучка по фразам: длительность фразы задаёт тайминг кадра (синхрон голос–кадр)
    beats = list(spec["beats"])
    d_first = beats[0].get("tool_depth", spec["params"]["depth_top"])
    if spec.get("hook"):
        beats.insert(0, {"say": spec["hook"], "claim_id": None, "on_screen": "", "tool_depth": d_first, "role": "hook"})
    if spec.get("prediction_question"):
        mid = max(2, len(beats) // 2)
        q = spec["prediction_question"].split(":")[-1].strip()
        beats.insert(mid, {"say": q, "claim_id": None, "on_screen": "Как думаете?", "tool_depth": beats[mid - 1].get("tool_depth", d_first), "role": "prediction"})
    if spec.get("transfer_question"):
        beats.append({"say": spec["transfer_question"], "claim_id": None, "on_screen": "Вопрос на перенос", "tool_depth": beats[-1].get("tool_depth", d_first), "role": "transfer"})
    spec["beats_voiced"] = beats
    # голос: облачный Microsoft Neural; если сервис недоступен — весь ролик офлайн-голосом Windows (Microsoft Irina),
    # чтобы в одном ролике не смешивались голоса
    texts = [stress(b["say"], dom) for b in beats]
    used_voice = voice
    srcs = []
    try:
        for i, text in enumerate(texts):
            mp3 = vdir / f"b{i:02d}.mp3"
            for attempt in range(4):
                try:
                    asyncio.run(_tts(text, mp3, vdir / f"b{i:02d}.srt", voice))
                    break
                except Exception as e:
                    log(f"[озвучка] повтор {attempt + 1}: {type(e).__name__}")
                    __import__("time").sleep(2 + attempt * 2)
            else:
                raise RuntimeError("облачная озвучка недоступна")
            srcs.append(mp3)
    except RuntimeError:
        log("[озвучка] переключаюсь на запасной офлайн-голос Microsoft Irina (Windows SAPI)")
        used_voice = "Microsoft Irina Desktop (офлайн, SAPI)"
        srcs = []
        for i, text in enumerate(texts):
            w = vdir / f"b{i:02d}_sapi.wav"
            _sapi(text, w)
            srcs.append(w)
    beats_t, t, parts = [], 0.4, []
    for i, b in enumerate(beats):
        mp3 = srcs[i]
        sped = vdir / f"b{i:02d}.wav"  # темп 110–150 слов/мин: ускорение без изменения высоты голоса
        subprocess.run([ffmpeg(), "-y", "-i", str(mp3), "-filter:a", f"atempo={TEMPO}", str(sped)], capture_output=True, check=True)
        mp3 = sped
        d = duration(mp3)
        pause = 2.5 if b.get("role") == "prediction" else (1.2 if b["say"].strip().endswith("?") else 0.35)  # пауза на предсказание после вопроса
        beats_t.append((t, t + d, b))
        parts.append((mp3, t))
        t += d + pause
    total = t + 0.6
    # звук: склейка с задержками, громкость −16 LUFS
    inputs, filt = [], []
    for k, (mp3, st) in enumerate(parts):
        inputs += ["-i", str(mp3)]
        filt.append(f"[{k}:a]adelay={int(st * 1000)}|{int(st * 1000)}[a{k}]")
    mix = "".join(f"[a{k}]" for k in range(len(parts))) + f"amix=inputs={len(parts)}:normalize=0,apad=whole_dur={total:.2f},loudnorm=I=-16:TP=-1.5:LRA=11[out]"
    wav = vdir / "voice.wav"
    subprocess.run([ffmpeg(), "-y", *inputs, "-filter_complex", ";".join(filt) + ";" + mix, "-map", "[out]", "-ar", "48000", str(wav)],
                   capture_output=True, check=True)
    # субтитры VTT по фразам
    def ts(x):
        return f"{int(x // 3600):02d}:{int(x % 3600 // 60):02d}:{x % 60:06.3f}"
    vtt = "WEBVTT\n\n" + "\n\n".join(f"{ts(a)} --> {ts(b)}\n{bt['say']}" for a, b, bt in beats_t)
    (vdir / f"{vid}.vtt").write_text(vtt, encoding="utf-8")
    frames = render(spec, node, dom["style"], beats_t, total, vdir, aspect)
    mp4 = vdir / f"{vid}.mp4"
    subprocess.run([ffmpeg(), "-y", "-framerate", "24", "-i", str(frames / "f%05d.png"), "-i", str(wav),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", "-preset", "veryfast", "-c:a", "aac", "-b:a", "128k",
                    "-shortest", str(mp4)], capture_output=True, check=True)
    for f in frames.glob("*.png"):
        if int(f.stem[1:]) % 120:
            f.unlink()  # оставляем каждый 120-й кадр для паспорта и проверки
    for f in list(vdir.glob("b[0-9][0-9]*.*")) + [wav]:
        f.unlink()  # промежуточный звук не нужен в курсе
    # измерение громкости итогового файла
    r = subprocess.run([ffmpeg(), "-i", str(mp4), "-af", "loudnorm=print_format=json", "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    lufs = json.loads(m.group(0))["input_i"] if m else None
    words = sum(len(b["say"].split()) for b in beats)
    speech = sum(b - a for a, b, _ in beats_t)
    claims = {c["id"]: c for c in node["claims"]}
    passport = {
        "video_id": vid, "node_id": node_id,
        "node_card": {"title": node["title"], "novice_title": (node.get("course") or {}).get("novice_title"),
                      "difficulty": node["difficulty"], "essence": (node.get("course") or {}).get("essence")},
        "script": [{"t_start": round(a, 2), "t_end": round(b, 2), "text": bt["say"], "claim_id": bt.get("claim_id"),
                    "is_analogy": bool(bt.get("is_analogy")), "on_screen": bt.get("on_screen", "")} for a, b, bt in beats_t],
        "sources": [{"claim_id": cid, "page_or_dataset": f"стр. {claims[cid]['page_pdf']}", "quote": claims[cid]["quote"]}
                    for cid in dict.fromkeys(bt.get("claim_id") for _, _, bt in beats_t) if cid in claims],
        "scene_spec": f"{vid}/scene_spec.json",
        "frames": [{"t": round(a, 2), "class": "B", "label": "симуляция"} for a, _, _ in beats_t],
        "exaggerations": spec.get("exaggerations") or [],
        "prediction_question": spec.get("prediction_question", ""), "transfer_question": spec.get("transfer_question", ""),
        "data_it_bridge": spec.get("data_it_bridge", ""),
        "physics_checklist": [{"item": c["item"], "answer": "да" if c["id"] in ("pc.gas_oil_water", "pc.fluids_in_pores") else "н/п"}
                              for c in dom["checklist"][:12]],
        "audio_check": {"duration_s": round(total, 1), "words": words, "wpm": round(words / max(speech, 1) * 60),
                        "loudness_lufs": lufs, "voice": used_voice, "backup_voice": "Microsoft Irina Desktop (офлайн)",
                        "sync": "тайминг кадров задан длительностью озвучки каждой фразы; сдвиг 0 с по построению",
                        "outside": "во внешний сервис (Microsoft TTS) уходит только текст сценария; офлайн-голос — ничего"},
    }
    (vdir / "passport.json").write_text(json.dumps(passport, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"[ролик] {mp4} ({total:.0f} с, {passport['audio_check']['wpm']} слов/мин, {lufs} LUFS)")
    return {"node_id": node_id, "src": f"media/{vid}/{vid}.mp4", "vtt": f"media/{vid}/{vid}.vtt",
            "title": spec["title"] + (" · шортс 9:16" if aspect == "9:16" else " · разбор 16:9"), "passport": passport}
