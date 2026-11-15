from datetime import datetime, timedelta, timezone

import mistralai.workflows as workflows

from worker.workflows.news import llm
from worker.workflows.news.duckduckgo import search_duckduckgo
from worker.workflows.news.models import (
    MAX_ARTICLES_PER_TOPIC,
    MAX_RESULTS_PER_QUERY,
    ArticleSummary,
    CredibleArticle,
    FilterRequest,
    NewsSearchInput,
    NewsSearchOutput,
    QueryExpansion,
    SearchRequest,
    SummaryRequest,
    TopicDigest,
    TopicFilterResult,
    TopicSearchResults,
)


def _mistral_client():
    # Imported lazily so the workflow sandbox never loads the API client stack at
    # workflow-import time; activities run outside the sandbox.
    from mistralai.workflows.client import get_mistral_client

    return get_mistral_client()


@workflows.activity(start_to_close_timeout=timedelta(minutes=2), retry_policy_max_attempts=3)
async def expand_search_queries(topics: list[str]) -> QueryExpansion:
    client = _mistral_client()
    expanded = await llm.expand_queries(client, topics)
    return QueryExpansion(
        generated_at=datetime.now(timezone.utc).isoformat(),
        topics=expanded.topics,
    )


@workflows.activity(start_to_close_timeout=timedelta(seconds=60), retry_policy_max_attempts=3)
async def search_recent_news(request: NewsSearchInput) -> NewsSearchOutput:
    query = f"{request.topic} latest news"
    results = await search_duckduckgo(query, max_results=MAX_RESULTS_PER_QUERY)
    return NewsSearchOutput(topic=request.topic, query=query, results=results)


@workflows.activity(start_to_close_timeout=timedelta(seconds=60), retry_policy_max_attempts=3)
async def search_news(request: SearchRequest) -> TopicSearchResults:
    results = await search_duckduckgo(request.query, max_results=request.max_results)
    return TopicSearchResults(topic=request.topic, query=request.query, results=results)


@workflows.activity(start_to_close_timeout=timedelta(minutes=2), retry_policy_max_attempts=2)
async def filter_credible_sources(request: FilterRequest) -> TopicFilterResult:
    if not request.results:
        return TopicFilterResult(topic=request.topic, articles=[])
    client = _mistral_client()
    filtered = await llm.filter_sources(client, request)
    articles = llm.validated_articles(filtered, request.results)
    return TopicFilterResult(topic=request.topic, articles=articles)


@workflows.activity(start_to_close_timeout=timedelta(minutes=3), retry_policy_max_attempts=2)
async def summarize_articles(request: SummaryRequest) -> TopicDigest:
    if not request.articles:
        return TopicDigest(topic=request.topic, queries=request.queries, articles=[])
    client = _mistral_client()
    summaries = await llm.summarize_articles(client, request)
    by_url = {a.url: a for a in request.articles}
    seen: set[str] = set()
    articles: list[ArticleSummary] = []
    for item in summaries.articles:
        base = by_url.get(item.url)
        if base is None or item.url in seen:
            continue
        seen.add(item.url)
        articles.append(
            ArticleSummary(
                title=base.title or item.title,
                url=item.url,
                source=base.source,
                summary=item.summary or base.snippet,
                key_topics=item.key_topics,
            )
        )
        if len(articles) >= MAX_ARTICLES_PER_TOPIC:
            break
    return TopicDigest(topic=request.topic, queries=request.queries, articles=articles)
