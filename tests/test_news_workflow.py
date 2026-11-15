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
    NewsDigest,
    NewsDigestInput,
    NO_CREDIBLE_RESULTS_NOTE,
    SearchResult,
)
from worker.workflows.news.workflow import NewsDigestWorkflow

from fakes import (
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


def _default_expansion():
    return ExpandedQueries(
        topics=[
            {"topic": "ai", "queries": ["ai breaking news", "ai latest"]},
            {"topic": "climate", "queries": ["climate news today", "climate latest developments"]},
        ]
    )


async def _run(monkeypatch, temporal_env, search_impl, input, expansion=None):
    expansion = expansion or _default_expansion()
    client = FakeMistralClient(
        {
            ExpandedQueries: expansion,
            ArticleSummaries: DEFAULT_SUMMARIES,
        }
    )
    monkeypatch.setattr(activities, "_mistral_client", lambda: client)
    monkeypatch.setattr(activities, "search_duckduckgo", search_impl)

    async with create_test_worker(
        temporal_env,
        [NewsDigestWorkflow, ParallelExecutionWorkflow, OnBehalfOfParallelExecutionWorkflow],
        activities=[
            activities.expand_search_queries,
            activities.search_news,
            activities.summarize_articles,
        ],
        task_queue=TEST_TASK_QUEUE,
    ):
        handle = await temporal_env.client.start_workflow(
            NewsDigestWorkflow,
            input.model_dump(),
            id=f"news-digest-test-{uuid.uuid4()}",
            task_queue=TEST_TASK_QUEUE,
        )
        return NewsDigest.model_validate(await handle.result()), client


async def test_news_digest_end_to_end(monkeypatch, temporal_env):
    digest, client = await _run(monkeypatch, temporal_env, _fake_search, NewsDigestInput(topics="ai, climate"))

    assert digest.error is None
    assert digest.generated_at
    assert [t.topic for t in digest.topics] == ["ai", "climate"]

    ai = digest.topics[0]
    assert ai.queries == ["ai breaking news", "ai latest"]
    assert len(ai.queries) == 2
    assert len(ai.articles) >= 2
    assert all(a.url.startswith("http") for a in ai.articles)
    assert all(a.summary for a in ai.articles)
    assert ai.note is None

    climate = digest.topics[1]
    assert climate.queries == ["climate news today", "climate latest developments"]
    assert len(climate.articles) >= 2

    llm_calls = client.chat.calls
    response_formats = {call["response_format"] for call in llm_calls}
    assert ExpandedQueries in response_formats
    assert ArticleSummaries in response_formats
    expansion_call = next(c for c in llm_calls if c["response_format"] is ExpandedQueries)
    assert "last 7 days" in expansion_call["messages"][0]["content"]
    assert "exactly 2" in expansion_call["messages"][1]["content"]
    summarize_call = next(c for c in llm_calls if c["response_format"] is ArticleSummaries)
    assert "3 sentences" in summarize_call["messages"][1]["content"]


async def test_topic_without_credible_results_gets_note(monkeypatch, temporal_env):
    async def search_only_blogs(query: str, max_results: int = 5) -> list[SearchResult]:
        return [
            SearchResult(
                title=f"Blog {i}",
                url=f"https://blog.example.com/{query}/{i}",
                snippet="Untrusted snippet.",
            )
            for i in range(max_results)
        ]

    digest, client = await _run(
        monkeypatch,
        temporal_env,
        search_only_blogs,
        NewsDigestInput(topics=["ai", "climate"]),
    )

    assert digest.error is None
    assert all(t.note == NO_CREDIBLE_RESULTS_NOTE for t in digest.topics)
    assert all(t.articles == [] for t in digest.topics)
    assert all(call["response_format"] is not ArticleSummaries for call in client.chat.calls)


async def test_search_failure_returns_clear_error(monkeypatch, temporal_env):
    from worker.workflows.news.duckduckgo import SearchUnavailableError

    async def failing_search(query: str, max_results: int = 5) -> list[SearchResult]:
        raise SearchUnavailableError(f"Web search failed for query '{query}'")

    digest, _ = await _run(
        monkeypatch,
        temporal_env,
        failing_search,
        NewsDigestInput(topics=["ai"]),
    )

    assert digest.error is not None
    assert "Web search failed" in digest.error
    assert digest.topics == []
