"""
Trench Tool V1 - Main Application
FastAPI application with real-time Solana and BSC transaction monitoring.
BBB-style alerts via Telegram.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import init_database, init_redis, close_database, close_redis
from services.solana_listener import get_solana_listener
from bsc.bsc_listener import get_bsc_listener

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Background tasks
solana_listener_task = None
bsc_listener_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global solana_listener_task, bsc_listener_task

    logger.info("🚀 Starting Trench Tool V1...")

    # Initialize database and Redis connections
    await init_database()
    await init_redis()
    logger.info("✅ Database and Redis initialized")

    # Start Solana listener as background task
    solana_listener = get_solana_listener()
    solana_listener_task = asyncio.create_task(solana_listener.start())
    logger.info("🟣 Solana listener started")
    
    # Start BSC listener as background task
    bsc_listener = get_bsc_listener()
    bsc_listener_task = asyncio.create_task(bsc_listener.start())
    logger.info("🟡 BSC listener started")
    
    logger.info("✅ Trench Tool V1 is running! (Solana + BSC)")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Trench Tool V1...")
    
    # Stop Solana listener
    await solana_listener.stop()
    if solana_listener_task:
        solana_listener_task.cancel()
        try:
            await solana_listener_task
        except asyncio.CancelledError:
            pass
    
    # Stop BSC listener
    await bsc_listener.stop()
    if bsc_listener_task:
        bsc_listener_task.cancel()
        try:
            await bsc_listener_task
        except asyncio.CancelledError:
            pass

    # Close database and Redis connections
    await close_database()
    await close_redis()

    logger.info("Trench Tool V1 stopped.")


# Create FastAPI app
app = FastAPI(
    title="Trench Tool V1",
    description="Solana + BSC fresh wallet detection bot with BBB-style alerts",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    solana_listener = get_solana_listener()
    bsc_listener = get_bsc_listener()
    
    return {
        "status": "healthy",
        "solana": solana_listener.get_stats(),
        "bsc": {
            "tx_received": bsc_listener._tx_received,
            "tx_processed": bsc_listener._tx_processed,
            "alerts_sent": bsc_listener._alerts_sent,
            "errors": bsc_listener._errors,
        },
    }


# Stats endpoint
@app.get("/stats")
async def get_stats():
    """Get overall system statistics."""
    solana_listener = get_solana_listener()
    bsc_listener = get_bsc_listener()
    
    return {
        "solana": solana_listener.get_stats(),
        "bsc": {
            "tx_received": bsc_listener._tx_received,
            "tx_processed": bsc_listener._tx_processed,
            "alerts_sent": bsc_listener._alerts_sent,
            "errors": bsc_listener._errors,
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )

