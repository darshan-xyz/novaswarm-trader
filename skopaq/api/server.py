"""FastAPI backend for SkopaqTrader.

Provides REST endpoints for the frontend dashboard and health checks.
Deployed on Railway via ``skopaq serve``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from skopaq import __version__
from skopaq.broker.token_manager import TokenManager
from skopaq.config import SkopaqConfig

logger = logging.getLogger(__name__)

_scanner_engine = None


def _get_scanner():
    """Lazy-init scanner engine singleton with real batch quote fetcher and LLM screener."""
    global _scanner_engine
    if _scanner_engine is None:
        from skopaq.scanner import ScannerEngine, Watchlist
        config = SkopaqConfig()
        _scanner_engine = ScannerEngine(
            watchlist=Watchlist(),
            cycle_seconds=config.scanner_cycle_seconds,
            max_candidates=config.scanner_max_candidates,
            quote_fetcher=ScannerEngine._default_quote_fetcher,
            llm_screener=ScannerEngine._default_llm_screener,
        )
    return _scanner_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Modern lifespan context manager replacing deprecated startup/shutdown events."""
    config = SkopaqConfig()
    if config.scanner_enabled:
        scanner = _get_scanner()
        await scanner.start()
        logger.info("Scanner background task started")
    yield
    if _scanner_engine and _scanner_engine.running:
        await _scanner_engine.stop()
        logger.info("Scanner background task stopped")


def _sec(val) -> str:
    """Safely extract string value from a SecretStr, str, or None."""
    if val is None:
        return ""
    if hasattr(val, "get_secret_value"):
        return val.get_secret_value()
    return str(val)


app = FastAPI(
    title="SkopaqTrader API",
    version=__version__,
    docs_url="/docs",
    lifespan=lifespan,
)

# CORS — allow frontend (Vercel) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Chat bridge (OpenClaw + external channels) ───────────────────────────────
from skopaq.chat.bridge import router as chat_router

app.include_router(chat_router)

# ── Expanded REST Routers ───────────────────────────────────────────────────
from skopaq.api.trades_router import router as trades_router
from skopaq.api.analysis_router import router as analysis_router
from skopaq.api.memory_router import router as memory_router
from skopaq.api.performance_router import router as performance_router
from skopaq.api.safety_router import router as safety_router
from skopaq.api.system_router import router as system_router

app.include_router(trades_router)
app.include_router(analysis_router)
app.include_router(memory_router)
app.include_router(performance_router)
app.include_router(safety_router)
app.include_router(system_router)


# ── Kite Connect OAuth ───────────────────────────────────────────────────────

@app.get("/api/kite/login")
async def kite_login():
    """Redirect to Zerodha Kite login page."""
    from skopaq.broker.kite_client import KiteClient

    config = SkopaqConfig()
    if not config.kite_api_key:
        raise HTTPException(400, "SKOPAQ_KITE_API_KEY not configured")

    client = KiteClient(api_key=config.kite_api_key)
    from fastapi.responses import RedirectResponse

    return RedirectResponse(client.login_url)


@app.get("/api/kite/callback")
async def kite_callback(request_token: str = "", status: str = ""):
    """Handle Kite OAuth callback — exchange request_token for access_token."""
    from skopaq.broker.kite_client import KiteClient

    config = SkopaqConfig()
    if not request_token or status != "success":
        raise HTTPException(400, f"Login failed: status={status}")

    secret = _sec(config.kite_api_secret)
    if not config.kite_api_key or not secret:
        raise HTTPException(400, "Kite API key or secret not configured")

    client = KiteClient(
        api_key=config.kite_api_key,
        api_secret=secret,
    )
    try:
        session = client.generate_session(request_token)
        return {
            "status": "success",
            "user_id": session.get("user_id"),
            "access_token_set": True,
            "message": "Kite login successful. Bot is now connected to Zerodha.",
        }
    except Exception as exc:
        raise HTTPException(500, f"Session generation failed: {exc}")


@app.get("/api/kite/status")
async def kite_status():
    """Check if Kite access token is set."""
    from skopaq.broker.kite_client import get_access_token

    token = get_access_token()
    return {
        "connected": bool(token),
        "token_length": len(token) if token else 0,
    }


@app.get("/api/kite/token")
async def kite_token():
    """Return the Kite access token (for internal service-to-service use).

    The Telegram bot fetches this to share the Kite session established
    via the API app's OAuth login flow.
    """
    from skopaq.broker.kite_client import get_access_token

    token = get_access_token()
    if not token:
        raise HTTPException(404, "No Kite token available. Login first.")
    return {"access_token": token}


