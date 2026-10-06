"""Native crypto data fetching — on-chain metrics, DeFi TVL, and derivatives data.

Provides clean-room public API integration:
- On-chain: Blockchair & Blockchain.info
- DeFi: DeFiLlama
- Derivatives: Binance Futures public endpoints
"""

from __future__ import annotations

import logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

CHAIN_MAP: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "bnb",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "DOT": "polkadot",
    "AVAX": "avalanche",
    "MATIC": "polygon",
    "LTC": "litecoin",
    "LINK": "chainlink",
    "ATOM": "cosmos",
    "UNI": "uniswap",
    "NEAR": "near",
}

BLOCKCHAIR_BASE = "https://api.blockchair.com"
DEFILLAMA_BASE = "https://api.llama.fi"
BINANCE_FUTURES_BASE = "https://fapi.binance.com"
_TIMEOUT = httpx.Timeout(15.0, connect=10.0)


def _strip_coin(symbol: str) -> str:
    """Extract base coin from trading pair (e.g. BTCUSDT -> BTC)."""
    sym = symbol.upper().strip().replace("/", "").replace("_", "")
    if "-" in sym:
        return sym.split("-")[0]
    for suffix in ("USDT", "BUSD", "USDC", "USD"):
        if sym.endswith(suffix) and len(sym) > len(suffix):
            return sym[:-len(suffix)]
    return sym


def get_blockchain_stats(coin: str) -> str:
    """Fetch on-chain network statistics for a coin from public endpoints."""
    base_coin = _strip_coin(coin)
    chain = CHAIN_MAP.get(base_coin, base_coin.lower())

    url = f"{BLOCKCHAIR_BASE}/{chain}/stats"
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return f"Blockchain stats unavailable for {coin} (HTTP {resp.status_code})"
            data = (resp.json() or {}).get("data") or {}
            return (
                f"=== Blockchain Stats for {base_coin} ({chain}) ===\n"
                f"Blocks: {data.get('blocks', 'N/A')}\n"
                f"Transactions (24h): {data.get('transactions_24h', 'N/A')}\n"
                f"Mempool TPS: {data.get('tps', 'N/A')}\n"
                f"Hashrate: {data.get('hashrate_24h', 'N/A')}\n"
                f"Difficulty: {data.get('difficulty', 'N/A')}\n"
                f"Market Price (USD): ${data.get('market_price_usd', 'N/A')}\n"
            )
    except Exception as exc:
        logger.warning("Blockchain stats fetch failed for %s: %s", coin, exc)
        return f"Blockchain stats error for {coin}: {exc}"


DEFAULT_ADDRESSES = {
    "BTC": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
    "ETH": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
}


