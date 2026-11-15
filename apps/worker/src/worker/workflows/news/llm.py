from worker.workflows.news.models import (
    ArticleSummaries,
    ExpandedQueries,
    SummaryRequest,
)
from worker.workflows.news.prompts import (
    QUERY_EXPANSION_SYSTEM_PROMPT,
    SUMMARIZE_SYSTEM_PROMPT,
    query_expansion_user_prompt,
    summarize_user_prompt,
)

EXPANSION_MODEL = "mistral-medium-latest"
SUMMARY_MODEL = "mistral-large-latest"


def _parsed(response, model: type) -> object:
    choice = response.choices[0] if response.choices else None
    parsed = choice.message.parsed if choice is not None and choice.message is not None else None
    if parsed is None:
        raise ValueError(f"LLM returned no parsed {model.__name__}")
    return parsed


async def expand_queries(client, topics: list[str]) -> ExpandedQueries:
    response = await client.chat.parse_async(
        model=EXPANSION_MODEL,
        messages=[
            {"role": "system", "content": QUERY_EXPANSION_SYSTEM_PROMPT},
            {"role": "user", "content": query_expansion_user_prompt(topics)},
        ],
        response_format=ExpandedQueries,
    )
    return _parsed(response, ExpandedQueries)


async def summarize_articles(client, request: SummaryRequest) -> ArticleSummaries:
    response = await client.chat.parse_async(
        model=SUMMARY_MODEL,
        messages=[
            {"role": "system", "content": SUMMARIZE_SYSTEM_PROMPT},
            {"role": "user", "content": summarize_user_prompt(request)},
        ],
        response_format=ArticleSummaries,
    )
    return _parsed(response, ArticleSummaries)
