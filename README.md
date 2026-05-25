# Trench Tool

Solana token monitoring bot with real-time fresh wallet detection and BBB-style Telegram alerts.

## Features

- 🔍 **Freshies Tracking** - Detect fresh wallet purchases in real-time
- 💰 **Whale Detection** - 🐳 (>15 SOL) and 🐬 (>5 SOL) transactions
- 🚀 **Launchpad Detection** - Pump.fun, Meteora, Raydium, Orca, etc.
- 🤖 **Router Detection** - Axiom, BananaGun, Maestro, Trojan, etc.
- 📊 **Pattern Detection** - Volume spikes, dormant inflows, freshie selling
- 🎯 **Bundle Detection** - Identify coordinated purchases
- 📱 **Telegram Alerts** - Real-time notifications with trading links

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your API keys and settings

# 3. Start PostgreSQL & Redis (Docker)
docker-compose up -d postgres redis

# 4. Run the bot
python main.py
```

## Docker Deployment (24/7)

```bash
# Build and run everything
docker-compose up -d

# View logs
docker-compose logs -f backend
```

## Project Structure

```
trench-tool/
├── main.py              # FastAPI entry point
├── config.py            # Environment configuration
├── database.py          # PostgreSQL & Redis connections
├── services/            # Core bot services (29 modules)
│   ├── solana_listener.py
│   ├── wallet_classifier.py
│   ├── freshies_tracker.py
│   ├── bundle_detector.py
│   └── ...
├── filters/             # Transaction filters
│   ├── launchpad_detector.py
│   ├── router_detector.py
│   └── transaction_filter.py
├── alerts/              # Telegram bot & routing
│   ├── telegram_bot.py
│   ├── channel_router.py
│   └── alert_router.py
├── models/              # Database models
├── Dockerfile           # Production container
├── docker-compose.yml   # Full stack deployment
└── requirements.txt     # Python dependencies
```

## Environment Variables

See `.env.example` for all configuration options including:
- Solana RPC endpoints (Helius recommended for production)
- Telegram bot credentials
- Database connection strings
- Alert thresholds and settings

## Tech Stack

- **Backend**: Python 3.11+ / FastAPI / asyncio
- **Database**: PostgreSQL + Redis
- **Blockchain**: Solana (Helius RPC)
- **Alerts**: Telegram Bot API
