from worker.workflows.news.models import (
    MAX_ARTICLES_PER_TOPIC,
    MAX_QUERIES_PER_TOPIC,
    FilterRequest,
    SummaryRequest,
)

QUERY_EXPANSION_SYSTEM_PROMPT = (
    "You are an expert news analyst specializing in crafting precise search queries "
    "to retrieve the most recent, up-to-date information. Focus only on breaking news, "
    "trending topics, or recent developments without specifying any year. "
    "Only include news from 2026 or later"
)

TRUSTED_NEWS_SOURCES = [
    "reuters.com",
    "apnews.com",
    "bbc.com",
    "bbc.co.uk",
    "npr.org",
    "theguardian.com",
    "nytimes.com",
    "washingtonpost.com",
    "bloomberg.com",
    "ft.com",
    "wsj.com",
    "cnbc.com",
    "aljazeera.com",
    "france24.com",
    "dw.com",
    "euronews.com",
    "techcrunch.com",
    "arstechnica.com",
    "wired.com",
    "theverge.com",
    "mit.edu",
    "nature.com",
    "science.org",
    "sciencedaily.com",
    "ieee.org",
    "who.int",
    "un.org",
    "nasa.gov",
    "esa.int",
    "cdc.gov",
    "europa.eu",
]


def query_expansion_user_prompt(topics: list[str]) -> str:
    listing = "\n".join(f"- {topic}" for topic in topics)
    return (
        f"The user is interested in these topics:\n{listing}\n\n"
        f"For each topic, craft up to {MAX_QUERIES_PER_TOPIC} precise DuckDuckGo search queries "
        "that retrieve the most recent breaking news, trending coverage, and recent developments "
        "about that topic. Do not include any year in the queries. "
        "Return one entry per topic, in the same order, each with its list of queries."
    )


def filter_sources_user_prompt(request: FilterRequest) -> str:
    listing = "\n".join(
        f"- title: {r.title}\n  url: {r.url}\n  snippet: {r.snippet}" for r in request.results
    )
    trusted = ", ".join(TRUSTED_NEWS_SOURCES)
    return (
        f"Topic: {request.topic}\n\n"
        f"Candidate news results from DuckDuckGo:\n{listing}\n\n"
        "Analyze this list and return ONLY credible sources. Prefer established news platforms "
        f"such as: {trusted}. Drop personal blogs, press-release-only aggregators, forums, "
        "social media posts, and any source whose credibility you cannot confirm. "
        f"Ensure diversity: include at least two links for the topic if that many credible "
        f"results are available, and never more than {MAX_ARTICLES_PER_TOPIC}. "
        "Each returned item must include the url and its snippet, copied from the list above. "
        "Only use urls that appear in the provided list, unchanged."
    )


def summarize_user_prompt(request: SummaryRequest) -> str:
    listing = "\n".join(
        f"- title: {a.title}\n  url: {a.url}\n  source: {a.source}\n  snippet: {a.snippet}"
        for a in request.articles
    )
    queries = ", ".join(request.queries)
    return (
        f"Topic: {request.topic}\nSearch queries used: {queries}\n\n"
        f"News sources to summarize:\n{listing}\n\n"
        "For each source above, infer its main topics and general coverage and write a concise, "
        "trustworthy summary (2-3 sentences) plus up to 5 key topics. "
        "Return one summary per source, using the exact urls from the list above, unchanged."
    )


FILTER_SOURCES_SYSTEM_PROMPT = (
    "You are a news credibility analyst. You evaluate search results and keep only sources "
    "from trusted platforms, minimizing misinformation. You never invent urls: every url you "
    "return must come from the provided candidate list."
)

SUMMARIZE_SYSTEM_PROMPT = (
    "You are a news summarizer. Given news source urls with their snippets, you infer the main "
    "topics and general coverage of each link and produce concise, high-level, trustworthy "
    "summaries. You never invent urls: every url you return must come from the provided list."
)
