FROM python:3.12-slim AS builder

WORKDIR /build
COPY . .
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.12-slim

COPY --from=builder /install /usr/local

RUN groupadd -r comply && useradd -r -g comply -s /usr/sbin/nologin comply

USER comply
WORKDIR /home/comply

EXPOSE 7860

CMD ["llm-comply", "--web", "--host", "0.0.0.0", "--port", "7860"]
