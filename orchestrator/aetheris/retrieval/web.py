"""Web search fallback for the CRAG loop: Tavily -> SerpAPI -> DuckDuckGo (no key)."""
from __future__ import annotations

import html as html_lib
import re
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from aetheris.config import settings

_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def _provider() -> str:
    want = settings.WEB_SEARCH_PROVIDER
    if want != "auto":
        return want
    if settings.TAVILY_API_KEY:
        return "tavily"
    if settings.SERPAPI_API_KEY:
        return "serpapi"
    return "duckduckgo"


async def web_search(query: str, k: int | None = None) -> dict:
    """Returns {provider, ok, results:[{title,url,snippet}], error?}."""
    k = k or settings.WEB_RESULT_COUNT
    provider = _provider()
    timeout = float(settings.WEB_TIMEOUT_SECONDS)
    try:
        if provider == "tavily":
            results = await _tavily(query, k, timeout)
        elif provider == "serpapi":
            results = await _serpapi(query, k, timeout)
        else:
            results = await _duckduckgo(query, k, timeout)
        return {"provider": provider, "ok": bool(results), "results": results}
    except Exception as exc:
        return {"provider": provider, "ok": False, "results": [], "error": str(exc)}


async def _tavily(query: str, k: int, timeout: float) -> list[dict]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            "https://api.tavily.com/search",
            json={"api_key": settings.TAVILY_API_KEY, "query": query,
                  "max_results": k, "include_answer": False},
        )
        resp.raise_for_status()
        data = resp.json()
    return [{"title": r.get("title", ""), "url": r.get("url", ""),
             "snippet": r.get("content", "")[:600]} for r in data.get("results", [])]


async def _serpapi(query: str, k: int, timeout: float) -> list[dict]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(
            "https://serpapi.com/search.json",
            params={"q": query, "api_key": settings.SERPAPI_API_KEY, "num": k, "engine": "google"},
        )
        resp.raise_for_status()
        data = resp.json()
    return [{"title": r.get("title", ""), "url": r.get("link", ""),
             "snippet": r.get("snippet", "")[:600]}
            for r in data.get("organic_results", [])[:k]]


async def _duckduckgo(query: str, k: int, timeout: float) -> list[dict]:
    async with httpx.AsyncClient(timeout=timeout, headers=_UA, follow_redirects=True) as client:
        resp = await client.post("https://html.duckduckgo.com/html/", data={"q": query})
        resp.raise_for_status()
        page = resp.text
    results: list[dict] = []
    # anchors: <a rel="nofollow" class="result__a" href="...">Title</a>
    for m in re.finditer(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page, re.S | re.I
    ):
        href, title_html = m.group(1), m.group(2)
        title = html_lib.unescape(re.sub(r"<[^>]+>", "", title_html)).strip()
        url = _unwrap_ddg(href)
        if not title or not url:
            continue
        results.append({"title": title, "url": url, "snippet": ""})
        if len(results) >= k:
            break
    # snippets
    snippets = [
        html_lib.unescape(re.sub(r"<[^>]+>", "", s)).strip()
        for s in re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', page, re.S | re.I)
    ]
    for i, snip in enumerate(snippets[:len(results)]):
        results[i]["snippet"] = snip[:600]
    return results


def _unwrap_ddg(href: str) -> str:
    if href.startswith("//"):
        href = "https:" + href
    try:
        parsed = urlparse(href)
        if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
            q = parse_qs(parsed.query)
            if "uddg" in q:
                return unquote(q["uddg"][0])
        return href
    except Exception:
        return href
