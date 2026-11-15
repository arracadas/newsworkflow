import pytest
from pydantic import ValidationError

import mistralai.workflows as workflows
from worker.workflows.news import activities, llm
from worker.workflows.news.duckduckgo import parse_search_results, search_duckduckgo
from worker.workflows.news.models import (
    MAX_ARTICLES_PER_TOPIC,
    CredibleArticle,
    FilterRequest,
    NewsDigestInput,
    SearchRequest,
    SearchResult,
    SummaryRequest,
)

from fakes import (
    DEFAULT_EXPANSION,
    DEFAULT_FILTERED,
    DEFAULT_SUMMARIES,
    ExplodingClient,
    FakeMistralClient,
    make_search_results,
)

HTML_PAGE = """
<html><body>
<div class="result">
  <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.reuters.com%2Fworld%2Fstory-1&amp;rut=abc">Reuters: story one</a>
  <a class="result__snippet" href="#">Reuters snippet one about the market.</a>
</div>
<div class="result">
  <a rel="nofollow" class="result__a" href="https://www.bbc.com/news/story-2">BBC: story two</a>
  <a class="result__snippet" href="#">BBC snippet two.</a>
</div>
<div class="result">
  <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.reuters.com%2Fworld%2Fstory-1&amp;rut=abc">Reuters: story one duplicate</a>
  <a class="result__snippet" href="#">Duplicate snippet.</a>
</div>
<div class="result">
  <a rel="nofollow" class="result__a" href="https://duckduckgo.com/?q=internal">DuckDuckGo internal</a>
</div>
</body></html>
"""

LITE_PAGE = """
<html><body><table>
<tr><td class="result-link"><a rel="nofollow" href="https://apnews.com/article/one">AP: story one</a></td></tr>
<tr><td class="result-snippet">AP snippet one.</td></tr>
<tr><td class="result-link"><a rel="nofollow" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fnpr.org%2F2026%2Fstory-two">NPR: story two</a></td></tr>
<tr><td class="result-snippet">NPR snippet two.</td></tr>
</table></body></html>
"""


def test_parse_search_results_html_unwraps_redirects_and_dedupes():
    results = parse_search_results(HTML_PAGE, max_results=5)
    assert [r.url for r in results] == [
        "https://www.reuters.com/world/story-1",
        "https://www.bbc.com/news/story-2",
    ]
    assert results[0].title == "Reuters: story one"
    assert results[0].snippet == "Reuters snippet one about the market."


def test_parse_search_results_lite():
    results = parse_search_results(LITE_PAGE, max_results=5)
    assert [r.url for r in results] == [
        "https://apnews.com/article/one",
        "https://npr.org/2026/story-two",
    ]
    assert results[1].snippet == "NPR snippet two."


def test_parse_search_results_caps_at_max_results():
    page = "".join(
        f'<a class="result__a" href="https://example.com/{i}">t{i}</a>'
        f'<a class="result__snippet" href="#">s{i}</a>'
        for i in range(10)
    )
    results = parse_search_results(page, max_results=5)
    assert len(results) == 5
    assert results[4].url == "https://example.com/4"


async def test_search_duckduckgo_falls_back_to_lite(monkeypatch):
    calls = []

    class FakeResponse:
        def __init__(self, status, text):
            self.status_code = status
            self.text = text

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            calls.append(url)
            if "html.duckduckgo.com" in url:
                return FakeResponse(202, "")
            return FakeResponse(200, LITE_PAGE)

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    results = await search_duckduckgo("test query")
    assert calls == [
        "https://html.duckduckgo.com/html/",
        "https://lite.duckduckgo.com/lite/",
    ]
    assert [r.url for r in results] == [
        "https://apnews.com/article/one",
        "https://npr.org/2026/story-two",
    ]


async def test_expand_search_queries_activity(monkeypatch):
    client = FakeMistralClient({type(DEFAULT_EXPANSION): DEFAULT_EXPANSION})
    monkeypatch.setattr(activities, "_mistral_client", lambda: client)
    with workflows.run_activities_locally():
        expansion = await activities.expand_search_queries(["ai", "climate"])
    assert expansion.generated_at.endswith("+00:00")
    assert [t.topic for t in expansion.topics] == ["ai", "climate"]
    call = client.chat.calls[0]
    assert "2026 or later" in call["messages"][0]["content"]
    assert "ai" in call["messages"][1]["content"]


async def test_search_news_activity_returns_top_results(monkeypatch):
    async def fake_search(query, max_results):
        return make_search_results("ai", max_results)

    monkeypatch.setattr(activities, "search_duckduckgo", fake_search)
    with workflows.run_activities_locally():
        result = await activities.search_news(SearchRequest(topic="ai", query="ai news", max_results=5))
    assert result.topic == "ai"
    assert result.query == "ai news"
    assert len(result.results) == 5
    assert all(isinstance(r, SearchResult) for r in result.results)