@app.post("/api/kite/postback")
async def kite_postback(request: Request):
    """Receive real-time order updates from Zerodha.

    Zerodha POSTs order status changes (fill, rejection, cancellation)
    to this endpoint. We log them and can trigger alerts via Telegram.
    """
    try:
        body = await request.json()
    except Exception:
        body = dict(await request.form())

    order_id = body.get("order_id", "?")
    status = body.get("status", "?")
    symbol = body.get("tradingsymbol", "?")
    txn = body.get("transaction_type", "?")
    qty = body.get("filled_quantity", body.get("quantity", 0))
    price = body.get("average_price", 0)

    logger.info(
        "Kite postback: %s %s %s qty=%s price=%s status=%s",
        txn, symbol, order_id, qty, price, status,
    )

    # Auto-notify via centralized notification system
    try:
        from skopaq.notifications import notify_trade_event

        await notify_trade_event(
            action=txn,
            symbol=symbol,
            price=float(price) if price else 0,
            quantity=int(qty) if qty else 0,
            status=status,
            order_id=order_id,
        )
    except Exception:
        logger.warning("Postback notification failed", exc_info=True)

    return {"status": "ok"}


@app.get("/health")
async def health() -> dict:
    """Health check endpoint (used by Railway)."""
    config = SkopaqConfig()
    token_mgr = TokenManager()
    health = token_mgr.get_health()

    return {
        "status": "ok",
        "version": __version__,
        "mode": config.trading_mode,
        "token_valid": health.valid,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/status")
async def system_status() -> dict:
    """Detailed system status for the dashboard."""
    config = SkopaqConfig()
    token_mgr = TokenManager()
    token_health = token_mgr.get_health()

    return {
        "version": __version__,
        "mode": config.trading_mode,
        "broker": {
            "name": "INDstocks",
            "base_url": config.indstocks_base_url,
            "token_valid": token_health.valid,
            "token_expires_at": token_health.expires_at.isoformat() if token_health.expires_at else None,
            "token_remaining": str(token_health.remaining) if token_health.remaining else None,
            "token_warning": token_health.warning or None,
        },
        "services": {
            "supabase": bool(config.supabase_url),
            "redis": bool(config.upstash_redis_url),
            "llms": {
                "gemini": bool(_sec(config.google_api_key)),
                "claude": bool(_sec(config.anthropic_api_key)),
                "perplexity": bool(_sec(config.perplexity_api_key)),
                "grok": bool(_sec(config.xai_api_key)),
            },
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Scanner ───────────────────────────────────────────────────────────────────


@app.get("/api/scanner/status")
async def scanner_status() -> dict:
    """Scanner engine status."""
    scanner = _get_scanner()
    return scanner.status


@app.get("/api/scanner/candidates")
async def scanner_candidates() -> dict:
    """Recent scanner candidates."""
    scanner = _get_scanner()
    return {
        "candidates": [c.to_dict() for c in scanner._last_candidates],
        "last_candidates": [c.to_dict() for c in scanner._last_candidates],
        "queue_size": scanner.candidate_queue.qsize(),
    }


@app.post("/api/scanner/scan")
async def trigger_scan() -> dict:
    """Trigger an immediate, on-demand scanner cycle."""
    scanner = _get_scanner()
    candidates = await scanner.scan_once()
    for c in candidates:
        await scanner.candidate_queue.put(c)
    return {
        "success": True,
        "triggered_at": datetime.now(timezone.utc).isoformat(),
        "candidates_found": len(candidates),
        "candidates": [c.to_dict() for c in candidates],
    }


def _get_paper_engine():
    """Get the centralized shared paper engine singleton."""
    from skopaq.broker.paper_engine import get_shared_paper_engine

    return get_shared_paper_engine()


@app.get("/api/portfolio")
async def portfolio() -> dict:
    """Current portfolio snapshot (paper mode)."""
    config = SkopaqConfig()
    paper = _get_paper_engine()
    snapshot = paper.get_snapshot()

    positions_list = []
    for p in snapshot.positions:
        p_dict = p.model_dump()
        qty = float(p.quantity)
        avg_p = float(p.average_price)
        last_p = float(p.last_price or avg_p)
        cur_val = round(abs(qty) * last_p, 2)
        cost_val = abs(qty) * avg_p
        pnl = float(p.pnl or ((last_p - avg_p) * qty))
        pnl_pct = round((pnl / cost_val * 100), 2) if cost_val > 0 else 0.0

        p_dict.update({
            "symbol": p.symbol,
            "quantity": abs(qty),
            "side": "BUY" if qty >= 0 else "SELL",
            "avg_price": avg_p,
            "average_price": avg_p,
            "ltp": last_p,
            "last_price": last_p,
            "current_price": last_p,
            "current_value": cur_val,
            "unrealized_pnl": pnl,
            "unrealized_pnl_pct": pnl_pct,
            "day_pnl": float(p.day_pnl),
        })
        positions_list.append(p_dict)

    return {
        "total_value": float(snapshot.total_value),
        "cash": float(snapshot.cash),
        "positions_value": float(snapshot.positions_value),
        "day_pnl": float(snapshot.day_pnl),
        "positions": positions_list,
        "open_orders": [],
        "open_orders_count": snapshot.open_orders if isinstance(snapshot.open_orders, int) else len(snapshot.open_orders or []),
        "mode": config.trading_mode,
        "timestamp": snapshot.timestamp.isoformat(),
    }
