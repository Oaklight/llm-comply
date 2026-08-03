.PHONY: all lint lint-fix test build push clean build-docker push-docker deploy-dev help

DOCKER_IMAGE ?= oaklight/llm-comply
VERSION := $(shell python -c 'import re; print(re.search(r"__version__ = \"([^\"]+)\"", open("src/llm_comply/__init__.py").read()).group(1))')
VERSION_FILE := src/llm_comply/__init__.py

REGISTRY_MIRROR ?= docker.io
PYPI_MIRROR ?=

SSH_TARGET ?=
REMOTE_STACK ?= /dockervol/dockge/stacks/llm-comply
REMOTE_CONTAINER ?= llm-comply

BUILD_ARGS =
ifneq ($(PYPI_MIRROR),)
BUILD_ARGS += --build-arg PYPI_MIRROR=$(PYPI_MIRROR)
endif

all: lint test

# ── Development ───────────────────────────────────────────────

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

# ── Package ───────────────────────────────────────────────────

build:
	python -m build

push: build
	twine upload dist/*

clean:
	rm -rf dist/ build/ *.egg-info src/*.egg-info

# ── Docker ────────────────────────────────────────────────────

build-docker:
	docker build $(BUILD_ARGS) -t $(DOCKER_IMAGE):$(VERSION) -t $(DOCKER_IMAGE):latest .

push-docker: build-docker
	docker push $(DOCKER_IMAGE):$(VERSION)
	docker push $(DOCKER_IMAGE):latest

# ── Dev Deploy ────────────────────────────────────────────────

deploy-dev:
ifndef SSH_TARGET
	$(error SSH_TARGET is required. Usage: make deploy-dev SSH_TARGET=cloud.kor2)
endif
	@set -e; \
	COMMIT=$$(git rev-parse --short HEAD); \
	ORIG_VER=$$(python -c 'import re; print(re.search(r"__version__ = \"([^\"]+)\"", open("$(VERSION_FILE)").read()).group(1))'); \
	DEV_VER="$$ORIG_VER.dev0+g$$COMMIT"; \
	echo "==> Building dev wheel $$DEV_VER..."; \
	python -c 'from pathlib import Path; p=Path("$(VERSION_FILE)"); s=p.read_text(); p.write_text(s.replace("__version__ = \"'"$$ORIG_VER"'\"", "__version__ = \"'"$$DEV_VER"'\""))'; \
	rm -rf dist build; \
	python -m build --wheel -q; \
	python -c 'from pathlib import Path; p=Path("$(VERSION_FILE)"); s=p.read_text(); p.write_text(s.replace("__version__ = \"'"$$DEV_VER"'\"", "__version__ = \"'"$$ORIG_VER"'\""))'; \
	WHEEL=$$(ls dist/*.whl | head -1 | xargs basename); \
	echo ""; \
	echo "Successfully built $$WHEEL"; \
	echo ""; \
	echo "==> Building Docker image from $$WHEEL..."; \
	docker build $(BUILD_ARGS) -t $(DOCKER_IMAGE):dev-test -q .; \
	echo "==> Deploying to $(SSH_TARGET) via zstd..."; \
	docker save $(DOCKER_IMAGE):dev-test | zstd -3 | ssh $(SSH_TARGET) \
		'zstd -d | docker load && \
		 docker tag $(DOCKER_IMAGE):dev-test $(DOCKER_IMAGE):latest && \
		 cd $(REMOTE_STACK) && \
		 docker compose up -d --force-recreate && \
		 sleep 3 && \
		 curl -sS http://127.0.0.1:8090/ | head -c 100 && echo && \
		 docker exec $(REMOTE_CONTAINER) llm-comply --version'; \
	echo "==> Dev deploy complete."

# ── Help ──────────────────────────────────────────────────────

help:
	@echo "Available targets:"
	@echo ""
	@echo "Development:"
	@echo "  lint           - Run ruff linter and format check"
	@echo "  lint-fix       - Auto-fix lint and formatting issues"
	@echo "  test           - Smoke test (list all formats)"
	@echo ""
	@echo "Package:"
	@echo "  build          - Build wheel and sdist"
	@echo "  push           - Upload to PyPI"
	@echo "  clean          - Remove build artifacts"
	@echo ""
	@echo "Docker:"
	@echo "  build-docker   - Build Docker image"
	@echo "  push-docker    - Push to Docker Hub"
	@echo "  deploy-dev     - Build dev wheel+image, deploy to remote host"
	@echo ""
	@echo "Variables:"
	@echo "  SSH_TARGET=<host>        - SSH target for deploy-dev (required)"
	@echo "  REMOTE_STACK=<path>      - Remote compose stack (default: $(REMOTE_STACK))"
	@echo "  PYPI_MIRROR=<url>        - PyPI mirror URL"
	@echo "  REGISTRY_MIRROR=<host>   - Docker registry mirror"
	@echo ""
	@echo "Usage examples:"
	@echo "  make deploy-dev SSH_TARGET=cloud.kor2"
	@echo ""
	@echo "Detected version: $(VERSION)"
