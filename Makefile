PYTHON  ?= python3
VENV    := env
BIN     := $(VENV)/bin
PORT    ?= 7001

.PHONY: help venv install install-ingestion test test-py test-js lint serve clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

venv: ## Create a virtual environment
	$(PYTHON) -m venv $(VENV)

install: venv ## Install project dependencies
	$(BIN)/pip install -r requirements.txt

install-ingestion: install ## Install ingestion-specific dependencies
	$(BIN)/pip install -r ingestion/requirements.txt

test: test-py test-js ## Run all tests

test-py: ## Run Python tests
	$(BIN)/python -m pytest

test-js: ## Run client-side JS tests
	node --test tests/test_client.js

lint: ## Run ruff linter (if installed)
	$(BIN)/python -m ruff check .

serve: ## Start the dev server (PORT=7001, all interfaces)
	$(BIN)/uvicorn server:app --reload --host 0.0.0.0 --port $(PORT)

clean: ## Remove virtual env and caches
	rm -rf $(VENV) __pycache__ .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
