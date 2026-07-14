from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any


NEWS_API_URL = "https://newsapi.org/v2/everything"


class NewsService:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("NEWS_API_KEY")

    def search_company_risk(self, company_name: str, limit: int = 5) -> dict[str, Any]:
        if not self.api_key:
            return {
                "enabled": False,
                "articles": [],
                "risk_signal": None,
                "message": "Set NEWS_API_KEY to enable live adverse-media lookup.",
            }

        query = f'"{company_name}" AND (sanctions OR laundering OR fraud OR corruption OR investigation)'
        params = urllib.parse.urlencode({
            "q": query,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": max(1, min(limit, 10)),
            "apiKey": self.api_key,
        })
        request = urllib.request.Request(f"{NEWS_API_URL}?{params}", headers={"User-Agent": "continuous-kyc-risk-console/1.0"})

        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            return {"enabled": True, "articles": [], "risk_signal": None, "message": f"Live news lookup failed: {exc}"}

        articles = []
        for article in payload.get("articles", [])[:limit]:
            title = article.get("title") or "Untitled"
            description = article.get("description") or ""
            source = (article.get("source") or {}).get("name") or "Unknown source"
            articles.append({
                "title": title,
                "source": source,
                "published_at": article.get("publishedAt"),
                "url": article.get("url"),
                "description": description,
            })

        severity = "LOW"
        if articles:
            joined = " ".join((item["title"] + " " + item["description"]).lower() for item in articles)
            if any(word in joined for word in ["sanction", "laundering", "terror", "fraud", "corruption"]):
                severity = "HIGH"
            elif any(word in joined for word in ["investigation", "probe", "regulator"]):
                severity = "MEDIUM"

        return {
            "enabled": True,
            "articles": articles,
            "risk_signal": {
                "negative_news_found": bool(articles),
                "severity": severity,
                "source": articles[0]["source"] if articles else "NewsAPI",
                "source_count": len(articles),
                "confidence": 0.72 if articles else 0.0,
                "mentions_sanctions": severity == "HIGH",
            },
            "message": "Live adverse-media lookup completed.",
        }