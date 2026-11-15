from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

from worker.workflows.news.models import MAX_RESULTS_PER_QUERY, SearchResult

DDG_HTML_URL = "https://html.duckduckgo.com/html/"
DDG_LITE_URL = "https://lite.duckduckgo.com/lite/"

class SearchUnavailableError(RuntimeError):
    """Raised when every DuckDuckGo endpoint fails, so callers can surface a clear error."""


REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _unwrap_url(href: str) -> str | None:
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com"):
        if not parsed.path.startswith("/l/"):
            return None
        target = parse_qs(parsed.query).get("uddg")
        if not target:
            return None
        return target[0]
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return href
    return None


class _DuckDuckGoResultParser(HTMLParser):
    """Collects result links and snippets in document order from DDG html/lite pages."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.events: list[tuple[str, str, str]] = []
        self._link_href: str | None = None
        self._link_text: list[str] = []
        self._capturing_snippet = False
        self._snippet_text: list[str] = []
        self._in_result_link_cell = False

    @staticmethod
    def _classes(attrs: dict[str, str]) -> set[str]:
        return set((attrs.get("class") or "").split())

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {k: (v or "") for k, v in attrs_list}
        classes = self._classes(attrs)
        if tag == "td":
            if "result-link" in classes:
                self._in_result_link_cell = True
            if "result-snippet" in classes:
                self._capturing_snippet = True
                self._snippet_text = []
        elif tag == "a":
            if "result__snippet" in classes:
                self._capturing_snippet = True
                self._snippet_text = []
            elif "result__a" in classes or self._in_result_link_cell:
                self._link_href = attrs.get("href") or ""
                self._link_text = []

    def handle_data(self, data: str) -> None:
        if self._link_href is not None:
            self._link_text.append(data)
        if self._capturing_snippet:
            self._snippet_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            if self._link_href is not None:
                self.events.append(("link", self._link_href, "".join(self._link_text).strip()))
                self._link_href = None
                self._link_text = []
            elif self._capturing_snippet:
                self.events.append(("snippet", "", "".join(self._snippet_text).strip()))
                self._capturing_snippet = False
                self._snippet_text = []
        elif tag == "td":
            if self._capturing_snippet:
                self.events.append(("snippet", "", "".join(self._snippet_text).strip()))
                self._capturing_snippet = False
                self._snippet_text = []
            self._in_result_link_cell = False


def parse_search_results(html: str, max_results: int = MAX_RESULTS_PER_QUERY) -> list[SearchResult]:
    parser = _DuckDuckGoResultParser()
    parser.feed(html)
    parser.close()

    results: list[SearchResult] = []
    seen_urls: set[str] = set()
    pending: tuple[str, str, str] | None = None

    def flush(item: tuple[str, str, str]) -> None:
        href, title, snippet = item
        url = _unwrap_url(href)
        if url and url not in seen_urls and len(results) < max_results:
            seen_urls.add(url)
            results.append(SearchResult(title=title, url=url, snippet=snippet))

    for kind, href, text in parser.events:
        if kind == "snippet":
            if pending is not None:
                pending = (pending[0], pending[1], text)
        else:
            if pending is not None:
                flush(pending)
            pending = (href, text, "")
    if pending is not None:
        flush(pending)

    return [result for result in results if result.title]


async def search_duckduckgo(
    query: str,
    max_results: int = MAX_RESULTS_PER_QUERY,
    timeout: float = 20.0,
) -> list[SearchResult]:
    # Imported lazily: httpx pulls in urllib.request, which the workflow sandbox restricts
    # at workflow-import time. Activities run outside the sandbox, so this is safe here.
    import httpx

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers=REQUEST_HEADERS,
    ) as client:
        failures: list[str] = []
        reached_ok = False
        for endpoint in (DDG_HTML_URL, DDG_LITE_URL):
            try:
                response = await client.get(endpoint, params={"q": query})
            except httpx.HTTPError as exc:
                failures.append(f"{endpoint}: {exc}")
                continue
            if response.status_code != 200:
                failures.append(f"{endpoint}: HTTP {response.status_code}")
                continue
            reached_ok = True
            results = parse_search_results(response.text, max_results)
            if results:
                return results
        if failures and not reached_ok:
            raise SearchUnavailableError(
                "Web search failed for query "
                f"'{query}' (attempted DuckDuckGo html and lite endpoints): "
                + "; ".join(failures)
            )
    return []
