from pydantic import BaseModel, Field, field_validator, model_validator

MAX_TOPICS = 3
QUERIES_PER_TOPIC = 2
MAX_RESULTS_PER_QUERY = 5
MAX_CANDIDATES_PER_TOPIC = 10
MAX_ARTICLES_PER_TOPIC = 5

NO_CREDIBLE_RESULTS_NOTE = "no credible recent results"


class NewsDigestInput(BaseModel):
    topics: list[str] = Field(
        min_length=1,
        max_length=MAX_TOPICS,
        description=(
            "The user's interests: 1-3 comma-separated topics to search news for."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _split_comma_separated(cls, value):
        if isinstance(value, str):
            value = {"topics": [part for part in value.split(",")]}
        if isinstance(value, dict) and isinstance(value.get("topics"), str):
            value = {**value, "topics": value["topics"].split(",")}
        return value

    @field_validator("topics")
    @classmethod
    def _strip_and_drop_empty(cls, value: list[str]) -> list[str]:
        cleaned = [topic.strip() for topic in value if topic.strip()]
        if not cleaned:
            raise ValueError("at least one non-empty topic is required")
        return cleaned


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str


class TopicQueries(BaseModel):
    topic: str
    queries: list[str] = Field(min_length=1, max_length=QUERIES_PER_TOPIC)


class ExpandedQueries(BaseModel):
    topics: list[TopicQueries]


class QueryExpansion(BaseModel):
    generated_at: str
    topics: list[TopicQueries]


class SearchRequest(BaseModel):
    topic: str
    query: str
    max_results: int = MAX_RESULTS_PER_QUERY


class TopicSearchResults(BaseModel):
    topic: str
    query: str
    results: list[SearchResult]


class CredibleArticle(BaseModel):
    url: str
    title: str
    snippet: str
    source: str


class SummaryRequest(BaseModel):
    topic: str
    queries: list[str]
    articles: list[CredibleArticle]


class ArticleSummary(BaseModel):
    title: str
    url: str
    source: str
    summary: str
    key_topics: list[str] = Field(default_factory=list)


class ArticleSummaries(BaseModel):
    articles: list[ArticleSummary]


class TopicDigest(BaseModel):
    topic: str
    queries: list[str]
    articles: list[ArticleSummary]
    note: str | None = None


class NewsDigest(BaseModel):
    generated_at: str
    topics: list[TopicDigest]
    error: str | None = None
