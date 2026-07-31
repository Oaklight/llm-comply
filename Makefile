.PHONY: all lint lint-fix test build push clean help

all: lint test

lint:
	ruff check src/
	ruff format --check src/

lint-fix:
	ruff check --fix src/
	ruff format src/

test:
	llm-comply --list
	llm-comply --format openai-chat --list
	llm-comply --format anthropic --list
	llm-comply --format google-genai --list

build:
	python -m build

push: build
	twine upload dist/*

clean:
	rm -rf dist/ build/ *.egg-info src/*.egg-info

help:
	@echo "Available targets:"
	@echo "  lint       - Run ruff check + format check"
	@echo "  lint-fix   - Auto-fix lint errors and format"
	@echo "  test       - Smoke test (list all formats)"
	@echo "  build      - Build wheel and sdist"
	@echo "  push       - Upload to PyPI"
	@echo "  clean      - Remove build artifacts"
