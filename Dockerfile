FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FASTEMBED_CACHE_PATH=/app/models \
    LANGSMITH_TRACING=false

WORKDIR /app

# Dependencies first: this layer is cached, so code changes rebuild fast
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Download the embedding model and test retrieval at BUILD time (no API key needed)
RUN python -c "from src.retrieval.search import hybrid_search; r = hybrid_search('cancellation refund', k=3); print('build check: retrieved', len(r), 'chunks')"

# Don't run as root
RUN useradd -m app && chown -R app /app
USER app

EXPOSE 8080
# --proxy-headers: behind Cloud Run, the real user IP is in X-Forwarded-For.
# Without it, every user shares ONE rate limit (the proxy's IP).
CMD ["sh", "-c", "uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'"]