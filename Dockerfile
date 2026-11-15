FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# `uv sync` installs into /app/.venv; put it on PATH so the plain `python` CMD
# below resolves to the venv interpreter that has mistralai-workflows installed.
ENV PATH="/app/.venv/bin:${PATH}"

COPY apps/worker/src/worker ./worker

ENV PYTHONPATH=/app

CMD ["python", "-m", "worker.entrypoints.worker"]
