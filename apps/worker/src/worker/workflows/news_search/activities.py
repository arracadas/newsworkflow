from datetime import timedelta

import mistralai.workflows as workflows

from worker.workflows.news.duckduckgo import search_duckduckgo
from worker.workflows.news.models import SearchResult
from worker.workflows.news_search.models import MAX_RESULTS


@workflows.activity(start_to_close_timeout=timedelta(seconds=60), retry_policy_max_attempts=3)
async def search_topic_news(topic: str) -> list[SearchResult]:
    results = await search_duckduckgo(f"{topic} latest news", max_results=MAX_RESULTS)
    return results[:MAX_RESULTS]
