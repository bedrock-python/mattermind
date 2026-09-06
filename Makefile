.PHONY: install fmt check test test-all test-unit test-integration build docs-serve docs-build clean

install:
	uv sync --extra dev

fmt:
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

check:
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/
	uv run mypy src/

test-unit:
	uv run pytest -m unit

test-integration:
	uv run pytest -m integration

test:
	uv run pytest -m unit --cov=src/mattermind --cov-report=term --cov-fail-under=80 --cov-report=xml:coverage.xml

test-all:
	uv run pytest

build:
	uv build

docs-serve:
	python -c "import shutil; shutil.copy('CHANGELOG.md', 'docs/changelog.md')"
	uv run --no-dev --extra docs zensical serve

docs-build:
	python -c "import shutil; shutil.copy('CHANGELOG.md', 'docs/changelog.md')"
	uv run --no-dev --extra docs zensical build --clean

clean:
	python -c "import shutil, os, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in ['.pytest_cache', '.mypy_cache', '.ruff_cache', 'dist', 'build', 'site'] if os.path.exists(p)]; [os.remove(p) for p in ['.coverage', 'coverage.xml'] if os.path.exists(p)]; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]"
