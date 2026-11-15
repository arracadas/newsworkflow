from urllib.parse import urlparse

from worker.workflows.news.models import CredibleArticle, MAX_ARTICLES_PER_TOPIC, SearchResult

TRUSTED_NEWS_DOMAINS = [
    "reuters.com",
    "apnews.com",
    "bbc.com",
    "bbc.co.uk",
    "npr.org",
    "theguardian.com",
    "nytimes.com",
    "washingtonpost.com",
    "bloomberg.com",
    "ft.com",
    "wsj.com",
    "cnbc.com",
    "aljazeera.com",
    "france24.com",
    "dw.com",
    "euronews.com",
    "techcrunch.com",
    "arstechnica.com",
    "wired.com",
    "theverge.com",
    "nature.com",
    "science.org",
    "scientificamerican.com",
    "ieee.org",
    "who.int",
    "un.org",
    "nasa.gov",
    "esa.int",
    "cdc.gov",
    "europa.eu",
]

SOCIAL_OR_AGGREGATOR_DOMAINS = [
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "reddit.com",
    "tiktok.com",
    "youtube.com",
    "linkedin.com",
    "threads.net",
    "news.google.com",
    "news.yahoo.com",
    "bing.com",
    "drudgereport.com",
    "flipboard.com",
    "smartnews.com",
    "msn.com",
    "apple.news",
]


def article_source(url: str) -> str:
    return urlparse(url).netloc.removeprefix("www.")


def _normalized_host(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def is_credible_source(url: str) -> bool:
    host = _normalized_host(url)
    if not host:
        return False
    if any(host == d or host.endswith("." + d) for d in SOCIAL_OR_AGGREGATOR_DOMAINS):
        return False
    return any(host == d or host.endswith("." + d) for d in TRUSTED_NEWS_DOMAINS)


def filter_credible_results(results: list[SearchResult]) -> list[CredibleArticle]:
    """Keep deduplicated results from trusted news outlets, capped per topic."""
    seen_urls: set[str] = set()
    articles: list[CredibleArticle] = []
    for result in results:
        if result.url in seen_urls or not is_credible_source(result.url):
            continue
        seen_urls.add(result.url)
        articles.append(
            CredibleArticle(
                url=result.url,
                title=result.title,
                snippet=result.snippet,
                source=article_source(result.url),
            )
        )
        if len(articles) >= MAX_ARTICLES_PER_TOPIC:
            break
    return articles
