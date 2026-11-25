"""Обёртка над моделью: кеш на диске, JSON-ответ с проверкой и повтором, учёт токенов и денег.

Поставщик заменяем: весь движок зовёт только ask_json(). Бэкенды (LLM_BACKEND в .env):
  api          — Anthropic API по ключу ANTHROPIC_API_KEY;
  claude-code  — Claude Code CLI по подписке пользователя (без ключа);
  openai       — любой OpenAI-совместимый сервер: локальная модель через vLLM / Ollama / LM Studio (LLM_BASE_URL).
Модели по ролям: gen — генерация слоя и заданий (LLM_MODEL), review — модуль проверки (LLM_MODEL_REVIEW).
"""
from __future__ import annotations

import base64
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "llm"
CACHE.mkdir(parents=True, exist_ok=True)

PRICES = {  # $ за 1M токенов (вход, выход), для оценки стоимости в metrics.csv
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}

_lock = threading.Lock()
USAGE = {"calls": 0, "cached": 0, "in": 0, "out": 0, "usd": 0.0}


def _load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


_load_env()
BACKEND = os.environ.get("LLM_BACKEND") or ("api" if os.environ.get("ANTHROPIC_API_KEY") else "claude-code")
_DEFAULT = {"api": ("claude-opus-5-5", "claude-opus-5-5"),
            "claude-code": ("claude-sonnet-5-5", "claude-opus-5-5"),  # экономный режим по подписке
            "openai": ("local-model", "local-model")}[BACKEND]
MODELS = {"gen": os.environ.get("LLM_MODEL", _DEFAULT[0]),
          "review": os.environ.get("LLM_MODEL_REVIEW", os.environ.get("LLM_MODEL", _DEFAULT[1]))}
MODEL = MODELS["gen"]  # для подписи в файлах
DEFAULT_WORKERS = int(os.environ.get("LLM_WORKERS", {"api": 8, "claude-code": 3, "openai": 4}[BACKEND]))
_client = None


def describe() -> str:
    return f"{BACKEND}: gen={MODELS['gen']}, review={MODELS['review']}"


def reset_usage():
    for k in USAGE:
        USAGE[k] = 0 if k != "usd" else 0.0


def _count(model: str, tin: int, tout: int, usd: float | None = None):
    pin, pout = PRICES.get(model, (0.0, 0.0))
    with _lock:
        USAGE["calls"] += 1
        USAGE["in"] += tin
        USAGE["out"] += tout
        USAGE["usd"] += usd if usd is not None else tin / 1e6 * pin + tout / 1e6 * pout


def _extract_json(text: str):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    start = min([i for i in (text.find("{"), text.find("[")) if i != -1], default=-1)
    if start == -1:
        raise ValueError("в ответе нет JSON")
    end = max(text.rfind("}"), text.rfind("]"))
    return json.loads(text[start:end + 1])


# ---------------------------------------------------------------- бэкенд: Anthropic API

def _call_api(model, system, content, effort, max_tokens) -> str:
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(max_retries=4, timeout=900)
    if not isinstance(content, str):
        content = [{k: v for k, v in c.items() if k != "_path"} for c in content]
    kwargs = dict(model=model, max_tokens=max_tokens, system=system,
                  messages=[{"role": "user", "content": content}], output_config={"effort": effort})
    if os.environ.get("LLM_FALLBACKS", "1") == "1" and model in ("claude-opus-5-5", "claude-sonnet-5-5"):
        with _client.beta.messages.stream(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs) as s:
            msg = s.get_final_message()
    else:
        with _client.messages.stream(**kwargs) as s:
            msg = s.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError(f"модель отказалась: {getattr(msg, 'stop_details', None)}")
    _count(model, msg.usage.input_tokens, msg.usage.output_tokens)
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("ответ обрезан по max_tokens")
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


# ---------------------------------------------------------------- бэкенд: Claude Code по подписке

def _find_claude_bin() -> str | None:
    if os.environ.get("CLAUDE_BIN"):
        return os.environ["CLAUDE_BIN"]
    found = shutil.which("claude")
    if found:
        return found
    base = os.environ.get("LOCALAPPDATA", "")
    cands = sorted(glob.glob(os.path.join(base, "Claude-Data", "*", "claude-code", "*", "*", "claude.exe")), key=os.path.getmtime)
    return cands[-1] if cands else None


