import mistralai.workflows as workflows

from worker.workflows.news.activities import search_recent_news
from worker.workflows.news.models import NewsSearchInput, NewsSearchOutput


@workflows.workflow.define(
    name="news-search",
    workflow_display_name="News Search",
    workflow_description=(
        "Manual-trigger workflow: takes a single topic, runs a web search for recent "
        "news about it, and returns the top 5 results with title, URL, and snippet."
    ),
)
class NewsSearchWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, input: NewsSearchInput) -> NewsSearchOutput:
        return await search_recent_news(input)
