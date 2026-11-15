import uuid

from mistralai.workflows.core.execution.concurrency import ParallelExecutionWorkflow
from mistralai.workflows.core.execution.concurrency._concurrency_workflow import (
    OnBehalfOfParallelExecutionWorkflow,
)
from mistralai.workflows.testing import create_test_worker

from worker.workflows.news import activities
from worker.workflows.news.models import (
    ArticleSummaries,
    ExpandedQueries,
    FilteredSources,
    NewsDigest,
    NewsDigestInput,
    SearchResult,
)
from worker.workflows.news.workflow import NewsDigestWorkflow

from fakes import (
    DEFAULT_EXPANSION,
    DEFAULT_FILTERED,
    DEFAULT_SUMMARIES,
    FakeMistralClient,
)

TEST_TASK_QUEUE = "test-task-queue"


async def _fake_search(query: str, max_results: int = 5) -> list[SearchResult]:
    base = [
        SearchResult(
            title="Reuters story",
            url="https://reuters.com/news/0",
            snippet="Reuters snippet.",
        ),
        SearchResult(
            title="BBC story",
            url="https://bbc.com/news/1",
            snippet="BBC snippet.",
        ),
    ]
    extra = [
        SearchResult(title=f"Extra {i}", url=f"https://blog.example.com/{i}", snippet="extra")
        for i in range(max_results)
    ]
    return (base + extra)[:max_results]


async def test_news_digest_end_to_end(temporal_env, monkeypatch):
    expansion = ExpandedQueries(
        topics=[
            {"topic": "ai", "queries": ["ai breaking news", "ai latest"]},
            {"topic": "climate", "queries": ["climate news today"]},
        ]
    )
    client = FakeMistralClient(
        {
            ExpandedQueries: expansion,
            FilteredSources: DEFAULT_FILTERED,
            ArticleSummaries: DEFAULT_SUMMARIES,
        }
    )
    monkeypatch.setattr(activities, "_mistral_client", lambda: client)
    monkeypatch.setattr(activities, "search_duckduckgo", _fake_search)

    async with create_test_worker(
        temporal_env,
        [NewsDigestWorkflow, ParallelExecutionWorkflow, OnBehalfOfParallelExecutionWorkflow],
        activities=[
            activities.expand_search_queries,
            activities.search_news,
            activities.filter_credible_sources,
            activities.summarize_articles,
        ],
        task_queue=TEST_TASK_QUEUE,
    ):
        handle = await temporal_env.client.start_workflow(
            NewsDigestWorkflow,
            NewsDigestInput(topics=["ai", "climate"]).model_dump(),
            id=f"news-digest-test-{uuid.uuid4()}",
            task_queue=TEST_TASK_QUEUE,
        )
        result = await handle.result()

    digest = NewsDigest.model_validate(result)
    assert digest.generated_at
    assert [t.topic for t in digest.topics] == ["ai", "climate"]

    ai = digest.topics[0]
    assert ai.queries == ["ai breaking news", "ai latest"]
    assert len(ai.articles) >= 2
    assert all(a.url.startswith("http") for a in ai.articles)
    assert all(a.summary for a in ai.articles)

    climate = digest.topics[1]
    assert climate.queries == ["climate news today"]
    assert len(climate.articles) >= 2

    llm_calls = client.chat.calls
    response_formats = {call["response_format"] for call in llm_calls}
    assert ExpandedQueries in response_formats
    assert FilteredSources in response_formats
    assert ArticleSummaries in response_formats
    expansion_call = next(c for c in llm_calls if c["response_format"] is ExpandedQueries)
    assert "2026 or later" in expansion_call["messages"][0]["content"]
