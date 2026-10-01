PY := .venv/bin/python
PIP := .venv/bin/pip
export PATH := /opt/homebrew/opt/postgresql@16/bin:/opt/homebrew/bin:$(PATH)

.PHONY: venv db migrate api worker test smoke clean

venv:
	/opt/homebrew/bin/python3.12 -m venv .venv
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -e '.[dev]'

db:
	brew services start postgresql@16
	@until pg_isready -q; do sleep 1; done
	@createdb siteimg 2>/dev/null || true
	@echo "postgres ready"

migrate:
	$(PY) -c "from app.db import migrate; print('applied:', migrate())"

api:
	.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

worker:
	$(PY) worker/run.py

test:
	$(PY) -m pytest

smoke:
	$(PY) -m pytest tests/test_e2e.py -v

clean:
	rm -rf .venv var __pycache__ .pytest_cache
