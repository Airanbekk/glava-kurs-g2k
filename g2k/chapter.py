"""Глава: нарезка md по меткам <!-- page N --> и на единицы покрытия (unit_id = p095.03)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

PAGE_RE = re.compile(r"<!--\s*page\s+(\d+)\s*-->")


@dataclass
class Unit:
    unit_id: str
    page: int
    kind: str
    text: str

    @property
    def excerpt(self) -> str:
        words = re.sub(r"[#*_|$>`]", " ", self.text).split()
        return " ".join(words[:12])


@dataclass
class Chapter:
    key: str
    chapter_id: str
    prefix: str
    book: str
    language: str
    domain: str
    pages: dict[int, str]
    md: str = ""
    units: list[Unit] = field(default_factory=list)

    def page_text(self, n: int) -> str:
        return self.pages.get(n, "")

    def text_with_units(self, unit_ids: list[str] | None = None) -> str:
        """Текст главы, где каждая единица помечена [p095.03]. Так модель ссылается на единицы, а покрытие считается кодом."""
        wanted = set(unit_ids) if unit_ids else None
        out, cur = [], None
        for u in self.units:
            if wanted is not None and u.unit_id not in wanted:
                continue
            if u.page != cur:
                out.append(f"\n<!-- page {u.page} -->")
                cur = u.page
            out.append(f"[{u.unit_id}] {u.text}")
        return "\n\n".join(out)

    def unit(self, uid: str) -> Unit | None:
        return self._index.get(uid)

    def __post_init__(self):
        self._index = {}


def _kind(block: str) -> str:
    b = block.strip()
    low = b.lower()
    if b.startswith("#"):
        return "heading"
    if b.startswith("|") or b.count("|") >= 4:
        return "table"
    if b.startswith("$$") or b.startswith("\\[") or (b.startswith("$") and b.endswith("$")):
        return "formula"
    if b.startswith("![") or re.match(r"^(рис\.|рисунок|fig\.|figure)\s*\d", low):
        return "figure"
    if re.match(r"^(задача|упражнение|problem|exercise)\s*\d*", low):
        return "task"
    if re.match(r"^(пример|example)\s*\d*[.:]", low):
        return "worked_example"
    return "paragraph"


def load_chapter(key: str, cfg: dict, root) -> Chapter:
    raw = (root / cfg["md"]).read_text(encoding="utf-8")
    parts = PAGE_RE.split(raw)
    all_pages: dict[int, str] = {}
    # parts: [before, n1, text1, n2, text2, ...]
    for i in range(1, len(parts), 2):
        all_pages[int(parts[i])] = parts[i + 1]
    wanted: list[int] = []
    for a, b in cfg["pages"]:
        wanted.extend(range(a, b + 1))
    pages = {n: all_pages.get(n, "") for n in wanted}
    ch = Chapter(key=key, chapter_id=cfg["chapter"], prefix=cfg["prefix"], book=cfg.get("book", ""),
                 language=cfg.get("language", "ru"), domain=cfg.get("domain", "geo"), pages=pages, md=cfg["md"])
    for n in wanted:
        blocks = [b.strip() for b in re.split(r"\n\s*\n", pages[n]) if b.strip()]
        k = 0
        for b in blocks:
            if len(re.sub(r"\W", "", b)) < 3:
                continue
            k += 1
            u = Unit(unit_id=f"p{n:03d}.{k:02d}", page=n, kind=_kind(b), text=b)
            ch.units.append(u)
            ch._index[u.unit_id] = u
    return ch


def load_md_pages(path) -> dict[int, str]:
    raw = path.read_text(encoding="utf-8")
    parts = PAGE_RE.split(raw)
    return {int(parts[i]): parts[i + 1] for i in range(1, len(parts), 2)}
