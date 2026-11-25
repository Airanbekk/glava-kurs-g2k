"""Доменный пакет: всё предметное лежит в domain/<имя>/, движок только читает."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@lru_cache
def load(name: str = "geo") -> dict:
    d = ROOT / "domain" / name
    if not d.exists():
        raise SystemExit(f"нет доменного пакета domain/{name}; создайте его командой: python run.py domain-bootstrap ...")
    rd = lambda f, default=None: json.loads((d / f).read_text(encoding="utf-8")) if (d / f).exists() else default
    return {
        "name": name,
        "dir": d,
        "domain_md": (d / "domain.md").read_text(encoding="utf-8"),
        "misconceptions": rd("misconceptions.json", []),
        "checklist": rd("physics_checklist.json", []),
        "style": rd("styleguide.json", {}),
        "stress_md": (d / "stress_dict.md").read_text(encoding="utf-8") if (d / "stress_dict.md").exists() else "",
        "glossary": rd("glossary.json", []),
    }


def misconceptions_text(dom: dict) -> str:
    return "\n".join(f"- {m['id']}: {m['text']}" for m in dom["misconceptions"])


def checklist_text(dom: dict) -> str:
    return "\n".join(f"- {c['id']}: {c['item']}" for c in dom["checklist"])
