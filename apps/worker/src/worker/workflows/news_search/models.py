from pydantic import BaseModel, Field

from worker.workflows.news.models import SearchResult

MAX_RESULTS = 5


class NewsSearchInput(BaseModel):
    topic: str = Field(
        min_length=1,
        description="The topic to search for recent news about.",
    )


class NewsSearchOutput(BaseModel):
    topic: str
    results: list[SearchResult] = Field(
        description="The top search results for the topic, each with title, url, and snippet.",
    )
