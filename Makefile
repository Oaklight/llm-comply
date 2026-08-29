.PHONY: all lint lint-fix test build push clean build-docker push-docker deploy-dev build-binary build-binary-musl build-docker-alpine build-docker-glibc clean-binary clean-binary-all help

DOCKER_IMAGE ?= oaklight/llm-comply
VERSION := $(shell python -c 'import re; print(re.search(r"__version__ = \"([^\"]+)\"", open("src/llm_comply/__init__.py").read()).group(1))')
VERSION_FILE := src/llm_comply/__init__.py

V ?= $(VERSION)
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

# ── Nuitka Binary Builds ──────────────────────────────────────

UNAME_S := $(shell uname -s 2>/dev/null || echo Windows)
UNAME_M := $(shell uname -m 2>/dev/null || echo x86_64)
ifeq ($(UNAME_S),Linux)
  BINARY_OS := linux
else ifeq ($(UNAME_S),Darwin)
  BINARY_OS := macos
else
  BINARY_OS := windows
endif
ifeq ($(UNAME_M),aarch64)
  BINARY_ARCH := arm64
else ifeq ($(UNAME_M),arm64)
  BINARY_ARCH := arm64
else
  BINARY_ARCH := x86_64
endif

BINARY_NAME = llm-comply-$(VERSION)-$(BINARY_OS)-$(BINARY_ARCH)
BINARY_NAME_MUSL = llm-comply-$(VERSION)-linux-$(BINARY_ARCH)-musl
BINARY_DIR := build
NUITKA_ENTRY := _nuitka_entry.py
NUITKA_JOBS := $(shell nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 2)

NUITKA_FLAGS = \
	--standalone \
	--onefile \
	--static-libpython=no \
	--jobs=$(NUITKA_JOBS) \
	--output-dir=$(BINARY_DIR) \
	--include-package=llm_comply \
	--include-data-files=src/llm_comply/web.html=llm_comply/web.html \
	--include-data-dir=src/llm_comply/specs=llm_comply/specs \
	--nofollow-import-to=pytest \
	--nofollow-import-to=setuptools \
	--nofollow-import-to=pip \
	--nofollow-import-to=_pytest \
	--assume-yes-for-downloads

build-binary:
	@echo "Building native binary: $(BINARY_NAME)..."
	@printf 'from llm_comply.cli import main\nmain()\n' > $(NUITKA_ENTRY)
	python -m nuitka $(NUITKA_FLAGS) \
		--output-filename=$(BINARY_NAME)$(if $(filter windows,$(BINARY_OS)),.exe,) \
		$(NUITKA_ENTRY); \
	ret=$$?; rm -f $(NUITKA_ENTRY); exit $$ret
	@ls -lh $(BINARY_DIR)/$(BINARY_NAME)*
	@echo "Binary build complete."

build-binary-musl:
	@echo "Building musl binary: $(BINARY_NAME_MUSL)..."
	@mkdir -p $(BINARY_DIR)
	docker run --rm \
		-v $(CURDIR):/workspace:ro \
		-v $(CURDIR)/$(BINARY_DIR):/output \
		$(REGISTRY_MIRROR:%=%/)python:3.12-alpine \
		/bin/sh -c '\
			mkdir -p /tmp/build && tar -cf - -C /workspace --exclude=.git --exclude=__pycache__ . | tar -xf - -C /tmp/build && cd /tmp/build && \
			apk add --no-cache gcc musl-dev python3-dev git >/dev/null && \
			pip install --break-system-packages patchelf -q && \
			pip install --break-system-packages -e . -q && \
			pip install --break-system-packages "nuitka[onefile]" ordered-set -q && \
			printf "from llm_comply.cli import main\nmain()\n" > /tmp/_entry.py && \
			python -m nuitka \
				--standalone --onefile \
				--jobs=$$(nproc) \
				--output-dir=/output \
				--output-filename=$(BINARY_NAME_MUSL) \
				--include-package=llm_comply \
				--include-data-files=src/llm_comply/web.html=llm_comply/web.html \
				--include-data-dir=src/llm_comply/specs=llm_comply/specs \
				--nofollow-import-to=pytest \
				--nofollow-import-to=setuptools \
				--nofollow-import-to=pip \
				--nofollow-import-to=_pytest \
				--assume-yes-for-downloads \
				/tmp/_entry.py && \
			rm -rf /output/_entry.* '
	@ls -lh $(BINARY_DIR)/$(BINARY_NAME_MUSL)
	@echo "Musl binary build complete."

clean-binary:
	@echo "Cleaning binary build artifacts..."
	rm -rf $(BINARY_DIR)/_nuitka_entry.* $(BINARY_DIR)/_entry.* $(NUITKA_ENTRY)
	@echo "Clean complete. Binaries in $(BINARY_DIR)/ preserved."

clean-binary-all:
	@echo "Cleaning all binary artifacts..."
	rm -rf $(BINARY_DIR)
	rm -f $(NUITKA_ENTRY)
	@echo "Clean complete."

# ── Docker ────────────────────────────────────────────────────

build-docker:
	docker build $(BUILD_ARGS) -t $(DOCKER_IMAGE):$(VERSION) -t $(DOCKER_IMAGE):latest .

push-docker: build-docker
	docker push $(DOCKER_IMAGE):$(VERSION)
	docker push $(DOCKER_IMAGE):latest

build-docker-alpine:
	@BINARY=$(BINARY_DIR)/$(BINARY_NAME_MUSL); \
	if [ ! -f "$$BINARY" ]; then \
		echo "::error::Musl binary not found: $$BINARY"; \
		echo "Run 'make build-binary-musl' first."; \
		exit 1; \
	fi; \
	echo "Building Alpine Docker image $(DOCKER_IMAGE):$(V)-alpine..."; \
	docker build -f docker/Dockerfile.binary \
		--build-arg BASE_IMAGE=$(REGISTRY_MIRROR:%=%/)alpine \
		--build-arg BINARY=$$BINARY \
		-t $(DOCKER_IMAGE):$(V)-alpine \
		-t $(DOCKER_IMAGE):$(V) \
		-t $(DOCKER_IMAGE):latest .
	@echo "Alpine Docker image built successfully."

build-docker-glibc:
	@BINARY=$(BINARY_DIR)/$(BINARY_NAME); \
	if [ ! -f "$$BINARY" ]; then \
		echo "::error::Native binary not found: $$BINARY"; \
		echo "Run 'make build-binary' first."; \
		exit 1; \
	fi; \
	echo "Building glibc Docker image $(DOCKER_IMAGE):$(V)-glibc..."; \
	docker build -f docker/Dockerfile.binary \
		--build-arg BASE_IMAGE=$(REGISTRY_MIRROR:%=%/)busybox:glibc \
		--build-arg BINARY=$$BINARY \
		-t $(DOCKER_IMAGE):$(V)-glibc .
	@echo "Glibc Docker image built successfully."

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
	@echo "Binary:"
	@echo "  build-binary       - Build native Nuitka binary"
	@echo "  build-binary-musl  - Build musl binary via Alpine container"
	@echo "  clean-binary       - Clean build artifacts (keep binaries)"
	@echo "  clean-binary-all   - Clean all binary artifacts"
	@echo ""
	@echo "Docker:"
	@echo "  build-docker       - Build Python-based Docker image"
	@echo "  push-docker        - Push to Docker Hub"
	@echo "  build-docker-alpine - Build Alpine image from musl binary"
	@echo "  build-docker-glibc  - Build glibc image from native binary"
	@echo "  deploy-dev         - Build dev wheel+image, deploy to remote host"
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
