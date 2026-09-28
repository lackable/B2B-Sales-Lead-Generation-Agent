# B2B Sales Lead Generation — common tasks
# Windows users can keep using start_backend.bat / start_frontend.bat instead.

PY ?= python
VENV ?= .venv
VENV_PY := $(VENV)/Scripts/python.exe

ifeq ($(OS),Windows_NT)
	PY_RUN := $(VENV_PY)
else
	PY_RUN := $(VENV)/bin/python
endif

.PHONY: help install dev-api dev-web test lint format clean

help:
	@echo "install   - editable install with dev extras into $(VENV)"
	@echo "dev-api   - run the FastAPI orchestrator on http://localhost:8000"
	@echo "dev-web   - run the Vite dev server on http://localhost:5173"
	@echo "test      - run the pytest suite"
	@echo "lint      - ruff check"
	@echo "format    - ruff check --fix"

install:
	$(PY) -m pip install -e ".[dev]"

dev-api:
	$(PY_RUN) -m uvicorn leadgen.api.app:app --host 0.0.0.0 --port 8000 --reload

dev-web:
	cd frontend && npm run dev

test:
	$(PY_RUN) -m pytest

lint:
	$(PY_RUN) -m ruff check .

format:
	$(PY_RUN) -m ruff check --fix .

clean:
	$(PY_RUN) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]"
