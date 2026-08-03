FROM python:3.12-slim AS builder

ARG PYPI_MIRROR

WORKDIR /build

RUN mkdir -p /tmp/dist/
COPY dist/ /tmp/dist/

RUN set -e; \
    WHEEL=$(ls /tmp/dist/*.whl 2>/dev/null | head -1); \
    if [ -n "$WHEEL" ]; then \
        pip install --no-cache-dir --prefix=/install "$WHEEL"; \
    else \
        if [ -n "$PYPI_MIRROR" ]; then \
            pip install --no-cache-dir --prefix=/install -i "$PYPI_MIRROR" llm-comply; \
        else \
            pip install --no-cache-dir --prefix=/install llm-comply; \
        fi; \
    fi

FROM python:3.12-slim

COPY --from=builder /install /usr/local

RUN groupadd -r comply && useradd -r -g comply -s /usr/sbin/nologin comply

USER comply
WORKDIR /home/comply

EXPOSE 7860

CMD ["llm-comply", "--web", "--host", "0.0.0.0", "--port", "7860"]
