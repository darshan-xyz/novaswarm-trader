"""Zerodha Kite Connect broker client.

Wraps the ``kiteconnect`` SDK to match the same interface used by
``INDstocksClient`` — so the ``OrderRouter`` can switch between
brokers transparently.

OAuth login flow:
    1. User visits ``/api/kite/login`` → redirected to Zerodha login
    2. After login, Zerodha redirects to ``/api/kite/callback?request_token=XXX``
    3. Callback exchanges request_token for access_token
    4. Access token stored in memory (valid for one trading day)

Usage::

    from novaswarm.broker.kite_client import KiteClient

    client = KiteClient(api_key="...", api_secret="...", access_token="...")
    quote = client.get_quote("NSE:TCS")
    positions = client.get_positions()
"""

from __future__ import annotations

import logging
import os as _os
import tempfile as _tempfile
from decimal import Decimal
from typing import Optional

try:
    from kiteconnect import KiteConnect
except ImportError:
    KiteConnect = None

from novaswarm.broker.models import (
    Funds,
    Holding,
    OrderRequest,
    OrderResponse,
    Position,
    Quote,
)

logger = logging.getLogger(__name__)

# Module-level access token cache
_access_token: str = ""

# Persistent storage: /data on Fly.io (volume mount), temp directory locally
_DATA_DIR = "/data" if _os.path.isdir("/data") else _tempfile.gettempdir()
_TOKEN_FILE = _os.path.join(_DATA_DIR, "novaswarm_kite_token.json")


def set_access_token(token: str) -> None:
    """Set the Kite access token and persist to file + env var."""
    global _access_token
    _access_token = token

    # Persist to file so it survives module reloads
    import json
    from datetime import datetime, timezone

    try:
        with open(_TOKEN_FILE, "w") as f:
            json.dump({
                "access_token": token,
                "set_at": datetime.now(timezone.utc).isoformat(),
            }, f)
        logger.info("Kite access token set and persisted")
    except Exception as exc:
        logger.warning("Could not persist Kite token: %s", exc)

    # Also set as env var for subprocess access
    import os
    os.environ["NOVASWARM_KITE_ACCESS_TOKEN"] = token


def get_access_token() -> str:
    """Get the current access token.

    Priority:
    1. Module-level cache (fastest)
    2. Persisted file (/tmp/novaswarm_kite_token.json)
    3. NOVASWARM_KITE_ACCESS_TOKEN env var
    4. NovaSwarmConfig (from .env)
    """
    global _access_token
    if _access_token:
        return _access_token

    # Try persisted file
    import json

    try:
        with open(_TOKEN_FILE) as f:
            data = json.load(f)
            token = data.get("access_token", "")
            if token:
                _access_token = token
                logger.info("Kite token restored from file")
                return token
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # Try env var
    import os

    env_token = os.environ.get("NOVASWARM_KITE_ACCESS_TOKEN", "")
    if env_token:
        _access_token = env_token
        logger.info("Kite token restored from env var")
        return env_token

    # Try config
    try:
        from novaswarm.config import NovaSwarmConfig

        config = NovaSwarmConfig()
        if config.kite_access_token:
            cfg_token = config.kite_access_token.get_secret_value()
            if cfg_token:
                _access_token = cfg_token
                return cfg_token
    except Exception:
        pass

    # Try fetching from the API server (for Telegram bot running on separate machine)
    try:
        import httpx

        resp = httpx.get("https://novaswarm-trader.fly.dev/api/kite/token", timeout=5)
        if resp.status_code == 200:
            token = resp.json().get("access_token", "")
            if token:
                _access_token = token
                # Persist locally so we don't keep fetching
                set_access_token(token)
                logger.info("Kite token fetched from API server")
                return token
    except Exception:
        pass

    return ""


