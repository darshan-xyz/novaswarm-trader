# Installation

## Prerequisites

- Python 3.11+
- At least one LLM API key (Google Gemini recommended as minimum)
- Zerodha Kite Connect account (for live trading)

## Install from Source

```bash
git clone https://github.com/samuelvinay91/novaswarm-trader.git
cd novaswarm-trader
pip install -e .
```

## Install via Docker

```bash
docker pull samuelvinay91/novaswarm:latest
```

## API Keys

Create a `.env` file from the template:

```bash
cp .env.example .env
```

### Minimum Setup (Paper Trading)

```bash
# At least one LLM provider
NOVASWARM_GOOGLE_API_KEY=your-gemini-key
```

### Full Setup (Live Trading)

```bash
# LLM Providers
NOVASWARM_GOOGLE_API_KEY=...          # Gemini 3 Flash (analysts)
NOVASWARM_ANTHROPIC_API_KEY=...       # Claude Opus (research/risk manager)
NOVASWARM_OPENROUTER_API_KEY=...      # Grok + Perplexity (social + news)

# Broker
NOVASWARM_KITE_API_KEY=...            # Zerodha Kite Connect
NOVASWARM_KITE_API_SECRET=...         # Kite API secret

# Telegram Bot
NOVASWARM_TELEGRAM_BOT_TOKEN=...      # From @BotFather
NOVASWARM_TELEGRAM_CHAT_ID=...        # Your chat ID

# Trading Mode
NOVASWARM_TRADING_MODE=paper          # Start with paper, switch to live later
```

### Optional Services

```bash
# Supabase (agent memory persistence)
NOVASWARM_SUPABASE_URL=...
NOVASWARM_SUPABASE_SERVICE_KEY=...

# Ollama (local model fallback)
NOVASWARM_OLLAMA_ENABLED=true
NOVASWARM_OLLAMA_BASE_URL=http://localhost:11434
```

## Verify Installation

```bash
novaswarm status    # System health check
novaswarm --help    # All commands
```

## Model Tiering

| Role | Primary | Fallback | Local |
|------|---------|----------|-------|
| Analysts | Gemini 3 Flash | — | Ollama |
| Social Analyst | Grok 3 Mini | Gemini | Ollama |
| Research/Risk Manager | Claude Opus | Gemini | — |
| Chat Brain | Claude Opus | Gemini | Ollama |
| Scanner | Gemini + Grok + Perplexity | — | — |
