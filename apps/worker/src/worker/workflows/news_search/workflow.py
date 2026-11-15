import mistralai.workflows as workflows

from worker.workflows.news_search.activities import search_topic_news
from worker.workflows.news_search.models import NewsSearchInput, NewsSearchOutput


@workflows.workflow.define(
    name="news-search",
    workflow_display_name="News Search",
    workflow_description=(
        "Takes a single topic and returns the top 5 recent news results for it, "
        "each with title, url, and snippet."
    ),
)
class NewsSearchWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, input: NewsSearchInput) -> NewsSearchOutput:
        results = await search_topic_news(input.topic)
        return NewsSearchOutput(topic=input.topic, results=results)