class KiteClient:
    """Zerodha Kite Connect client matching INDstocksClient interface."""

    def __init__(
        self,
        api_key: str,
        api_secret: str = "",
        access_token: str = "",
    ) -> None:
        if KiteConnect is None:
            raise ImportError(
                "kiteconnect package is required to use KiteClient. "
                "Install it with: pip install kiteconnect"
            )
        self._api_key = api_key
        self._api_secret = api_secret
        self._kite = KiteConnect(api_key=api_key)

        token = access_token or get_access_token()
        if token:
            self._kite.set_access_token(token)

    def set_access_token(self, token: str) -> None:
        """Set access token (call after OAuth flow)."""
        self._kite.set_access_token(token)
        set_access_token(token)

    def generate_session(self, request_token: str) -> dict:
        """Exchange request_token for access_token."""
        data = self._kite.generate_session(
            request_token, api_secret=self._api_secret
        )
        self._kite.set_access_token(data["access_token"])
        set_access_token(data["access_token"])
        logger.info("Kite session generated for %s", data.get("user_id", "?"))
        return data

    @property
    def login_url(self) -> str:
        """Get the Kite login URL for OAuth."""
        return self._kite.login_url()

    # ── Market Data ──────────────────────────────────────────────────────

    async def get_quote(self, scrip_code: str, symbol: str = "") -> Quote:
        """Get real-time quote. ``scrip_code`` is ``NSE:TCS`` format."""
        import asyncio

        data = await asyncio.to_thread(
            self._kite.quote, [scrip_code]
        )
        data = data or {}
        q = data.get(scrip_code) or {}
        ohlc = q.get("ohlc") or {}

        depth = q.get("depth") or {}
        buy_depth = depth.get("buy") or []
        sell_depth = depth.get("sell") or []
        bid = buy_depth[0].get("price", 0) if buy_depth and isinstance(buy_depth[0], dict) else 0
        ask = sell_depth[0].get("price", 0) if sell_depth and isinstance(sell_depth[0], dict) else 0

        close_price = ohlc.get("close") or 0
        net_change = q.get("net_change") or 0
        change_pct = round((net_change / close_price) * 100, 2) if close_price else 0.0

        return Quote(
            symbol=symbol or (scrip_code.split(":")[-1] if ":" in scrip_code else scrip_code),
            exchange=scrip_code.split(":")[0] if ":" in scrip_code else "NSE",
            ltp=float(q.get("last_price") or 0),
            open=float(ohlc.get("open") or 0),
            high=float(ohlc.get("high") or 0),
            low=float(ohlc.get("low") or 0),
            close=float(close_price),
            volume=int(q.get("volume") or 0),
            change=float(net_change),
            change_pct=float(change_pct),
            bid=float(bid),
            ask=float(ask),
        )

    async def get_positions(self) -> list[Position]:
        """Get open positions."""
        import asyncio

        data = await asyncio.to_thread(self._kite.positions)
        positions = []
        for p in (data or {}).get("net", []):
            qty = p.get("quantity", 0)
            if qty != 0:
                positions.append(Position(
                    symbol=p.get("tradingsymbol", ""),
                    exchange=p.get("exchange", ""),
                    product=p.get("product", ""),
                    quantity=Decimal(str(qty)),
                    average_price=float(p.get("average_price") or 0),
                    last_price=float(p.get("last_price") or 0),
                    pnl=float(p.get("pnl") or 0),
                    day_pnl=float(p.get("day_m2m") or 0),
                ))
        return positions

    async def get_holdings(self) -> list[Holding]:
        """Get delivery holdings."""
        import asyncio

        data = await asyncio.to_thread(self._kite.holdings)
        return [
            Holding(
                symbol=h.get("tradingsymbol", ""),
                exchange=h.get("exchange", ""),
                quantity=Decimal(str(h.get("quantity", 0))),
                average_price=float(h.get("average_price") or 0),
                last_price=float(h.get("last_price") or 0),
                pnl=float(h.get("pnl") or 0),
                day_change=float(h.get("day_change") or 0),
                day_change_pct=float(h.get("day_change_percentage") or 0),
            )
            for h in (data or [])
        ]

    async def get_funds(self) -> Funds:
        """Get available margins/funds."""
        import asyncio

        data = await asyncio.to_thread(self._kite.margins)
        equity = (data or {}).get("equity") or {}
        avail = equity.get("available") or {}
        util = equity.get("utilised") or {}
        return Funds(
            available_cash=float(avail.get("cash", 0)),
            used_margin=float(util.get("debits", 0)),
            available_margin=float(equity.get("net", 0)),
            total_collateral=float(avail.get("collateral", 0)),
        )

    async def get_order_book(self) -> list[dict]:
        """Get today's orders."""
        import asyncio

        orders = await asyncio.to_thread(self._kite.orders)
        return orders or []

    async def place_order(self, order: OrderRequest) -> OrderResponse:
        """Place an order via Kite Connect."""
        import asyncio

        # Map our order types and products to Kite's
        variety = "regular"
        raw_order_type = getattr(order.order_type, "value", str(order.order_type))
        order_type_map = {
            "MARKET": "MARKET",
            "LIMIT": "LIMIT",
            "SL": "SL",
            "SLM": "SL-M",
            "SL-M": "SL-M",
        }
        order_type = order_type_map.get(raw_order_type.upper(), raw_order_type)

        exchange_val = getattr(order.exchange, "value", str(order.exchange))
        side_val = getattr(order.side, "value", str(order.side))

        raw_product = getattr(order.product, "value", str(order.product))
        product_map = {
            "INTRADAY": "MIS",
            "MARGIN": "NRML",
            "MIS": "MIS",
            "CNC": "CNC",
            "NRML": "NRML",
            "CO": "CO",
            "BO": "BO",
        }
        kite_product = product_map.get(raw_product.upper(), raw_product)

        # Sanitize symbol for Kite (no NSE: prefix or .NS suffix)
        tradingsymbol = order.symbol.split(":")[-1] if ":" in order.symbol else order.symbol
        if tradingsymbol.endswith(".NS") or tradingsymbol.endswith(".BO"):
            tradingsymbol = tradingsymbol[:-3]

        try:
            order_id = await asyncio.to_thread(
                self._kite.place_order,
                variety=variety,
                exchange=exchange_val,
                tradingsymbol=tradingsymbol,
                transaction_type=side_val,
                quantity=int(order.quantity),
                product=kite_product,
                order_type=order_type,
                price=float(order.price) if order.price else None,
                trigger_price=float(order.trigger_price) if order.trigger_price else None,
            )
            logger.info("Kite order placed: %s", order_id)

            # Auto-notify via Telegram
            try:
                from novaswarm.notifications import notify_trade_event

                await notify_trade_event(
                    side_val, tradingsymbol,
                    order.price or 0, int(order.quantity),
                    "PENDING", order_id=str(order_id),
                )
            except Exception:
                pass

            return OrderResponse(
                order_id=str(order_id),
                status="PENDING",
                message="Order placed via Kite Connect",
            )
        except Exception as exc:
            logger.error("Kite order failed: %s", exc)
            return OrderResponse(
                order_id="",
                status="FAILED",
                message=str(exc),
            )

    async def cancel_order(self, order_id: str, variety: str = "regular") -> OrderResponse:
        """Cancel an open order via Kite Connect."""
        import asyncio

        try:
            resp = await asyncio.to_thread(
                self._kite.cancel_order,
                variety=variety,
                order_id=order_id,
            )
            return OrderResponse(
                order_id=str(order_id),
                status="CANCELLED",
                message=f"Order cancelled: {resp}",
            )
        except Exception as exc:
            logger.error("Kite cancel order failed: %s", exc)
            return OrderResponse(
                order_id=str(order_id),
                status="FAILED",
                message=str(exc),
            )

    async def modify_order(
        self,
        order_id: str,
        quantity: Optional[int] = None,
        price: Optional[float] = None,
        order_type: Optional[str] = None,
        trigger_price: Optional[float] = None,
        variety: str = "regular",
    ) -> OrderResponse:
        """Modify an open order via Kite Connect."""
        import asyncio

        kwargs = {"variety": variety, "order_id": order_id}
        if quantity is not None:
            kwargs["quantity"] = int(quantity)
        if price is not None:
            kwargs["price"] = float(price)
        if order_type is not None:
            kwargs["order_type"] = str(order_type)
        if trigger_price is not None:
            kwargs["trigger_price"] = float(trigger_price)

        try:
            resp = await asyncio.to_thread(self._kite.modify_order, **kwargs)
            return OrderResponse(
                order_id=str(order_id),
                status="MODIFIED",
                message=f"Order modified: {resp}",
            )
        except Exception as exc:
            logger.error("Kite modify order failed: %s", exc)
            return OrderResponse(
                order_id=str(order_id),
                status="FAILED",
                message=str(exc),
            )

    # ── Context manager (compatibility with INDstocksClient) ─────────

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass
