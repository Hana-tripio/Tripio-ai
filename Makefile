.PHONY: install dev test lint schemas check

install:
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev]"

dev:
	.venv/bin/uvicorn app.main:app --reload --port 8000

test:
	.venv/bin/pytest -v

lint:
	.venv/bin/ruff check .

schemas:
	.venv/bin/python scripts/export_schemas.py

check: lint test
