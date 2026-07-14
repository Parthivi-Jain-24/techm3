"""GDPR article loader with keyword search.

Source file: data/gdpr_text/gdpr.json
Format: JSON array of objects with keys:
    article_id, article_title, article_text, article_recitals

Note: the source data has multiple entries per article_id (one per
paragraph/sub-section).  Search deduplicates by text content;
``get_gdpr_article_by_id`` returns all paragraphs for an article.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.config import settings

# ── In-memory cache ─────────────────────────────────────────────────

_articles: list[dict] | None = None
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _load() -> list[dict]:
    global _articles
    if _articles is not None:
        return _articles

    path: Path = settings.data_folder / "gdpr_text" / "gdpr.json"
    with open(path, encoding="utf-8") as fh:
        _articles = json.load(fh)

    return _articles


# ── Public API ──────────────────────────────────────────────────────

def get_gdpr_article(query: str, *, limit: int = 5) -> list[dict]:
    """Keyword-search GDPR articles.

    Tokenises *query* and scores each article paragraph by the fraction
    of query tokens present in its title + text + recitals.  Deduplicates
    by ``article_text`` so identical paragraphs don't repeat.  Returns up
    to *limit* results sorted by descending relevance::

        {"article_id", "article_title", "article_text",
         "article_recitals", "score"}

    Score is 0–100.  Articles scoring 0 are excluded.
    """
    articles = _load()
    q_tokens = set(_TOKEN_RE.findall(query.lower()))
    if not q_tokens:
        return []

    seen_texts: set[str] = set()
    scored: list[tuple[int, dict]] = []
    for art in articles:
        text = art.get("article_text", "")
        if text in seen_texts:
            continue
        seen_texts.add(text)

        blob = " ".join([
            art.get("article_title", ""),
            text,
            art.get("article_recitals", ""),
        ]).lower()
        art_tokens = set(_TOKEN_RE.findall(blob))
        overlap = len(q_tokens & art_tokens)
        score = int((overlap / len(q_tokens)) * 100)
        if score > 0:
            scored.append((score, art))

    scored.sort(key=lambda h: h[0], reverse=True)
    return [
        {**art, "score": sc}
        for sc, art in scored[:limit]
    ]


def get_gdpr_article_by_id(article_id: str) -> list[dict]:
    """Return all paragraphs for *article_id* (e.g. ``'article5'``)."""
    return [art for art in _load() if art.get("article_id") == article_id]
