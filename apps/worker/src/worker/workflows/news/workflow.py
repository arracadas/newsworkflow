import mistralai.workflows as workflows

from worker.workflows.news.activities import (
    expand_search_queries,
    search_news,
    summarize_articles,
)
from worker.workflows.news.credibility import filter_credible_results
from worker.workflows.news.models import (
    MAX_CANDIDATES_PER_TOPIC,
    NewsDigest,
    NewsDigestInput,
    NO_CREDIBLE_RESULTS_NOTE,
    SearchRequest,
    SearchResult,
    SummaryRequest,
    TopicDigest,
)


def _failure_detail(exc: Exception) -> str:
    details: list[str] = []
    current: Exception | None = exc
    while current is not None and len(details) < 6:
        message = str(getattr(current, "message", None) or current)
        if message and message not in details:
            details.append(message)
        current = getattr(current, "cause", None) or current.__cause__
    return "; ".join(details)


@workflows.workflow.define(
    name="news-digest",
    workflow_display_name="Personalized News Digest",
    workflow_description=(
        "Finds relevant news from trusted sources for up to three user-selected topics: "
        "expands each topic into two precise search queries for breaking news and recent "
        "developments from the last 7 days, searches DuckDuckGo for the top 5 results per "
        "query, keeps only deduplicated results from established news outlets (at least "
        "two per topic when available), and generates a neutral 3-sentence summary for "
        "each article."
    ),
)
class NewsDigestWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, input: NewsDigestInput) -> NewsDigest:
        expansion = await expand_search_queries(input.topics)

        search_requests = [
            SearchRequest(topic=topic_queries.topic, query=query)
            for topic_queries in expansion.topics
            for query in topic_queries.queries
        ]
        try:
            search_results = (
                await workflows.execute_activities_in_parallel(search_news, items=search_requests)
            ) or []
        except Exception as exc:
            return NewsDigest(
                generated_at=expansion.generated_at,
                topics=[],
                error=(
                    "Web search failed, so no news digest could be generated: "
                    f"{_failure_detail(exc) or 'search step error'}. "
                    "Please retry the run."
                ),
            )

        candidates: dict[str, list[SearchResult]] = {
            topic_queries.topic: [] for topic_queries in expansion.topics
        }
        seen_urls: dict[str, set[str]] = {
            topic_queries.topic: set() for topic_queries in expansion.topics
        }
        for result in search_results:
            for item in result.results:
                topic = result.topic
                if item.url in seen_urls[topic] or len(candidates[topic]) >= MAX_CANDIDATES_PER_TOPIC:
                    continue
                seen_urls[topic].add(item.url)
                candidates[topic].append(item)

        summary_requests = [
            SummaryRequest(
                topic=topic_queries.topic,
                queries=topic_queries.queries,
                articles=filter_credible_results(candidates[topic_queries.topic]),
            )
            for topic_queries in expansion.topics
        ]
        summary_requests = [request for request in summary_requests if request.articles]
        digests = (
            await workflows.execute_activities_in_parallel(summarize_articles, items=summary_requests)
            if summary_requests
            else []
        ) or []

        digests_by_topic = {digest.topic: digest for digest in digests}
        topics = [
            digests_by_topic.get(
                topic_queries.topic,
                TopicDigest(
                    topic=topic_queries.topic,
                    queries=topic_queries.queries,
                    articles=[],
                    note=NO_CREDIBLE_RESULTS_NOTE,
                ),
            )
            for topic_queries in expansion.topics
        ]
        return NewsDigest(generated_at=expansion.generated_at, topics=topics)
