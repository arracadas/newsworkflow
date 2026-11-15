from worker.workflows.news.models import (
    ArticleSummaries,
    ExpandedQueries,
    FilteredSources,
    SearchResult,
)


class FakeParsedResponse:
    def __init__(self, parsed):
        self.parsed = parsed


class FakeChat:
    """Dispatches parse_async calls by the requested response_format model."""

    def __init__(self, payloads: dict[type, object]):
        self._payloads = payloads
        self.calls: list[dict] = []

    async def parse_async(self, **kwargs):
        self.calls.append(kwargs)
        response_format = kwargs.get("response_format")
        if response_format not in self._payloads:
            raise AssertionError(f"unexpected response_format: {response_format}")
        return FakeParsedResponse(self._payloads[response_format])


class FakeMistralClient:
    def __init__(self, payloads: dict[type, object]):
        self.chat = FakeChat(payloads)


class ExplodingClient:
    def __init__(self):
        self.chat = None

    def __getattr__(self, name):
        raise AssertionError(f"LLM client should not be called, got .{name}")


def make_search_results(prefix: str, count: int) -> list[SearchResult]:
    return [
        SearchResult(
            title=f"{prefix} story {i}",
            url=f"https://{prefix}.example.com/news/{i}",
            snippet=f"Snippet for {prefix} story {i}.",
        )
        for i in range(count)
    ]


DEFAULT_EXPANSION = ExpandedQueries(
    topics=[
        {"topic": "ai", "queries": ["ai breaking news", "ai latest developments"]},
        {"topic": "climate", "queries": ["climate change news today"]},
    ]
)

DEFAULT_FILTERED = FilteredSources(
    articles=[
        {
            "url": "https://reuters.com/news/0",
            "title": "Reuters story 0",
            "snippet": "Reuters snippet 0.",
            "source": "Reuters",
            "reason": "Established wire service.",
        },
        {
            "url": "https://bbc.com/news/1",
            "title": "BBC story 1",
            "snippet": "BBC snippet 1.",
            "source": "BBC",
            "reason": "Public broadcaster.",
        },
        {
            "url": "https://hallucinated.example.com/fake",
            "title": "Invented",
            "snippet": "Not in candidates.",
            "source": "blog",
            "reason": "Should be dropped.",
        },
    ]
)

DEFAULT_SUMMARIES = ArticleSummaries(
    articles=[
        {
            "title": "Reuters story 0",
            "url": "https://reuters.com/news/0",
            "source": "Reuters",
            "summary": "Summary of the Reuters story.",
            "key_topics": ["ai"],
        },
        {
            "title": "BBC story 1",
            "url": "https://bbc.com/news/1",
            "source": "BBC",
            "summary": "Summary of the BBC story.",
            "key_topics": ["ai", "policy"],
        },
    ]
)
