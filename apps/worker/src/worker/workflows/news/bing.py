import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, urlparse

from worker.workflows.news.models import MAX_RESULTS_PER_QUERY, SearchResult

BING_RSS_URL = "https://www.bing.com/search"


def _unwrap_bing_url(href: str) -> str | None:
    parsed = urlparse(href)
    if "bing.com" in parsed.netloc and parsed.path.startswith("/ck/"):
        target = parse_qs(parsed.query).get("u")
        if not target:
            return None
        import base64

        encoded = target[0]
        if encoded.startswith("a1"):
            encoded = encoded[2:]
        try:
            padded = encoded + "=" * (-len(encoded) % 4)
            decoded = base64.urlsafe_b64decode(padded).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None
        if decoded.startswith(("http://", "https://")):
            return decoded
        return None
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return href
    return None


def parse_rss_results(rss: str, max_results: int = MAX_RESULTS_PER_QUERY) -> list[SearchResult]:
    try:
        root = ET.fromstring(rss)
    except ET.ParseError:
        return []

    results: list[SearchResult] = []
    seen_urls: set[str] = set()
    for item in root.iter("item"):
        if len(results) >= max_results:
            break
        title = (item.findtext("title") or "").strip()
        link = _unwrap_bing_url((item.findtext("link") or "").strip())
        snippet = (item.findtext("description") or "").strip()
        if not title or not link or link in seen_urls:
            continue
        seen_urls.add(link)
        results.append(SearchResult(title=title, url=link, snippet=snippet))
    return results


async def search_bing_rss(
    query: str,
    max_results: int = MAX_RESULTS_PER_QUERY,
    timeout: float = 20.0,
) -> list[SearchResult]:
    import httpx

    from worker.workflows.news.duckduckgo import REQUEST_HEADERS

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers=REQUEST_HEADERS,
    ) as client:
        try:
            response = await client.get(BING_RSS_URL, params={"q": query, "format": "rss"})
        except httpx.HTTPError:
            return []
        if response.status_code != 200:
            return []
        return parse_rss_results(response.text, max_results)
