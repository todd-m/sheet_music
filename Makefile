PYTHON  ?= python3
VENV    := .venv
BIN     := $(VENV)/bin
PORT    ?= 8000

.PHONY: help venv install install-ingestion test lint serve clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

venv: ## Create a virtual environment
	$(PYTHON) -m venv $(VENV)

install: venv ## Install project dependencies
	$(BIN)/pip install -r requirements.txt

install-ingestion: install ## Install ingestion-specific dependencies
	$(BIN)/pip install -r ingestion/requirements.txt

test: ## Run the test suite
	$(BIN)/python -m pytest

lint: ## Run ruff linter (if installed)
	$(BIN)/python -m ruff check .

serve: ## Start the dev server (PORT=8000)
	$(BIN)/uvicorn server:app --reload --port $(PORT)

clean: ## Remove virtual env and caches
	rm -rf $(VENV) __pycache__ .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
