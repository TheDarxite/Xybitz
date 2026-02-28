VENV_PYTHON := .venv/bin/python
ifeq ($(OS),Windows_NT)
    VENV_PYTHON := .venv/Scripts/python.exe
endif

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	$(VENV_PYTHON) -m pytest tests/ -v --asyncio-mode=auto

test-cov:
	$(VENV_PYTHON) -m pytest tests/ --cov=app --cov-report=html

lint:
	$(VENV_PYTHON) -m ruff check app/ tests/

format:
	$(VENV_PYTHON) -m ruff format app/ tests/

db-reset:
	rm -f data/xybitz.db data/xybitz.db-wal data/xybitz.db-shm

setup:
	python setup.py

install:
	$(VENV_PYTHON) -m pip install -r requirements.txt

.PHONY: dev test test-cov lint format db-reset setup install
