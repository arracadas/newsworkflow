from worker.workflows.news.bing import parse_rss_results

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>AI news story</title>
    <link>https://www.bing.com/ck/a?u=a1aHR0cHM6Ly9leGFtcGxlLmNvbS9uZXdzLzE</link>
    <description>Snippet about AI news.</description>
  </item>
  <item>
    <title>Direct link story</title>
    <link>https://example.org/news/2</link>
    <description>Snippet two.</description>
  </item>
  <item>
    <title>Duplicate of first</title>
    <link>https://example.com/news/1</link>
    <description>Duplicate snippet.</description>
  </item>
</channel></rss>
"""


def test_parse_rss_results_unwraps_bing_redirects_and_dedupes():
    results = parse_rss_results(RSS, max_results=5)
    assert [r.url for r in results] == [
        "https://example.com/news/1",
        "https://example.org/news/2",
    ]
    assert results[0].title == "AI news story"
    assert results[0].snippet == "Snippet about AI news."


def test_parse_rss_results_respects_max_results():
    results = parse_rss_results(RSS, max_results=1)
    assert len(results) == 1


def test_parse_rss_results_invalid_xml_returns_empty():
    assert parse_rss_results("<not-rss", max_results=5) == []
