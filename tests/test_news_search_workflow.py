import uuid

from mistralai.workflows.testing import create_test_worker

from worker.workflows.news import activities
from worker.workflows.news.models import NewsSearchInput, NewsSearchOutput, SearchResult
from worker.workflows.news.search_workflow import NewsSearchWorkflow

from fakes import ExplodingClient, make_search_results

TEST_TASK_QUEUE = "test-task-queue"


async def test_news_search_end_to_end(temporal_env, monkeypatch):
    fake_results = make_search_results("search", 5)
    monkeypatch.setattr(activities, "_mistral_client", lambda: ExplodingClient())
    monkeypatch.setattr(
        activities,
        "search_duckduckgo",
        lambda query, max_results=5: _fake_search(query, max_results, fake_results),
    )

    async with create_test_worker(
        temporal_env,
        [NewsSearchWorkflow],
        activities=[activities.search_recent_news],
        task_queue=TEST_TASK_QUEUE,
    ):
        handle = await temporal_env.client.start_workflow(
            NewsSearchWorkflow,
            NewsSearchInput(topic="artificial intelligence").model_dump(),
            id=f"news-search-test-{uuid.uuid4()}",
            task_queue=TEST_TASK_QUEUE,
        )
        result = await handle.result()

    output = NewsSearchOutput.model_validate(result)
    assert output.topic == "artificial intelligence"
    assert output.query == "artificial intelligence latest news"
    assert len(output.results) == 5
    assert all(r.title and r.url.startswith("http") and r.snippet for r in output.results)


async def test_news_search_returns_fewer_when_engine_has_less(temporal_env, monkeypatch):
    fake_results = make_search_results("sparse", 2)
    monkeypatch.setattr(activities, "_mistral_client", lambda: ExplodingClient())
    monkeypatch.setattr(
        activities,
        "search_duckduckgo",
        lambda query, max_results=5: _fake_search(query, max_results, fake_results),
    )

    async with create_test_worker(
        temporal_env,
        [NewsSearchWorkflow],
        activities=[activities.search_recent_news],
        task_queue=TEST_TASK_QUEUE,
    ):
        handle = await temporal_env.client.start_workflow(
            NewsSearchWorkflow,
            NewsSearchInput(topic="climate change").model_dump(),
            id=f"news-search-sparse-test-{uuid.uuid4()}",
            task_queue=TEST_TASK_QUEUE,
        )
        result = await handle.result()

    output = NewsSearchOutput.model_validate(result)
    assert output.topic == "climate change"
    assert len(output.results) == 2
    assert [r.url for r in output.results] == [r.url for r in fake_results]


async def _fake_search(query: str, max_results: int, results: list[SearchResult]):
    assert query
    return results[:max_results]
