import mistralai.workflows as workflows

from worker.workflows.news.activities import (
    expand_search_queries,
    filter_credible_sources,
    search_news,
    summarize_articles,
)
from worker.workflows.news.models import (
    MAX_CANDIDATES_PER_TOPIC,
    FilterRequest,
    NewsDigest,
    NewsDigestInput,
    SearchRequest,
    SearchResult,
    SummaryRequest,
    TopicDigest,
)


@workflows.workflow.define(
    name="news-digest",
    workflow_display_name="News Digest",
    workflow_description=(
        "Finds relevant, credible news for up to three user-selected topics: expands each "
        "topic into precise recent-news search queries, searches DuckDuckGo for the top "
        "results, filters them down to trusted sources (at least two per topic when "
        "available), and generates a concise summary for each selected link."
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
        search_results = (
            await workflows.execute_activities_in_parallel(search_news, items=search_requests)
        ) or []

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

        filter_requests = [
            FilterRequest(topic=topic_queries.topic, results=candidates[topic_queries.topic])
            for topic_queries in expansion.topics
        ]
        filtered = (
            await workflows.execute_activities_in_parallel(filter_credible_sources, items=filter_requests)
        ) or []

        queries_by_topic = {t.topic: t.queries for t in expansion.topics}
        summary_requests = [
            SummaryRequest(
                topic=result.topic,
                queries=queries_by_topic.get(result.topic, []),
                articles=result.articles,
            )
            for result in filtered
        ]
        digests = (
            await workflows.execute_activities_in_parallel(summarize_articles, items=summary_requests)
        ) or []

        digests_by_topic = {digest.topic: digest for digest in digests}
        topics = [
            digests_by_topic.get(
                topic_queries.topic,
                TopicDigest(topic=topic_queries.topic, queries=topic_queries.queries, articles=[]),
            )
            for topic_queries in expansion.topics
        ]
        return NewsDigest(generated_at=expansion.generated_at, topics=topics)
