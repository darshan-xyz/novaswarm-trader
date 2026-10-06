# Telegram Bot Setup

NovaSwarm Trader includes a Telegram bot (`@NovaSwarm_bot`) that provides trade alerts, portfolio monitoring, and scheduled market updates. The bot is defined in `novaswarm/telegram_bot.py`.

## Create Your Bot

### Step 1: Register with BotFather

1. Open Telegram and search for `@BotFather`
2. Send `/newbot`
3. Choose a name (e.g., "NovaSwarm Trader")
4. Choose a username (e.g., `my_novaswarm_bot`)
5. BotFather gives you a token like `7123456789:AAH-abc123def456ghi789jkl`

### Step 2: Set the Token

Add the token to your `.env`:

```bash
NOVASWARM_TELEGRAM_BOT_TOKEN=7123456789:AAH-abc123def456ghi789jkl
```

Optionally set a default chat ID for notifications:

```bash
NOVASWARM_TELEGRAM_CHAT_ID=123456789
```

!!! tip "Finding your chat ID"
    Send `/start` to your bot, then check the logs. The chat ID is printed when the bot receives the first message. Alternatively, send a message to `@userinfobot`.

### Step 3: Configure Bot Commands (Optional)

Send these commands to `@BotFather` to set up the menu:

```
/setcommands
```

Then paste:

```
quote - Get real-time stock quote
portfolio - View positions and P&L
status - System health check
pnl - Current P&L summary
analyze - Quick stock analysis
login - Connect to Zerodha Kite
help - List all commands
```

## Running Locally

```bash
python -m novaswarm.telegram_bot
```

Or via the CLI:

```bash
novaswarm telegram  # If this command exists
```

The bot starts polling for messages and registers 3 scheduled jobs:

```
Starting NovaSwarm Trader Telegram bot...
Scheduled jobs:
  09:00 IST — Pre-market login reminder
  09:25 IST — Auto market scan
  15:35 IST — EOD P&L summary
Bot ready. Polling for messages...
```

## Deploying to Fly.io

### Step 1: Create the App

```bash
fly launch --name novaswarm-telegram --region bom --no-deploy
```

### Step 2: Set Secrets

```bash
fly secrets set \
  NOVASWARM_TELEGRAM_BOT_TOKEN="your-token" \
  NOVASWARM_KITE_API_KEY="your-key" \
  NOVASWARM_KITE_API_SECRET="your-secret" \
  NOVASWARM_GOOGLE_API_KEY="your-key" \
  -a novaswarm-telegram
```

### Step 3: Deploy

Use the Telegram-specific Fly config (`fly-telegram.toml`):

```bash
fly deploy --config fly-telegram.toml
```

The Telegram bot runs as a background worker (no HTTP port needed):

```toml
# fly-telegram.toml
app = 'novaswarm-telegram'
primary_region = 'bom'

[processes]
  app = "telegram"

[mounts]
  source = "novaswarm_data"
  destination = "/data"

[[vm]]
  memory = '512mb'
  cpu_kind = 'shared'
  cpus = 1
```

### Step 4: Create Volume for Token Persistence

```bash
fly volumes create novaswarm_data --region bom --size 1 -a novaswarm-telegram
```

The Kite access token is persisted to `/data/novaswarm_kite_token.json` so it survives restarts.

## Deploying with Docker

```bash
docker run -d \
  --name novaswarm-telegram \
  --env-file .env \
  samuelvinay91/novaswarm:latest \
  telegram
```

Or with Docker Compose:

```bash
docker compose up -d telegram
```

## Architecture

```
Telegram Cloud
      │
      │ (polling)
      ▼
novaswarm/telegram_bot.py
      │
      ├── Command Handlers (/quote, /portfolio, etc.)
      ├── Natural Language Handler (AI chat brain)
      ├── Scheduled Jobs (login, scan, EOD)
      │
      ├── novaswarm/broker/kite_client.py (market data)
      ├── novaswarm/notifications.py (centralized alerts)
      └── novaswarm/mcp_server.py (analysis tools)
```

## Notification System

The bot integrates with `novaswarm/notifications.py`. Any part of the system can send alerts:

```python
from novaswarm.notifications import notify

await notify("Order filled: BUY 10x RELIANCE @ Rs 2,485")
```

Chat IDs are registered when users send `/start`. All registered chats receive notifications.

!!! warning "Single bot per token"
    Telegram allows only one bot instance per token. If you run the bot locally and on Fly.io simultaneously, one will fail to receive messages.