def get_address_activity(coin: str, address: Optional[str] = None, days: int = 3) -> str:
    """Fetch address activity summary from public endpoints."""
    base_coin = _strip_coin(coin)
    addr = address or DEFAULT_ADDRESSES.get(base_coin, "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
    chain = CHAIN_MAP.get(base_coin, base_coin.lower())
    url = f"{BLOCKCHAIR_BASE}/{chain}/dashboards/address/{addr}"
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.get(url, params={"limit": 5})
            if resp.status_code != 200:
                return f"Address activity unavailable (HTTP {resp.status_code})"
            res_json = resp.json() or {}
            data = (res_json.get("data") or {}).get(addr) or {}
            addr_info = data.get("address") or {}
            divisor = 1e18 if base_coin in ("ETH", "BNB", "MATIC") else 1e8
            balance = float(addr_info.get("balance") or 0) / divisor
            received = float(addr_info.get("received") or 0) / divisor
            return (
                f"=== Address Summary for {addr} ({base_coin}) ===\n"
                f"Balance: {balance:.4f} {base_coin}\n"
                f"Total Received: {received:.4f} {base_coin}\n"
                f"Transactions: {addr_info.get('transaction_count', 0)}\n"
            )
    except Exception as exc:
        return f"Address activity error: {exc}"


def get_token_fundamentals(token: str) -> str:
    """Fetch protocol fundamentals and TVL from DeFiLlama or CoinGecko."""
    base = _strip_coin(token).lower()
    url = f"{DEFILLAMA_BASE}/protocol/{base}"
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                data = resp.json() or {}
                tvl = float(data.get("tvl") or 0)
                return (
                    f"=== DeFi Fundamentals: {data.get('name', token)} ===\n"
                    f"Category: {data.get('category', 'N/A')}\n"
                    f"Chains: {', '.join(data.get('chains') or [])}\n"
                    f"Current TVL: ${tvl:,.2f}\n"
                    f"Description: {str(data.get('description') or '')[:300]}\n"
                )
            # Fallback for base cryptocurrencies (BTC, ETH, etc.) via CoinGecko
            cg_id = {"btc": "bitcoin", "eth": "ethereum", "sol": "solana"}.get(base, base)
            cg_url = f"https://api.coingecko.com/api/v3/coins/{cg_id}"
            cg_resp = client.get(cg_url, params={"localization": "false", "tickers": "false", "community_data": "false"})
            if cg_resp.status_code == 200:
                cg_data = cg_resp.json() or {}
                mdata = cg_data.get("market_data") or {}
                price = (mdata.get("current_price") or {}).get("usd", "N/A")
                mcap = float((mdata.get("market_cap") or {}).get("usd") or 0)
                circ = float(mdata.get("circulating_supply") or 0)
                return (
                    f"=== Market Fundamentals: {cg_data.get('name', token)} ===\n"
                    f"Current Price (USD): ${price}\n"
                    f"Market Cap: ${mcap:,.0f}\n"
                    f"Circulating Supply: {circ:,.0f}\n"
                )
            return f"Protocol fundamentals not found for {token}"
    except Exception as exc:
        return f"DeFi fundamentals error: {exc}"


def get_defi_tvl(protocol: str) -> str:
    """Fetch current Total Value Locked (TVL) for a protocol."""
    return get_token_fundamentals(protocol)


def get_chain_tvl_overview(chain: Optional[str] = None) -> str:
    """Fetch chain-level Total Value Locked summary from DeFiLlama."""
    url = f"{DEFILLAMA_BASE}/v2/chains"
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return f"Chain TVL unavailable (HTTP {resp.status_code})"
            chains = resp.json()
            if not isinstance(chains, list):
                return "Chain TVL unavailable: unexpected format"
            if not chain:
                valid_chains = [c for c in chains if isinstance(c, dict)]
                top = sorted(valid_chains, key=lambda c: float(c.get("tvl") or 0), reverse=True)[:5]
                lines = ["=== Top Chains by TVL ==="]
                for c in top:
                    lines.append(f"- {c.get('name', 'N/A')}: ${float(c.get('tvl') or 0):,.2f}")
                return "\n".join(lines)
            target = chain.lower()
            match = next((c for c in chains if isinstance(c, dict) and str(c.get("name") or "").lower() == target), None)
            if not match:
                return f"Chain '{chain}' not found on DeFiLlama."
            return (
                f"=== Chain TVL: {match.get('name')} ===\n"
                f"TVL: ${float(match.get('tvl') or 0):,.2f}\n"
                f"Token: {match.get('tokenSymbol', 'N/A')}\n"
            )
    except Exception as exc:
        return f"Chain TVL overview error: {exc}"


def get_funding_rates(symbol: str, limit: int = 5) -> str:
    """Fetch current and historical funding rates from Binance Futures."""
    clean = symbol.upper().strip().replace("/", "").replace("_", "").replace("-", "")
    if not clean.endswith("USDT"):
        clean = f"{_strip_coin(clean)}USDT"
    sym = clean
    url = f"{BINANCE_FUTURES_BASE}/fapi/v1/fundingRate"
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.get(url, params={"symbol": sym, "limit": limit})
            if resp.status_code != 200:
                return f"Funding rate unavailable for {sym} (HTTP {resp.status_code})"
            records = resp.json()
            if not isinstance(records, list) or not records:
                return f"No funding records for {sym}."
            latest = records[-1]
            if not isinstance(latest, dict):
                return f"No valid funding records for {sym}."
            rate = float(latest.get("fundingRate") or 0)
            return (
                f"=== Funding Rates: {sym} ===\n"
                f"Latest Rate: {rate * 100:.4f}% ({'Longs pay shorts' if rate > 0 else 'Shorts pay longs'})\n"
                f"Annualized: {rate * 3 * 365 * 100:.2f}%\n"
            )
    except Exception as exc:
        return f"Funding rate error: {exc}"


def get_open_interest(symbol: str) -> str:
    """Fetch current open interest from Binance Futures."""
    clean = symbol.upper().strip().replace("/", "").replace("_", "").replace("-", "")
    if not clean.endswith("USDT"):
        clean = f"{_strip_coin(clean)}USDT"
    sym = clean
    url = f"{BINANCE_FUTURES_BASE}/fapi/v1/openInterest"
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.get(url, params={"symbol": sym})
            if resp.status_code != 200:
                return f"Open interest unavailable for {sym} (HTTP {resp.status_code})"
            data = resp.json()
            if not isinstance(data, dict):
                return f"Open interest unavailable for {sym}"
            return (
                f"=== Open Interest: {sym} ===\n"
                f"Open Interest: {float(data.get('openInterest') or 0):,.2f} contracts\n"
            )
    except Exception as exc:
        return f"Open interest error: {exc}"


def get_long_short_ratio(symbol: str, period: str = "5m", limit: int = 1) -> str:
    """Fetch top trader long/short position ratio from Binance Futures."""
    clean = symbol.upper().strip().replace("/", "").replace("_", "").replace("-", "")
    if not clean.endswith("USDT"):
        clean = f"{_strip_coin(clean)}USDT"
    sym = clean
    url = f"{BINANCE_FUTURES_BASE}/futures/data/topLongShortPositionRatio"
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.get(url, params={"symbol": sym, "period": period, "limit": limit})
            if resp.status_code != 200:
                return f"Long/Short ratio unavailable for {sym} (HTTP {resp.status_code})"
            records = resp.json()
            if not isinstance(records, list) or not records:
                return f"No ratio data for {sym}."
            rec = records[-1]
            if not isinstance(rec, dict):
                return f"No valid ratio data for {sym}."
            return (
                f"=== Top Trader Long/Short Ratio: {sym} ===\n"
                f"Long: {float(rec.get('longAccount') or 0) * 100:.1f}%\n"
                f"Short: {float(rec.get('shortAccount') or 0) * 100:.1f}%\n"
                f"Long/Short Ratio: {rec.get('longShortRatio', 'N/A')}\n"
            )
    except Exception as exc:
        return f"Long/Short ratio error: {exc}"

