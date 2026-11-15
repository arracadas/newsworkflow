import uuid

from mistralai.workflows.core.execution.concurrency import ParallelExecutionWorkflow
from mistralai.workflows.core.execution.concurrency._concurrency_workflow import (
    OnBehalfOfParallelExecutionWorkflow,
)
from mistralai.workflows.testing import create_test_worker

from worker.workflows.news import models as news_models
from worker.workflows.news_search import activities
from worker.workflows.news_search.models import NewsSearchInput, NewsSearchOutput
from worker.workflows.news_search.workflow import NewsSearchWorkflow

TEST_TASK_QUEUE = "test-task-queue"


async def _fake_search(query: str, max_results: int = 5) -> list[news_models.SearchResult]:
    return [
        news_models.SearchResult(
            title=f"Story {i}",
            url=f"https://news.example.com/{i}",
            snippet=f"Snippet {i} about {query}.",
        )
        for i in range(max_results)
    ]


async def test_news_search_end_to_end(temporal_env, monkeypatch):
    monkeypatch.setattr(activities, "search_duckduckgo", _fake_search)

    async with create_test_worker(
        temporal_env,
        [NewsSearchWorkflow, ParallelExecutionWorkflow, OnBehalfOfParallelExecutionWorkflow],
        activities=[activities.search_topic_news],
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
    assert len(output.results) == 5
    assert all(r.title and r.url.startswith("http") and r.snippet for r in output.results)
