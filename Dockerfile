FROM python:3.12-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir .

EXPOSE 7860

CMD ["llm-comply", "--web", "--host", "0.0.0.0", "--port", "7860"]
