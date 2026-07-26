# Trench Tool

Solana token monitoring bot with real-time fresh wallet detection and BBB-style Telegram alerts.

## Features

- ðŸ” **Freshies Tracking** - Detect fresh wallet purchases in real-time
- ðŸ’° **Whale Detection** - ðŸ³ (>15 SOL) and ðŸ¬ (>5 SOL) transactions
- ðŸš€ **Launchpad Detection** - Pump.fun, Meteora, Raydium, Orca, etc.
- ðŸ¤– **Router Detection** - Axiom, BananaGun, Maestro, Trojan, etc.
- ðŸ“Š **Pattern Detection** - Volume spikes, dormant inflows, freshie selling
- ðŸŽ¯ **Bundle Detection** - Identify coordinated purchases
- ðŸ“± **Telegram Alerts** - Real-time notifications with trading links

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
# Build and run both alert runtimes: V1 (SOL) and V2 (ETH/Base/Best Wallets)
docker compose up -d

# Verify both workers are healthy
docker compose ps
curl -f http://localhost:8000/health
curl -f http://localhost:8001/v2/signals
curl -f http://localhost:8001/v2/topics

# On the production host, repair any deleted/stale topic IDs and restart both workers
TRENCH_V2_ENV=.env TRENCH_V1_ENV=.env python scripts/reconcile_v2_topics.py
docker compose up -d --force-recreate backend v2-backend
```

## Project Structure

```
trench-tool/
â”œâ”€â”€ main.py              # FastAPI entry point
â”œâ”€â”€ config.py            # Environment configuration
â”œâ”€â”€ database.py          # PostgreSQL & Redis connections
â”œâ”€â”€ services/            # Core bot services (29 modules)
â”‚   â”œâ”€â”€ solana_listener.py
â”‚   â”œâ”€â”€ wallet_classifier.py
â”‚   â”œâ”€â”€ freshies_tracker.py
â”‚   â”œâ”€â”€ bundle_detector.py
â”‚   â””â”€â”€ ...
â”œâ”€â”€ filters/             # Transaction filters
â”‚   â”œâ”€â”€ launchpad_detector.py
â”‚   â”œâ”€â”€ router_detector.py
â”‚   â””â”€â”€ transaction_filter.py
â”œâ”€â”€ alerts/              # Telegram bot & routing
â”‚   â”œâ”€â”€ telegram_bot.py
â”‚   â”œâ”€â”€ channel_router.py
â”‚   â””â”€â”€ alert_router.py
â”œâ”€â”€ models/              # Database models
â”œâ”€â”€ Dockerfile           # Production container
â”œâ”€â”€ docker-compose.yml   # Full stack deployment
â””â”€â”€ requirements.txt     # Python dependencies
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
