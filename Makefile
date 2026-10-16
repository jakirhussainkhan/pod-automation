.PHONY: install install-dev run test lint fmt check

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt

run:
	python run.py

test:
	pytest

lint:
	ruff check app

fmt:
	ruff format app

check:
	python -m compileall -q app
	ruff check app
	@for f in app/static/js/*.js; do node --check "$$f" || exit 1; done
	pytest
