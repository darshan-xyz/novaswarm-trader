# Configuration

All configuration is via environment variables with the `NOVASWARM_` prefix, loaded from `.env`.

## Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `NOVASWARM_TRADING_MODE` | `paper` | `paper` or `live` |
| `NOVASWARM_ASSET_CLASS` | `equity` | `equity` or `crypto` |
| `NOVASWARM_INITIAL_PAPER_CAPITAL` | `1000000` | Paper trading capital (INR) |

## LLM API Keys

| Variable | Required | Used For |
|----------|----------|----------|
| `NOVASWARM_GOOGLE_API_KEY` | Yes | Gemini Flash (all analysts) |
| `NOVASWARM_ANTHROPIC_API_KEY` | Recommended | Claude Opus (judge roles, chat brain) |
| `NOVASWARM_OPENROUTER_API_KEY` | Optional | Grok (social) + Perplexity (scanner) |

## Broker

| Variable | Description |
|----------|-------------|
| `NOVASWARM_KITE_API_KEY` | Zerodha Kite Connect API key |
| `NOVASWARM_KITE_API_SECRET` | Kite API secret |
| `NOVASWARM_INDSTOCKS_TOKEN` | INDstocks API token (alternative broker) |

## Risk Management

| Variable | Default | Description |
|----------|---------|-------------|
| `NOVASWARM_POSITION_SIZING_ENABLED` | `true` | ATR-based position sizing |
| `NOVASWARM_RISK_PER_TRADE_PCT` | `0.01` | 1% of equity per trade |
| `NOVASWARM_ATR_MULTIPLIER` | `2.0` | Stop distance in ATR units |
| `NOVASWARM_MAX_SECTOR_CONCENTRATION_PCT` | `0.40` | Max 40% in one sector |
| `NOVASWARM_MIN_CONFIDENCE_PCT` | `0` | Minimum AI confidence to trade |

## Position Monitor

| Variable | Default | Description |
|----------|---------|-------------|
| `NOVASWARM_MONITOR_POLL_INTERVAL_SECONDS` | `10` | Check interval |
| `NOVASWARM_MONITOR_HARD_STOP_PCT` | `0.04` | 4% hard stop |
| `NOVASWARM_MONITOR_EOD_EXIT_MINUTES_BEFORE_CLOSE` | `10` | EOD exit at 15:20 |
| `NOVASWARM_MONITOR_TRAILING_STOP_ENABLED` | `false` | Enable trailing stop |
| `NOVASWARM_MONITOR_TRAILING_STOP_PCT` | `0.02` | 2% trail distance |

## Daemon (Autonomous)

| Variable | Default | Description |
|----------|---------|-------------|
| `NOVASWARM_DAEMON_MAX_TRADES_PER_SESSION` | `3` | Max BUY orders/day |
| `NOVASWARM_DAEMON_MAX_CANDIDATES_TO_ANALYZE` | `5` | Top N scanner picks |
| `NOVASWARM_DAEMON_SCAN_DELAY_AFTER_OPEN_SECONDS` | `60` | Wait after 9:15 |

## Telegram

| Variable | Description |
|----------|-------------|
| `NOVASWARM_TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `NOVASWARM_TELEGRAM_CHAT_ID` | Your chat ID for auto-notifications |

## Ollama (Local Models)

| Variable | Default | Description |
|----------|---------|-------------|
| `NOVASWARM_OLLAMA_ENABLED` | `false` | Enable local model fallback |
| `NOVASWARM_OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server |
| `NOVASWARM_OLLAMA_MODEL` | (auto-detect) | Model name |
