from urllib.parse import urlparse

from worker.workflows.news.models import (
    MAX_ARTICLES_PER_TOPIC,
    ArticleSummaries,
    CredibleArticle,
    ExpandedQueries,
    FilterRequest,
    FilteredSources,
    SearchResult,
    SummaryRequest,
)
from worker.workflows.news.prompts import (
    FILTER_SOURCES_SYSTEM_PROMPT,
    QUERY_EXPANSION_SYSTEM_PROMPT,
    SUMMARIZE_SYSTEM_PROMPT,
    filter_sources_user_prompt,
    query_expansion_user_prompt,
    summarize_user_prompt,
)

EXPANSION_MODEL = "mistral-medium-latest"
FILTER_MODEL = "mistral-medium-latest"
SUMMARY_MODEL = "mistral-large-latest"


def _parsed(response, model: type) -> object:
    choice = response.choices[0] if response.choices else None
    parsed = choice.message.parsed if choice is not None and choice.message is not None else None
    if parsed is None:
        raise ValueError(f"LLM returned no parsed {model.__name__}")
    return parsed


async def expand_queries(client, topics: list[str]) -> ExpandedQueries:
    response = await client.chat.parse_async(
        model=EXPANSION_MODEL,
        messages=[
            {"role": "system", "content": QUERY_EXPANSION_SYSTEM_PROMPT},
            {"role": "user", "content": query_expansion_user_prompt(topics)},
        ],
        response_format=ExpandedQueries,
    )
    return _parsed(response, ExpandedQueries)


async def filter_sources(client, request: FilterRequest) -> FilteredSources:
    response = await client.chat.parse_async(
        model=FILTER_MODEL,
        messages=[
            {"role": "system", "content": FILTER_SOURCES_SYSTEM_PROMPT},
            {"role": "user", "content": filter_sources_user_prompt(request)},
        ],
        response_format=FilteredSources,
    )
    return _parsed(response, FilteredSources)


async def summarize_articles(client, request: SummaryRequest) -> ArticleSummaries:
    response = await client.chat.parse_async(
        model=SUMMARY_MODEL,
        messages=[
            {"role": "system", "content": SUMMARIZE_SYSTEM_PROMPT},
            {"role": "user", "content": summarize_user_prompt(request)},
        ],
        response_format=ArticleSummaries,
    )
    return _parsed(response, ArticleSummaries)


def article_source(url: str) -> str:
    return urlparse(url).netloc.removeprefix("www.")


def validated_articles(filtered: FilteredSources, results: list[SearchResult]) -> list[CredibleArticle]:
    """Keep only LLM-picked articles whose url was in the candidate list, deduped and capped."""
    by_url = {r.url: r for r in results}
    seen: set[str] = set()
    articles: list[CredibleArticle] = []
    for item in filtered.articles:
        base = by_url.get(item.url)
        if base is None or item.url in seen:
            continue
        seen.add(item.url)
        articles.append(
            CredibleArticle(
                url=item.url,
                title=base.title or item.title,
                snippet=base.snippet or item.snippet,
                source=item.source or article_source(item.url),
                reason=item.reason,
            )
        )
        if len(articles) >= MAX_ARTICLES_PER_TOPIC:
            break
    return articles
