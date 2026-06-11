PYTHON  ?= python3
VENV    := .venv
BIN     := $(VENV)/bin
PORT    ?= 7001

.PHONY: help venv install install-ingestion test test-py test-js lint audit check-cdn ci serve clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

venv: ## Create a virtual environment
	$(PYTHON) -m venv $(VENV)

install: venv ## Install project dependencies
	$(BIN)/pip install -r requirements.txt
	npm ci

install-ingestion: install ## Install ingestion-specific dependencies
	$(BIN)/pip install -r ingestion/requirements.txt

test: test-py test-js ## Run all tests

test-py: ## Run Python tests
	$(BIN)/python -m pytest

test-js: ## Run client-side JS tests
	npx vitest run

audit: ## Scan dependencies for known vulnerabilities
	$(BIN)/pip-audit -r requirements.txt
	npm audit --omit=dev --audit-level=high

check-cdn: ## Verify PDF.js CDN URLs in app/index.html are reachable
	@grep -oE 'https://cdn\.jsdelivr\.net/npm/pdfjs-dist@[a-zA-Z0-9./_-]+' app/index.html | sort -u | while read url; do \
		printf "  %s ... " "$$url"; \
		curl -fsI "$$url" > /dev/null && echo "ok" || { echo "FAILED"; exit 1; }; \
	done

ci: test lint audit check-cdn ## Run tests, lint, security audit, and CDN URL liveness check

lint: ## Run ruff lint + format check
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

serve: ## Start the dev server (PORT=7001, all interfaces)
	$(BIN)/uvicorn server:app --reload --host 0.0.0.0 --port $(PORT)

clean: ## Remove virtual env and caches
	rm -rf $(VENV) __pycache__ .pytest_cache .ruff_cache .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
