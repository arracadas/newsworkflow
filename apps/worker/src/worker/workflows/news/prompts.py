from worker.workflows.news.models import (
    QUERIES_PER_TOPIC,
    SummaryRequest,
)

QUERY_EXPANSION_SYSTEM_PROMPT = (
    "You are an expert news analyst specializing in crafting precise search queries "
    "to retrieve the most recent, up-to-date information. Focus only on breaking news, "
    "trending topics, or developments from the last 7 days. Do not specify any year "
    "in the queries."
)


def query_expansion_user_prompt(topics: list[str]) -> str:
    listing = "\n".join(f"- {topic}" for topic in topics)
    return (
        f"The user is interested in these topics:\n{listing}\n\n"
        f"For each topic, craft exactly {QUERIES_PER_TOPIC} precise DuckDuckGo search queries "
        "focused on breaking news and recent developments from the last 7 days about that "
        "topic. Do not include any year in the queries. "
        "Return one entry per topic, in the same order, each with its list of queries."
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
        "For each source above, write a neutral, factual summary of exactly 3 sentences "
        "based only on its title and snippet. Do not add information that is not in the "
        "title or snippet, and keep an unbiased tone. "
        "Return one summary per source, using the exact urls from the list above, unchanged."
    )


SUMMARIZE_SYSTEM_PROMPT = (
    "You are a news summarizer. Given news source urls with their titles and snippets, "
    "you produce neutral, factual summaries of exactly 3 sentences based only on the "
    "provided title and snippet. You never invent urls: every url you return must come "
    "from the provided list."
)