def _call_cli(model, system, content, effort) -> str:
    exe = _find_claude_bin()
    if not exe:
        raise SystemExit("Не найден Claude Code CLI. Укажите путь в .env: CLAUDE_BIN=...")
    tools, extra, text = "", [], content
    if not isinstance(content, str):  # картинки: модель читает файл инструментом Read
        paths = [c["_path"] for c in content if c.get("type") == "image"]
        text = next(c["text"] for c in content if c.get("type") == "text")
        text = "Сначала открой и рассмотри изображения: " + ", ".join(paths) + "\n\n" + text
        tools = "Read"
        for d in {str(Path(p).parent) for p in paths}:
            extra += ["--add-dir", d]
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(system)
        sp = f.name
    cmd = [exe, "-p", "--output-format", "json", "--model", model, "--effort", effort,
           "--system-prompt-file", sp, "--tools", tools, "--no-session-persistence", *extra]
    try:
        r = subprocess.run(cmd, input=text, capture_output=True, text=True, encoding="utf-8", timeout=1800)
    finally:
        os.unlink(sp)
    try:
        d = json.loads(r.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"CLI: {r.stdout[-400:]} {r.stderr[-400:]}")
    if d.get("is_error"):
        msg = str(d.get("result"))
        low = msg.lower()
        if "authenticate" in low or "log in" in low or "login" in low:
            raise SystemExit("Claude Code не авторизован. Выполните: claude auth login (вход вашей подпиской)")
        if "limit" in low:
            raise SystemExit(f"Лимит подписки исчерпан: {msg[:200]}. Готовые шаги сохранены в кеше; повторите команду позже.")
        raise RuntimeError(f"CLI: {msg[:400]}")
    u = d.get("usage") or {}
    tin = int(u.get("input_tokens", 0)) + int(u.get("cache_read_input_tokens", 0)) + int(u.get("cache_creation_input_tokens", 0))
    _count(model, tin, int(u.get("output_tokens", 0)))  # стоимость — эквивалент по ценам API; по подписке денег не списывается
    return d.get("result") or ""


# ---------------------------------------------------------------- бэкенд: OpenAI-совместимый сервер (локальная модель)

def _call_openai(model, system, content, effort, max_tokens) -> str:
    base = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/")
    if isinstance(content, str):
        user = content
    else:
        user = []
        for c in content:
            if c.get("type") == "image":
                user.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{c['source']['data']}"}})
            else:
                user.append({"type": "text", "text": c["text"]})
    body = {"model": model, "max_tokens": max_tokens, "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request(base + "/chat/completions", data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {os.environ.get('LLM_API_KEY', 'none')}"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        d = json.loads(r.read().decode("utf-8"))
    u = d.get("usage") or {}
    _count(model, int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0)), 0.0)
    return d["choices"][0]["message"]["content"] or ""


def _call(model, system, content, effort, max_tokens) -> str:
    if BACKEND == "claude-code":
        return _call_cli(model, system, content, effort)
    if BACKEND == "openai":
        return _call_openai(model, system, content, effort, max_tokens)
    return _call_api(model, system, content, effort, max_tokens)


def ask_json(system: str, user: str, *, schema: dict | None = None, validate=None, effort: str = "medium",
             max_tokens: int = 32000, images: list[Path] | None = None, tag: str = "", retries: int = 2,
             role: str = "gen"):
    """Запрос -> JSON. schema: JSON Schema для проверки; validate: функция(obj)->список ошибок.
    Ответы кешируются по хешу запроса: повторная сборка бесплатна и детерминирована."""
    model = MODELS[role]
    content: list | str = user
    img_key = ""
    if images:
        content = []
        for p in images:
            data = base64.b64encode(Path(p).read_bytes()).decode()
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data},
                            "_path": str(Path(p).resolve())})
            img_key += hashlib.sha256(data.encode()).hexdigest()[:16]
        content.append({"type": "text", "text": user})
    key = hashlib.sha256(f"{model}|{effort}|{system}|{user}|{img_key}".encode()).hexdigest()[:32]
    path = CACHE / f"{tag + '_' if tag else ''}{key}.json"
    if path.exists():
        with _lock:
            USAGE["cached"] += 1
        return json.loads(path.read_text(encoding="utf-8"))

    note, last_err = "", None
    for attempt in range(retries + 1):
        cur = content
        if note:
            fix = f"\n\nПредыдущий ответ был отклонён: {note}\nИсправь и верни полный JSON заново."
            cur = (content + fix) if isinstance(content, str) else content[:-1] + [{"type": "text", "text": user + fix}]
        try:
            text = _call(model, system, cur, effort, max_tokens)
            obj = _extract_json(text)
            errs = []
            if schema is not None:
                v = jsonschema.Draft202012Validator(schema)
                errs += [f"{'/'.join(map(str, e.path))}: {e.message}" for e in list(v.iter_errors(obj))[:15]]
            if validate is not None:
                errs += validate(obj)
            if errs:
                note = last_err = "; ".join(errs[:15])
                continue
            path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
            return obj
        except (ValueError, json.JSONDecodeError) as e:
            note = last_err = f"невалидный JSON ({e})"
        except RuntimeError as e:
            note = last_err = str(e)
            time.sleep(3)
    raise RuntimeError(f"[{tag}] не удалось получить валидный ответ: {last_err}")
