"""Scanner engine — async background loop that screens watchlist stocks.

Multi-model scanning pipeline:
    1. Fetch quotes for all watchlist symbols
    2. Compute metrics (change%, volume ratio, gap%)
    3. Primary screen: Gemini Flash for technical candidate selection
    4. Optional: Perplexity Sonar for news-driven signals (parallel)
    5. Optional: Grok for social sentiment signals (parallel)
    6. Merge and deduplicate candidates, push to asyncio.Queue
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from novaswarm.scanner.models import ScannerCandidate, ScannerMetrics
from novaswarm.scanner.screen import (
    build_news_prompt,
    build_screen_prompt,
    build_social_prompt,
    parse_screen_response,
)
from novaswarm.scanner.watchlist import Watchlist

logger = logging.getLogger(__name__)


class ScannerEngine:
    """Background scanner that cycles every N seconds.

    Supports multi-model screening: a primary screener (technical metrics)
    plus optional news and social screeners that run in parallel.

    Args:
        watchlist: Symbols to scan.
        cycle_seconds: Interval between scan cycles.
        max_candidates: Max candidates per cycle.
        quote_fetcher: Async callable ``(symbols) -> list[dict]`` returning
            quote dicts with keys: symbol, ltp, open, high, low, close, volume.
            Defaults to paper-mode stub if not provided.
        llm_screener: Async callable ``(prompt) -> str`` that sends the
            screening prompt to an LLM and returns the response text.
            Defaults to a no-op if not provided.
        news_screener: Optional async callable ``(prompt) -> str`` for
            news-aware screening (Perplexity Sonar recommended).
        social_screener: Optional async callable ``(prompt) -> str`` for
            social sentiment screening (Grok recommended).
    """

    def __init__(
        self,
        watchlist: Optional[Watchlist] = None,
        cycle_seconds: int = 30,
        max_candidates: int = 5,
        quote_fetcher: Optional[Callable] = None,
        llm_screener: Optional[Callable] = None,
        news_screener: Optional[Callable] = None,
        social_screener: Optional[Callable] = None,
    ) -> None:
        self.watchlist = watchlist or Watchlist()
        self.cycle_seconds = cycle_seconds
        self.max_candidates = max_candidates
        self._quote_fetcher = quote_fetcher or self._default_quote_fetcher
        self._llm_screener = llm_screener or self._default_llm_screener
        self._news_screener = news_screener
        self._social_screener = social_screener
        self.candidate_queue: asyncio.Queue[ScannerCandidate] = asyncio.Queue()

        # State
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._cycle_count = 0
        self._last_cycle_at: Optional[datetime] = None
        self._last_candidates: list[ScannerCandidate] = []

    # ── Public API ────────────────────────────────────────────────────

    @property
    def running(self) -> bool:
        return self._running

    @property
    def status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "cycle_count": self._cycle_count,
            "last_cycle_at": self._last_cycle_at.isoformat() if self._last_cycle_at else None,
            "watchlist_size": len(self.watchlist),
            "cycle_seconds": self.cycle_seconds,
            "queue_size": self.candidate_queue.qsize(),
            "last_candidates": [c.to_dict() for c in self._last_candidates],
            "screeners": self._screener_info(),
        }

    async def start(self) -> None:
        """Start the background scanning loop."""
        if self._running:
            logger.warning("Scanner already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "Scanner started (cycle=%ds, watchlist=%d, screeners=%s)",
            self.cycle_seconds, len(self.watchlist),
            "+".join(self._screener_info()["active"]),
        )

    async def stop(self) -> None:
        """Stop the scanner gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Scanner stopped after %d cycles", self._cycle_count)

    async def scan_once(self) -> list[ScannerCandidate]:
        """Run a single scan cycle (useful for manual/CLI triggering)."""
        return await self._scan_cycle()

    # ── Internal ──────────────────────────────────────────────────────

    async def _run_loop(self) -> None:
        """Main loop — scan, wait, repeat."""
        while self._running:
            try:
                candidates = await self._scan_cycle()
                for c in candidates:
                    await self.candidate_queue.put(c)
                    logger.debug("Queued candidate: %s — %s", c.symbol, c.reason)
            except Exception:
                logger.exception("Scanner cycle failed")

            await asyncio.sleep(self.cycle_seconds)

    async def _scan_cycle(self) -> list[ScannerCandidate]:
        """Execute one full scan cycle with multi-model screening."""
        self._cycle_count += 1
        self._last_cycle_at = datetime.now(timezone.utc)

        # 1. Fetch quotes
        symbols = self.watchlist.symbols
        quotes = await self._quote_fetcher(symbols)

        if not quotes:
            logger.debug("No quotes returned for cycle %d", self._cycle_count)
            return []

        # 2. Compute metrics
        metrics = self._compute_metrics(quotes)

        # 3. Run screeners in parallel
        all_candidates = await self._run_screeners(metrics, symbols)

        # 4. Deduplicate (same symbol from multiple screeners)
        candidates = self._deduplicate(all_candidates)
        self._last_candidates = candidates

        logger.info(
            "Scan cycle %d: %d quotes → %d candidates (from %d raw)",
            self._cycle_count, len(quotes), len(candidates), len(all_candidates),
        )
        return candidates

    async def _run_screeners(
        self,
        metrics: list[ScannerMetrics],
        symbols: list[str],
    ) -> list[ScannerCandidate]:
        """Run all active screeners in parallel and collect candidates."""
        tasks: list[asyncio.Task] = []

        # Primary: technical screening (always runs)
        tasks.append(asyncio.create_task(
            self._screen_technical(metrics),
            name="screen_technical",
        ))

        # Optional: news screening (Perplexity Sonar)
        if self._news_screener:
            tasks.append(asyncio.create_task(
                self._screen_news(symbols),
                name="screen_news",
            ))

        # Optional: social screening (Grok)
        if self._social_screener:
            tasks.append(asyncio.create_task(
                self._screen_social(symbols),
                name="screen_social",
            ))

        # Wait for all screeners (with individual error isolation)
        all_candidates: list[ScannerCandidate] = []
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for task, result in zip(tasks, results):
            if isinstance(result, Exception):
                logger.warning(
                    "Screener '%s' failed: %s", task.get_name(), result,
                )
            elif isinstance(result, list):
                all_candidates.extend(result)

        return all_candidates

    async def _screen_technical(
        self, metrics: list[ScannerMetrics],
    ) -> list[ScannerCandidate]:
        """Technical metrics screening (Gemini Flash)."""
        prompt = build_screen_prompt(metrics, self.max_candidates)
        response_text = await self._llm_screener(prompt)
        candidates = parse_screen_response(response_text)
        metrics_by_sym = {m.symbol.upper(): m for m in metrics}

        # Tag source and attach computed metrics
        for c in candidates:
            c.metrics["source"] = "technical"
            m = metrics_by_sym.get(c.symbol.upper())
            if m:
                c.metrics["ltp"] = m.ltp
                c.metrics["change_pct"] = m.change_pct
                c.metrics["gap_pct"] = m.gap_pct
                c.metrics["volume_ratio"] = m.volume_ratio
                c.metrics["volume"] = m.volume

        # Algorithmic momentum fallback if LLM returned no candidates
        if not candidates and metrics:
            sorted_m = sorted(
                metrics,
                key=lambda m: abs(m.change_pct) * (m.volume_ratio or 1.0),
                reverse=True,
            )[: self.max_candidates]
            for m in sorted_m:
                direction = "gainer" if m.change_pct >= 0 else "loser"
                cand = ScannerCandidate(
                    symbol=m.symbol,
                    reason=f"Top technical {direction} with {m.change_pct:+.2f}% change and {m.volume_ratio:.1f}x volume",
                    urgency="high" if abs(m.change_pct) >= 2.0 or m.volume_ratio >= 1.5 else "normal",
                    metrics={
                        "source": "technical",
                        "ltp": m.ltp,
                        "change_pct": m.change_pct,
                        "gap_pct": m.gap_pct,
                        "volume_ratio": m.volume_ratio,
                        "volume": m.volume,
                    },
                )
                candidates.append(cand)

        return candidates

    async def _screen_news(self, symbols: list[str]) -> list[ScannerCandidate]:
        """News-aware screening (Perplexity Sonar)."""
        prompt = build_news_prompt(symbols, max_candidates=3)
        response_text = await self._news_screener(prompt)
        candidates = parse_screen_response(response_text)
        for c in candidates:
            c.metrics["source"] = "news"
        return candidates

    async def _screen_social(self, symbols: list[str]) -> list[ScannerCandidate]:
        """Social sentiment screening (Grok)."""
        prompt = build_social_prompt(symbols, max_candidates=3)
        response_text = await self._social_screener(prompt)
        candidates = parse_screen_response(response_text)
        for c in candidates:
            c.metrics["source"] = "social"
        return candidates

    @staticmethod
    def _deduplicate(
        candidates: list[ScannerCandidate],
    ) -> list[ScannerCandidate]:
        """Deduplicate candidates — merge reasons if same symbol from multiple sources.

        When multiple screeners flag the same stock, the candidate is promoted
        to "high" urgency and reasons are combined.
        """
        by_symbol: dict[str, list[ScannerCandidate]] = {}
        for c in candidates:
            by_symbol.setdefault(c.symbol, []).append(c)

        merged: list[ScannerCandidate] = []
        for symbol, group in by_symbol.items():
            if len(group) == 1:
                merged.append(group[0])
            else:
                # Multi-source confluence — combine and promote
                sources = [c.metrics.get("source", "?") for c in group]
                reasons = [f"[{c.metrics.get('source', '?')}] {c.reason}" for c in group]
                base_metrics: dict[str, Any] = {}
                for c in group:
                    base_metrics.update(c.metrics)
                base_metrics["sources"] = sources
                base_metrics["source"] = "multi"
                base_metrics["source_count"] = len(group)
                merged.append(ScannerCandidate(
                    symbol=symbol,
                    reason=" | ".join(reasons)[:200],
                    urgency="high",  # Multi-source = high urgency
                    metrics=base_metrics,
                ))

        # Sort: multi-source first, then high urgency, then rest
        merged.sort(key=lambda c: (
            -c.metrics.get("source_count", 1),
            0 if c.urgency == "high" else 1,
        ))

        return merged

    @staticmethod
    def _compute_metrics(quotes: list[dict]) -> list[ScannerMetrics]:
        """Compute scanner metrics from raw quote dicts."""
        metrics = []
        for q in quotes:
            symbol = q.get("symbol", "")
            ltp = float(q.get("ltp", 0))
            close = float(q.get("close", 0)) or ltp
            open_price = float(q.get("open", 0)) or ltp
            volume = int(q.get("volume", 0))
            avg_volume = int(q.get("avg_volume", 0)) or 1

            change_pct = ((ltp - close) / close * 100) if close else 0
            gap_pct = ((open_price - close) / close * 100) if close else 0
            volume_ratio = volume / avg_volume if avg_volume else 0

            metrics.append(ScannerMetrics(
                symbol=symbol,
                ltp=ltp,
                change_pct=round(change_pct, 2),
                volume=volume,
                volume_ratio=round(volume_ratio, 1),
                gap_pct=round(gap_pct, 2),
            ))

        return metrics

    def _screener_info(self) -> dict[str, Any]:
        """Return info about which screeners are active."""
        active = ["technical"]
        if self._news_screener:
            active.append("news")
        if self._social_screener:
            active.append("social")
        return {"active": active, "count": len(active)}

    # ── Default fetcher & screener ────────────────────────────────────

    @staticmethod
    async def _default_quote_fetcher(symbols: list[str]) -> list[dict]:
        """Batch-fetch live quotes across watchlist symbols using INDstocks or yfinance."""
        if not symbols:
            return []

        # 1. Attempt INDstocks if credentials are valid
        try:
            from novaswarm.broker.token_manager import TokenManager
            from novaswarm.config import NovaSwarmConfig

            config = NovaSwarmConfig()
            token_mgr = TokenManager()
            if token_mgr.get_health().valid:
                from novaswarm.broker.client import INDstocksClient
                from novaswarm.broker.scrip_resolver import resolve_scrip_code

                async with INDstocksClient(config, token_mgr) as client:
                    resolved: list[tuple[str, str]] = []
                    for sym in symbols:
                        try:
                            code = await resolve_scrip_code(client, sym)
                            resolved.append((sym, code))
                        except Exception:
                            pass
                    if resolved:
                        syms, codes = zip(*resolved)
                        raw_quotes = await client.get_quotes(list(codes), symbols=list(syms))
                        if raw_quotes:
                            return [
                                {
                                    "symbol": q.symbol,
                                    "ltp": q.ltp,
                                    "open": q.open,
                                    "high": q.high,
                                    "low": q.low,
                                    "close": q.close,
                                    "volume": q.volume,
                                    "avg_volume": q.volume,
                                }
                                for q in raw_quotes
                            ]
        except Exception as exc:
            logger.debug("INDstocks quote fetch unavailable: %s", exc)

        # 2. Universal live batch fetching via yfinance
        try:
            import pandas as pd
            import yfinance as yf

            def _to_yf(sym: str) -> str:
                s = sym.strip().upper()
                if s.endswith(".NS") or s.endswith(".BO") or s.startswith("^"):
                    return s
                return f"{s}.NS"

            yf_map = {_to_yf(s): s for s in symbols}
            tickers = list(yf_map.keys())

            df = await asyncio.to_thread(
                lambda: yf.download(
                    tickers,
                    period="5d",
                    interval="1d",
                    progress=False,
                    auto_adjust=False,
                )
            )

            if df is None or df.empty:
                logger.warning("yfinance batch download returned empty dataframe")
                return []

            quotes: list[dict] = []

            def _get_series(data: pd.DataFrame, col: str, ticker: str) -> pd.Series:
                if col in data:
                    sub = data[col]
                    if isinstance(sub, pd.DataFrame):
                        if ticker in sub.columns:
                            return sub[ticker].dropna()
                    elif isinstance(sub, pd.Series):
                        return sub.dropna()
                if ticker in data:
                    sub = data[ticker]
                    if isinstance(sub, pd.DataFrame):
                        if col in sub.columns:
                            return sub[col].dropna()
                    elif isinstance(sub, pd.Series):
                        return sub.dropna()
                if (col, ticker) in data.columns:
                    return data[(col, ticker)].dropna()
                if (ticker, col) in data.columns:
                    return data[(ticker, col)].dropna()
                return pd.Series(dtype=float)

            for ticker, orig_sym in yf_map.items():
                closes = _get_series(df, "Close", ticker)
                if len(closes) == 0:
                    continue

                opens = _get_series(df, "Open", ticker)
                highs = _get_series(df, "High", ticker)
                lows = _get_series(df, "Low", ticker)
                vols = _get_series(df, "Volume", ticker)

                ltp = float(closes.iloc[-1])
                close = float(closes.iloc[-2]) if len(closes) >= 2 else ltp
                open_price = float(opens.iloc[-1]) if len(opens) >= 1 else ltp
                high_price = float(highs.iloc[-1]) if len(highs) >= 1 else ltp
                low_price = float(lows.iloc[-1]) if len(lows) >= 1 else ltp
                volume = int(vols.iloc[-1]) if len(vols) >= 1 else 0
                avg_volume = int(vols.mean()) if len(vols) >= 1 else max(volume, 1)

                quotes.append({
                    "symbol": orig_sym,
                    "ltp": ltp,
                    "close": close,
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "volume": volume,
                    "avg_volume": avg_volume,
                })

            logger.info("Batch fetched %d quotes via yfinance", len(quotes))
            return quotes

        except Exception as exc:
            logger.exception("Batch quote fetcher failed: %s", exc)
            return []

    @staticmethod
    async def _default_llm_screener(prompt: str) -> str:
        """Real LLM screener using Gemini Flash Lite via instantiate_model."""
        try:
            from langchain_core.messages import HumanMessage
            from novaswarm.llm import bridge_env_vars, instantiate_model, extract_text

            bridge_env_vars()
            model = instantiate_model("google", "gemini-flash-lite-latest", temperature=0.1)
            if hasattr(model, "ainvoke"):
                res = await model.ainvoke([HumanMessage(content=prompt)])
            else:
                res = await asyncio.to_thread(lambda: model.invoke([HumanMessage(content=prompt)]))
            return extract_text(res.content) if hasattr(res, "content") else str(res)
        except Exception as exc:
            logger.warning("Default LLM screener failed: %s", exc)
            return "[]"
