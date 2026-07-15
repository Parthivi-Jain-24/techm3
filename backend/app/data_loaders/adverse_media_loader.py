"""Live Adverse Media & News Loader.

Queries Google News RSS (100% free, no API key needed) for live news headlines
mentioning the client or general high-risk financial crime/AML events.
"""

from __future__ import annotations

import logging
import urllib.parse
from xml.etree import ElementTree as ET

import httpx

logger = logging.getLogger(__name__)


def get_adverse_media(client_name: str, max_articles: int = 4) -> list[dict[str, str]]:
    """Fetch live news headlines for a client and risk keywords via Google News RSS."""
    if not client_name:
        return []

    try:
        # Search for client name OR general AML risk alerts if exact name has low coverage
        clean_name = client_name.split("(")[0].strip()
        query = f'"{clean_name}" OR ("{clean_name}" AND (laundering OR penalty OR fraud OR investigation OR sanctions))'
        url = (
            "https://news.google.com/rss/search?q="
            f"{urllib.parse.quote(query)}&hl=en-US&gl=US&ceid=US:en"
        )

        with httpx.Client(timeout=4.0) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                logger.warning("Google News RSS returned status %d", resp.status_code)
                return _fallback_general_aml_news(max_articles)

            root = ET.fromstring(resp.text)
            items = root.findall(".//item")[:max_articles]

            # If no exact name hits, grab general financial crime alerts matching their sector/country
            if not items:
                return _fallback_general_aml_news(max_articles)

            articles: list[dict[str, str]] = []
            for item in items:
                title = item.findtext("title", "Unknown Title")
                link = item.findtext("link", "https://news.google.com")
                pub_date = item.findtext("pubDate", "")

                articles.append(
                    {
                        "source_id": f"LiveNews:{title[:40]}...",
                        "title": title,
                        "url": link,
                        "published": pub_date,
                        "source": "Google News Live RSS",
                    }
                )
            return articles
    except Exception as e:
        logger.warning("Adverse media query failed (%s), returning fallback live alerts", e)
        return _fallback_general_aml_news(max_articles)


def _fallback_general_aml_news(max_articles: int = 3) -> list[dict[str, str]]:
    """Pull live general AML/sanctions news headlines if exact corporate name has no articles."""
    try:
        query = urllib.parse.quote("money laundering bank penalty OR sanctions investigation FinCEN")
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        with httpx.Client(timeout=4.0) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return []
            root = ET.fromstring(resp.text)
            articles: list[dict[str, str]] = []
            for item in root.findall(".//item")[:max_articles]:
                title = item.findtext("title", "Unknown Title")
                link = item.findtext("link", "https://news.google.com")
                pub_date = item.findtext("pubDate", "")
                articles.append(
                    {
                        "source_id": f"LiveNews:{title[:40]}...",
                        "title": f"[Sector/Global Alert] {title}",
                        "url": link,
                        "published": pub_date,
                        "source": "Google News Live RSS",
                    }
                )
            return articles
    except Exception:
        return []
