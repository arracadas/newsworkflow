# newsworkflow

An intelligent [Mistral Workflow](https://docs.mistral.ai/studio/workflows/overview) that finds
relevant news from trusted sources based on the user's interests.

The user chooses **up to three topics** (a comma-separated string or a list). The `news-digest`
workflow then:

1. **Query expansion** — an LLM (system prompt: breaking news and recent developments from the
   last 7 days, no year in queries) expands each topic into exactly two precise search queries.
2. **Search relevant news** — a DuckDuckGo search per query returns the top 5 results with
   title, URL, and snippet (html endpoint with lite-endpoint fallback). If the search step
   fails, the workflow returns a clear error message instead of empty results.
3. **Credibility filter** — only results from established news outlets (reuters.com, apnews.com,
   bbc.com, ft.com, and outlets with comparable editorial standards) are kept; social media
   and aggregators are excluded. URLs are deduplicated. A topic without any credible result
   gets a `"no credible recent results"` note instead of articles.
4. **Generate summaries** — an LLM writes a neutral, factual 3-sentence summary of each kept
   article based only on its title and snippet.

All side effects (LLM calls, HTTP) live in activities; the workflow itself stays deterministic.

## Input / output

```json
{ "topics": "artificial intelligence, climate change" }
```

Returns a `NewsDigest`: per topic, the expanded queries, a list of articles
(`title`, `url`, `source`, `summary`, `key_topics`) from credible outlets, and a
`"no credible recent results"` note when a topic has no credible article. A
non-null `error` field carries a clear message when the search step fails.

## Layout

- `apps/worker/src/worker/workflows/news/` — models, prompts, DuckDuckGo search, credibility
  filter, LLM helpers, activities, and the `news-digest` workflow
- `apps/worker/src/worker/entrypoints/worker.py` — worker entrypoint (discovers and serves workflows)
- `Dockerfile` — image built by the managed deployment; `CMD` starts the worker
- `tests/` — unit tests with mocked LLM/HTTP effects plus an end-to-end test on a Temporal
  time-skipping test server (`create_test_worker` + `temporal_env`)

## Local development

```bash
uv sync
uv run pytest
```

Local worker runs need `MISTRAL_API_KEY` in the environment (see `.env.example`); the managed
deployment on Mistral Cloud authenticates with an injected service-account token instead.

## Deployment

Managed deployment from this repository (build directory = repo root, `Dockerfile` at the root):

```
deployment_name = newsworkflow
github_url      = https://github.com/arracadas/newsworkflow
revision        = <pushed commit SHA>
dockerfile_path = Dockerfile
```

Prerequisites: the [Mistral GitHub App](https://github.com/apps/mistralai) installed on this
repository, and pay-as-you-go billing enabled on the Mistral organization.

Run it on demand with input `{"topics": "your, topics, here"}` (at most three).