async def test_filter_credible_sources_drops_hallucinated_urls(monkeypatch):
    candidates = [
        SearchResult(
            title="Reuters story 0",
            url="https://reuters.com/news/0",
            snippet="Original Reuters snippet.",
        ),
        SearchResult(
            title="BBC story 1",
            url="https://bbc.com/news/1",
            snippet="Original BBC snippet.",
        ),
        SearchResult(
            title="Shady blog",
            url="https://shady.example.com/post",
            snippet="Untrusted snippet.",
        ),
    ]
    client = FakeMistralClient({type(DEFAULT_FILTERED): DEFAULT_FILTERED})
    monkeypatch.setattr(activities, "_mistral_client", lambda: client)
    request = FilterRequest(topic="ai", results=candidates)
    with workflows.run_activities_locally():
        result = await activities.filter_credible_sources(request)
    assert [a.url for a in result.articles] == [
        "https://reuters.com/news/0",
        "https://bbc.com/news/1",
    ]
    assert result.articles[0].snippet == "Original Reuters snippet."
    assert result.articles[0].source == "Reuters"
    assert "trusted" in client.chat.calls[0]["messages"][0]["content"].lower()


async def test_filter_credible_sources_empty_results_skips_llm(monkeypatch):
    monkeypatch.setattr(activities, "_mistral_client", lambda: ExplodingClient())
    with workflows.run_activities_locally():
        result = await activities.filter_credible_sources(FilterRequest(topic="ai", results=[]))
    assert result.articles == []


async def test_filter_caps_articles_per_topic(monkeypatch):
    from worker.workflows.news.models import CredibleArticle, FilteredSources

    many = make_search_results("src", MAX_ARTICLES_PER_TOPIC + 3)
    filtered = FilteredSources(
        articles=[
            CredibleArticle(
                url=r.url, title=r.title, snippet=r.snippet, source="src.example.com", reason="ok"
            )
            for r in many
        ]
    )
    monkeypatch.setattr(
        activities, "_mistral_client", lambda: FakeMistralClient({FilteredSources: filtered})
    )
    with workflows.run_activities_locally():
        result = await activities.filter_credible_sources(FilterRequest(topic="src", results=many))
    assert len(result.articles) == MAX_ARTICLES_PER_TOPIC


async def test_summarize_articles_matches_by_url_and_falls_back_to_snippet(monkeypatch):
    articles_in = [
        CredibleArticle(
            url="https://reuters.com/news/0",
            title="Reuters story 0",
            snippet="Reuters snippet fallback.",
            source="Reuters",
            reason="wire",
        ),
        CredibleArticle(
            url="https://bbc.com/news/1",
            title="BBC story 1",
            snippet="BBC snippet.",
            source="BBC",
            reason="broadcaster",
        ),
    ]
    summaries = type(DEFAULT_SUMMARIES)(
        articles=[
            *DEFAULT_SUMMARIES.articles,
            {
                "title": "Invented",
                "url": "https://invented.example.com/x",
                "source": "blog",
                "summary": "Should be dropped.",
                "key_topics": [],
            },
        ]
    )
    empty_summary = type(DEFAULT_SUMMARIES)(
        articles=[
            {
                "title": "Reuters story 0",
                "url": "https://reuters.com/news/0",
                "source": "Reuters",
                "summary": "",
                "key_topics": ["ai"],
            }
        ]
    )
    client = FakeMistralClient({type(summaries): summaries})
    monkeypatch.setattr(activities, "_mistral_client", lambda: client)
    request = SummaryRequest(topic="ai", queries=["ai news"], articles=articles_in)
    with workflows.run_activities_locally():
        digest = await activities.summarize_articles(request)
    assert digest.topic == "ai"
    assert digest.queries == ["ai news"]
    assert [a.url for a in digest.articles] == [
        "https://reuters.com/news/0",
        "https://bbc.com/news/1",
    ]
    assert digest.articles[0].summary == "Summary of the Reuters story."

    client_empty = FakeMistralClient({type(empty_summary): empty_summary})
    monkeypatch.setattr(activities, "_mistral_client", lambda: client_empty)
    with workflows.run_activities_locally():
        digest_fallback = await activities.summarize_articles(request)
    assert digest_fallback.articles[0].summary == "Reuters snippet fallback."


async def test_summarize_articles_empty_skips_llm(monkeypatch):
    monkeypatch.setattr(activities, "_mistral_client", lambda: ExplodingClient())
    with workflows.run_activities_locally():
        digest = await activities.summarize_articles(
            SummaryRequest(topic="ai", queries=["q"], articles=[])
        )
    assert digest.articles == []


def test_input_accepts_up_to_three_topics():
    assert NewsDigestInput(topics=[" ai ", "climate", "space"]).topics == ["ai", "climate", "space"]


def test_input_rejects_more_than_three_topics():
    with pytest.raises(ValidationError):
        NewsDigestInput(topics=["a", "b", "c", "d"])


def test_input_rejects_empty_topics():
    with pytest.raises(ValidationError):
        NewsDigestInput(topics=[])
    with pytest.raises(ValidationError):
        NewsDigestInput(topics=["  ", ""])


def test_validated_articles_keeps_candidate_snippets():
    results = make_search_results("reuters.com", 2)
    from worker.workflows.news.models import CredibleArticle, FilteredSources

    filtered = FilteredSources(
        articles=[
            CredibleArticle(
                url=results[0].url,
                title="LLM title",
                snippet="LLM snippet",
                source="",
                reason="r",
            )
        ]
    )
    articles = llm.validated_articles(filtered, results)
    assert len(articles) == 1
    assert articles[0].title == results[0].title
    assert articles[0].snippet == results[0].snippet
    assert articles[0].source == "reuters.com.example.com"
