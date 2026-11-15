import pytest
from pydantic import ValidationError

import mistralai.workflows as workflows
from worker.workflows.news import activities
from worker.workflows.news.credibility import (
    article_source,
    filter_credible_results,
    is_credible_source,
)
from worker.workflows.news.duckduckgo import (
    SearchUnavailableError,
    parse_search_results,
    search_duckduckgo,
)
from worker.workflows.news.models import (
    MAX_ARTICLES_PER_TOPIC,
    NewsDigestInput,
    SearchRequest,
    SummaryRequest,
    CredibleArticle,
)

from fakes import (
    DEFAULT_EXPANSION,
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


async def test_search_duckduckgo_raises_clear_error_when_all_endpoints_fail(monkeypatch):
    import httpx

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    with pytest.raises(SearchUnavailableError) as excinfo:
        await search_duckduckgo("test query")
    assert "Web search failed" in str(excinfo.value)
    assert "test query" in str(excinfo.value)


async def test_search_duckduckgo_empty_page_is_not_an_error(monkeypatch):
    class FakeResponse:
        status_code = 200
        text = "<html><body>no results</body></html>"

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    assert await search_duckduckgo("test query") == []


async def test_expand_search_queries_activity(monkeypatch):
    client = FakeMistralClient({type(DEFAULT_EXPANSION): DEFAULT_EXPANSION})
    monkeypatch.setattr(activities, "_mistral_client", lambda: client)
    with workflows.run_activities_locally():
        expansion = await activities.expand_search_queries(["ai", "climate"])
    assert expansion.generated_at.endswith("+00:00")
    assert [t.topic for t in expansion.topics] == ["ai", "climate"]
    call = client.chat.calls[0]
    assert "last 7 days" in call["messages"][0]["content"]
    assert "exactly 2" in call["messages"][1]["content"]
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
    assert all(r.url.startswith("https://") for r in result.results)


def test_is_credible_source_accepts_trusted_outlets():
    for url in [
        "https://www.reuters.com/world/story",
        "https://apnews.com/article",
        "https://www.bbc.com/news/story",
        "https://www.ft.com/content",
        "https://subdomain.theguardian.com/x",
    ]:
        assert is_credible_source(url), url


def test_is_credible_source_rejects_social_media_and_aggregators():
    for url in [
        "https://twitter.com/user/status/1",
        "https://x.com/user/status/1",
        "https://reddit.com/r/news",
        "https://news.google.com/read/x",
        "https://facebook.com/page",
        "https://randomblog.example.com/post",
        "https://reuters.com.fake.example.com/post",
        "",
    ]:
        assert not is_credible_source(url), url


def test_filter_credible_results_dedupes_and_keeps_snippets():
    from worker.workflows.news.models import SearchResult

    candidates = [
        {
            "title": "Reuters story",
            "url": "https://www.reuters.com/news/0",
            "snippet": "Reuters snippet.",
        },
        {
            "title": "Blog story",
            "url": "https://blog.example.com/post",
            "snippet": "Blog snippet.",
        },
        {
            "title": "Reuters duplicate",
            "url": "https://www.reuters.com/news/0",
            "snippet": "Duplicate snippet.",
        },
        {
            "title": "BBC story",
            "url": "https://www.bbc.com/news/1",
            "snippet": "BBC snippet.",
        },
    ]
    articles = filter_credible_results([SearchResult(**c) for c in candidates])
    assert [a.url for a in articles] == [
        "https://www.reuters.com/news/0",
        "https://www.bbc.com/news/1",
    ]
    assert articles[0].title == "Reuters story"
    assert articles[0].snippet == "Reuters snippet."
    assert articles[0].source == "reuters.com"
    assert all(isinstance(a, CredibleArticle) for a in articles)


def test_filter_credible_results_caps_articles_per_topic():
    many = [
        {
            "title": f"Reuters story {i}",
            "url": f"https://www.reuters.com/news/{i}",
            "snippet": f"Snippet {i}.",
        }
        for i in range(MAX_ARTICLES_PER_TOPIC + 3)
    ]
    from worker.workflows.news.models import SearchResult

    articles = filter_credible_results([SearchResult(**m) for m in many])
    assert len(articles) == MAX_ARTICLES_PER_TOPIC


def test_article_source_strips_www():
    assert article_source("https://www.reuters.com/a") == "reuters.com"


async def test_summarize_articles_matches_by_url_and_falls_back_to_snippet(monkeypatch):
    articles_in = [
        CredibleArticle(
            url="https://reuters.com/news/0",
            title="Reuters story 0",
            snippet="Reuters snippet fallback.",
            source="Reuters",
        ),
        CredibleArticle(
            url="https://bbc.com/news/1",
            title="BBC story 1",
            snippet="BBC snippet.",
            source="BBC",
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
    summarize_call = next(c for c in client.chat.calls if "3 sentences" in c["messages"][1]["content"])
    assert summarize_call["messages"][0]["content"].startswith("You are a news summarizer.")

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


def test_input_accepts_comma_separated_string():
    parsed = NewsDigestInput(topics=" ai , climate ,space")
    assert parsed.topics == ["ai", "climate", "space"]


def test_input_accepts_up_to_three_topics():
    assert NewsDigestInput(topics=[" ai ", "climate", "space"]).topics == ["ai", "climate", "space"]


def test_input_rejects_more_than_three_topics():
    with pytest.raises(ValidationError):
        NewsDigestInput(topics="a, b, c, d")


def test_input_rejects_empty_topics():
    with pytest.raises(ValidationError):
        NewsDigestInput(topics=[])
    with pytest.raises(ValidationError):
        NewsDigestInput(topics="  , ")
