# newsworkflow

An intelligent [Mistral Workflow](https://docs.mistral.ai/studio/workflows/overview) that finds
relevant news from trusted sources based on the user's interests.

The user chooses **up to three topics**. The `news-digest` workflow then:

1. **Query expansion** — an LLM (system prompt: recent/breaking news only, no year, 2026 or
   later) expands each topic into up to five precise search queries.
2. **Search relevant news** — a DuckDuckGo search per query returns the top 5 results with
   title, URL, and snippet (html endpoint with lite-endpoint fallback).
3. **Filter URLs** — an LLM analyzes the results per topic and returns only credible sources
   (established news platforms), ensuring diversity with at least two links per topic when
   available; each returned item keeps its URL and snippet. URLs are validated against the
   candidate list so nothing is hallucinated.
4. **Generate summaries** — an LLM infers the main topics and general coverage of each
   selected link and writes a concise, trustworthy summary with key topics.

All side effects (LLM calls, HTTP) live in activities; the workflow itself stays deterministic.

## Input / output

```json
{ "topics": ["artificial intelligence", "climate change"] }
```

Returns a `NewsDigest`: per topic, the expanded queries and a list of articles
(`title`, `url`, `source`, `summary`, `key_topics`).

## `news-search`

A minimal manual-trigger workflow: input `{"topic": "..."}` runs a web search for
recent news about the topic and returns the top 5 results, each with `title`,
`url`, and `snippet` (no LLM steps).

## Layout

- `apps/worker/src/worker/workflows/news/` — models, prompts, DuckDuckGo search, LLM helpers,
  activities, and the `news-digest` workflow
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

Run it on demand with input `{"topics": ["your", "topics", "here"]}` (at most three).
