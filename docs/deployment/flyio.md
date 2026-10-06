# Fly.io Deployment

NovaSwarm Trader runs on [Fly.io](https://fly.io/) with two apps: the API server and the Telegram bot. Both are deployed in the Mumbai region (`bom`) for lowest latency to Indian exchanges.

## Apps

| App | Purpose | Config | Type |
|-----|---------|--------|------|
| `novaswarm-trader` | FastAPI backend (REST API + Kite OAuth) | `fly.toml` | HTTP service |
| `novaswarm-telegram` | Telegram bot (polling + scheduled jobs) | `fly-telegram.toml` | Background worker |

## Initial Setup

### Step 1: Install Fly CLI

```bash
# macOS
brew install flyctl

# Linux
curl -L https://fly.io/install.sh | sh
```

### Step 2: Login

```bash
fly auth login
```

### Step 3: Create Apps

```bash
# API server
fly launch --name novaswarm-trader --region bom --no-deploy

# Telegram bot
fly launch --name novaswarm-telegram --region bom --no-deploy
```

### Step 4: Create Volumes

Volumes persist data across deploys (Kite tokens, logs):

```bash
fly volumes create novaswarm_data --region bom --size 1 -a novaswarm-trader
fly volumes create novaswarm_data --region bom --size 1 -a novaswarm-telegram
```

### Step 5: Set Secrets

```bash
# API server secrets
fly secrets set \
  NOVASWARM_KITE_API_KEY="..." \
  NOVASWARM_KITE_API_SECRET="..." \
  NOVASWARM_GOOGLE_API_KEY="..." \
  NOVASWARM_ANTHROPIC_API_KEY="..." \
  NOVASWARM_SUPABASE_URL="..." \
  NOVASWARM_SUPABASE_SERVICE_KEY="..." \
  -a novaswarm-trader

# Telegram bot secrets
fly secrets set \
  NOVASWARM_TELEGRAM_BOT_TOKEN="..." \
  NOVASWARM_KITE_API_KEY="..." \
  NOVASWARM_KITE_API_SECRET="..." \
  NOVASWARM_GOOGLE_API_KEY="..." \
  -a novaswarm-telegram
```

## Deploy

### API Server

```bash
fly deploy --config fly.toml
```

Configuration in `fly.toml`:

```toml
app = 'novaswarm-trader'
primary_region = 'bom'

[build]
  dockerfile = 'Dockerfile'

[env]
  PYTHONUNBUFFERED = '1'

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = 'stop'
  auto_start_machines = true
  min_machines_running = 1

[mounts]
  source = "novaswarm_data"
  destination = "/data"

[[vm]]
  memory = '1gb'
  cpu_kind = 'shared'
  cpus = 1
```

The API server:

- Runs on port 8000 with HTTPS
- Auto-stops when idle, auto-starts on requests
- Keeps at least 1 machine running
- Mounts a 1 GB volume at `/data` for token persistence

### Telegram Bot

```bash
fly deploy --config fly-telegram.toml
```

Configuration in `fly-telegram.toml`:

```toml
app = 'novaswarm-telegram'
primary_region = 'bom'

[build]
  dockerfile = 'Dockerfile'

[env]
  PYTHONUNBUFFERED = '1'

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

The Telegram bot:

- Runs as a background worker (no HTTP port)
- Uses 512 MB RAM (lighter than API)
- Shares the same volume mount for Kite token access

## URLs

After deployment:

| Service | URL |
|---------|-----|
| API | `https://novaswarm-trader.fly.dev` |
| Health check | `https://novaswarm-trader.fly.dev/health` |
| API docs | `https://novaswarm-trader.fly.dev/docs` |
| Kite login | `https://novaswarm-trader.fly.dev/api/kite/login` |
| Kite callback | `https://novaswarm-trader.fly.dev/api/kite/callback` |

!!! note "Kite redirect URL"
    Set `https://novaswarm-trader.fly.dev/api/kite/callback` as the redirect URL in your Kite Connect developer console.

## Monitoring

### Logs

```bash
# API logs
fly logs -a novaswarm-trader

# Telegram bot logs
fly logs -a novaswarm-telegram
```

### Status

```bash
fly status -a novaswarm-trader
fly status -a novaswarm-telegram
```

### SSH

```bash
fly ssh console -a novaswarm-trader
```

## Scaling

```bash
# Scale API to 2 machines
fly scale count 2 -a novaswarm-trader

# Increase memory
fly scale memory 2048 -a novaswarm-trader
```

## Cost

Rough monthly estimates (Fly.io shared-cpu pricing):

| Service | Spec | Estimated Cost |
|---------|------|---------------|
| API | 1 shared CPU, 1 GB RAM | ~$5/month |
| Telegram | 1 shared CPU, 512 MB RAM | ~$3/month |
| Volumes (2x 1 GB) | Persistent storage | ~$0.30/month |
| **Total** | | **~$8/month** |

!!! tip "Free tier"
    Fly.io offers a free tier that covers small apps. Check current pricing at [fly.io/pricing](https://fly.io/pricing).

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Deploy fails | Check `fly logs` for build errors |
| Token not persisting | Verify volume is mounted (`fly ssh console` then `ls /data`) |
| Kite login fails | Verify redirect URL matches in Kite developer console |
| Bot not responding | Check `fly status -a novaswarm-telegram` and logs |
| Out of memory | Scale up: `fly scale memory 2048 -a novaswarm-trader` |

## CI/CD

Deploy automatically on push to main:

```yaml
# .github/workflows/deploy.yml
name: Deploy to Fly.io
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: superfly/flyctl-actions/setup-flyctl@master
      - run: flyctl deploy --config fly.toml --remote-only
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
```
