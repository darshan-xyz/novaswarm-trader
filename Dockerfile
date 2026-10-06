# NovaSwarm Trader — Multi-service Docker image
#
# Services (select via NOVASWARM_SERVICE env var):
#   api       — FastAPI backend (default)
#   chat      — Interactive AI chatbot REPL
#   telegram  — Telegram bot (@NovaSwarm_bot)
#   mcp       — MCP server (stdio transport)
#   daemon    — Autonomous trading session
#   monitor   — Position monitor
#
# Quick start:
#   docker run -it --env-file .env novaswarm-trader/novaswarm-trader chat
#   docker run -d --env-file .env novaswarm-trader/novaswarm-trader telegram
#   docker run -d --env-file .env -p 8000:8000 novaswarm-trader/novaswarm-trader api
#
# Or use docker-compose.yml for all services at once.

FROM python:3.14-slim AS base

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (cached layer)
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e . 2>/dev/null || pip install --no-cache-dir . \
    && pip install --no-cache-dir python-telegram-bot>=21.0 langchain-ollama>=1.0.0 kiteconnect>=5.0.0 psycopg2-binary>=2.9 quantstats>=0.0.80 redis>=5.0 langchain-community>=0.3

# Copy application code
COPY . .

# Install the project in editable mode
RUN pip install --no-cache-dir -e .

# Create non-root user
RUN useradd -m -s /bin/bash novaswarm
USER novaswarm

EXPOSE 8000

# Health check for API mode
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Entry point script
COPY docker/entrypoint.sh /entrypoint.sh
USER root
RUN chmod +x /entrypoint.sh
USER novaswarm

ENTRYPOINT ["/entrypoint.sh"]
CMD ["api"]
