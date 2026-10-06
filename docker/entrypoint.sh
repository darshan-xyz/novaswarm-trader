#!/bin/bash
set -e

SERVICE="${1:-api}"

echo "NovaSwarm Trader — Starting service: $SERVICE"

case "$SERVICE" in
    api)
        echo "Starting FastAPI server on port 8000..."
        exec python -m novaswarm.cli.main serve --host 0.0.0.0 --port 8000
        ;;
    chat)
        echo "Starting interactive AI chatbot..."
        exec python -m novaswarm.cli.main chat
        ;;
    telegram)
        echo "Starting Telegram bot..."
        exec python -m novaswarm.telegram_bot
        ;;
    mcp)
        echo "Starting MCP server (stdio)..."
        exec python -m novaswarm.mcp_server
        ;;
    daemon)
        echo "Starting autonomous trading daemon..."
        exec python -m novaswarm.cli.main daemon --once --paper
        ;;
    daemon-live)
        echo "Starting LIVE autonomous trading daemon..."
        exec python -m novaswarm.cli.main daemon --once --live --confirm-live
        ;;
    monitor)
        echo "Starting position monitor..."
        exec python -m novaswarm.cli.main monitor
        ;;
    scan)
        echo "Running market scan..."
        exec python -m novaswarm.cli.main scan
        ;;
    status)
        exec python -m novaswarm.cli.main status
        ;;
    shell)
        exec /bin/bash
        ;;
    *)
        echo "Unknown service: $SERVICE"
        echo ""
        echo "Available services:"
        echo "  api       — FastAPI backend (port 8000)"
        echo "  chat      — Interactive AI chatbot"
        echo "  telegram  — Telegram bot"
        echo "  mcp       — MCP server (stdio)"
        echo "  daemon    — Paper trading daemon"
        echo "  daemon-live — LIVE trading daemon"
        echo "  monitor   — Position monitor"
        echo "  scan      — Market scan"
        echo "  status    — System health check"
        echo "  shell     — Bash shell"
        exit 1
        ;;
esac
