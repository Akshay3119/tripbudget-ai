.PHONY: setup migrate test run corpus
setup:
	uv sync --frozen
migrate:
	uv run python -m scripts.manage migrate
test:
	uv run ruff check src scripts evaluation tests
	uv run pytest -q
run:
	uv run uvicorn tripbudget.api:app --host 127.0.0.1 --port 8084 --no-access-log
corpus:
	uv run python -c 'from tripbudget.retrieval import Corpus; from tripbudget.settings import Settings; Corpus(Settings()).build()'
