FROM python:3.12.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy \
    TRIPBUDGET_DATA_DIR=/app/data TRIPBUDGET_EMBEDDING_CACHE=/app/embeddings
WORKDIR /app
RUN pip install --no-cache-dir uv==0.9.13
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev
COPY static ./static
COPY corpus ./corpus
COPY scripts ./scripts
# Derived public index only. No live source promotion, user data, credentials, or local LLM weights.
RUN .venv/bin/python -c "from tripbudget.retrieval import Corpus; from tripbudget.settings import Settings; Corpus(Settings()).build()"
RUN useradd --uid 10001 --create-home app && chown -R app:app /app
USER app
ENV PATH=/app/.venv/bin:$PATH
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn tripbudget.api:app --host 0.0.0.0 --port ${PORT:-8080} --no-access-log --limit-concurrency 24"]
