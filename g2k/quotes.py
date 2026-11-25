"""Проверка цитат ровно по правилу жюри: дословно из md, без учёта пробелов, переносов строк и регистра.

Если модель процитировала почти дословно, цитата заменяется точным фрагментом источника (авторемонт),
а страница — той, где фрагмент реально найден. Неремонтируемая цитата = утверждение отклоняется.
"""
from __future__ import annotations

import re

from rapidfuzz import fuzz

WS = re.compile(r"\s+")


def norm(s: str) -> str:
    return WS.sub("", s).lower()


class PageIndex:
    def __init__(self, pages: dict[int, str]):
        self.pages = pages
        self.norm: dict[int, str] = {}
        self.maps: dict[int, list[int]] = {}
        for n, t in pages.items():
            chars, idx = [], []
            for i, c in enumerate(t):
                if not c.isspace():
                    chars.append(c.lower())
                    idx.append(i)
            self.norm[n] = "".join(chars)
            self.maps[n] = idx

    def exact_pages(self, quote: str) -> list[int]:
        q = norm(quote)
        if len(q) < 8:
            return []
        return [n for n, t in self.norm.items() if q in t]

    def verify(self, quote: str, page: int) -> bool:
        q = norm(quote)
        return len(q) >= 8 and q in self.norm.get(page, "")

    def repair(self, quote: str, page_hint: int | None, min_score: float = 88.0):
        """-> (quote, page, status) ; status: exact | moved | repaired | failed"""
        q = norm(quote)
        if len(q) < 8:
            return quote, page_hint, "failed"
        if page_hint is not None and q in self.norm.get(page_hint, ""):
            return quote, page_hint, "exact"
        hits = self.exact_pages(quote)
        if hits:
            best = min(hits, key=lambda n: abs(n - (page_hint or n)))
            return quote, best, "moved"
        order = sorted(self.norm, key=lambda n: (abs(n - page_hint) if page_hint else 0, n))
        best = (0.0, None, None, None)
        for n in order[: (5 if page_hint else len(order))]:
            t = self.norm[n]
            if not t:
                continue
            al = fuzz.partial_ratio_alignment(q, t, score_cutoff=min_score)
            if al and al.score > best[0]:
                best = (al.score, n, al.dest_start, al.dest_end)
        if best[1] is None:
            return quote, page_hint, "failed"
        _, n, s, e = best
        m = self.maps[n]
        page = self.pages[n]
        a, b = m[s], m[e - 1] + 1
        # обрезать до границ слов, чтобы не оставлять обрывков вроде «с п»
        if b < len(page) and page[b].isalnum():
            cut = page.rfind(" ", a, b)
            if cut > a:
                b = cut
        if a > 0 and page[a - 1].isalnum():
            nxt = page.find(" ", a, b)
            if nxt != -1:
                a = nxt + 1
        orig = WS.sub(" ", page[a:b]).strip()
        if self.verify(orig, n):
            return orig, n, "repaired"
        return quote, page_hint, "failed"


NUM_RE = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?")


def numbers_in(s: str) -> set[str]:
    return {x.replace(",", ".") for x in NUM_RE.findall(s)}


def unsupported_numbers(text: str, sources: list[str]) -> set[str]:
    """Числа из text, которых нет ни в одном источнике (страницы/цитаты). Мелкие порядковые 1–3 не считаем."""
    src = set()
    for s in sources:
        src |= numbers_in(s)
    return {x for x in numbers_in(text) if x not in src and x not in {"1", "2", "3"}}
