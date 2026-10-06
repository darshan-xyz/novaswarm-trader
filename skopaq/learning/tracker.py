"""Signal accuracy tracker — records every AI prediction and its outcome.

Tracks:
    - Per-symbol win rate (which stocks is the AI good/bad at?)
    - Confidence calibration (when AI says 75%, does it win 75%?)
    - Sector performance (IT, banking, energy — where's the edge?)
    - Regime performance (high VIX vs low VIX, trending vs ranging)
    - Time-of-day patterns (morning entries vs afternoon)
    - Stop-loss effectiveness (too tight? too loose?)
    - Holding period analysis (optimal duration per symbol)

All data persisted to Postgres for long-term learning.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Sector mapping for NIFTY 50 stocks
SECTOR_MAP = {
    "RELIANCE": "Energy", "ONGC": "Energy", "BPCL": "Energy",
    "HDFCBANK": "Banking", "ICICIBANK": "Banking", "SBIN": "Banking",
    "KOTAKBANK": "Banking", "AXISBANK": "Banking", "INDUSINDBK": "Banking",
    "TCS": "IT", "INFY": "IT", "WIPRO": "IT", "HCLTECH": "IT", "TECHM": "IT",
    "LT": "Infrastructure", "ULTRACEMCO": "Infrastructure", "GRASIM": "Infrastructure",
    "BHARTIARTL": "Telecom", "SUNPHARMA": "Pharma", "CIPLA": "Pharma",
    "TATAMOTORS": "Auto", "M&M": "Auto", "MARUTI": "Auto", "BAJAJ-AUTO": "Auto",
    "NTPC": "Power", "POWERGRID": "Power", "ADANIGREEN": "Power",
    "HINDALCO": "Metals", "TATASTEEL": "Metals", "JSWSTEEL": "Metals",
    "NESTLEIND": "FMCG", "HINDUNILVR": "FMCG", "ITC": "FMCG",
    "HDFC": "NBFC", "BAJFINANCE": "NBFC", "BAJAJFINSV": "NBFC",
}


@dataclass
class SignalRecord:
    """A recorded signal with outcome."""

    symbol: str
    signal: str  # BUY, SELL, HOLD
    confidence: int  # 0-100
    entry_price: float
    exit_price: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    won: bool = False
    sector: str = ""
    regime: str = ""  # "high_vix", "low_vix", "trending_up", "trending_down", "ranging"
    entry_hour: int = 0  # IST hour of entry
    holding_days: int = 0
    stop_loss_pct: float = 0.0
    stop_hit: bool = False
    target_hit: bool = False
    exit_reason: str = ""
    timestamp: str = ""


def _get_db():
    """Get Postgres connection."""
    try:
        import psycopg2
        url = os.environ.get("DATABASE_URL", "")
        if not url:
            try:
                from skopaq.config import SkopaqConfig
                cfg = SkopaqConfig()
                if cfg.database_url:
                    url = cfg.database_url.get_secret_value() if hasattr(cfg.database_url, "get_secret_value") else str(cfg.database_url)
            except Exception:
                pass
        if url:
            return psycopg2.connect(url)
    except Exception:
        pass
    return None


def _ensure_table():
    """Create signal_records table if needed."""
    conn = _get_db()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS signal_records (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                signal VARCHAR(10) NOT NULL,
                confidence INT DEFAULT 50,
                entry_price FLOAT,
                exit_price FLOAT DEFAULT 0,
                pnl FLOAT DEFAULT 0,
                pnl_pct FLOAT DEFAULT 0,
                won BOOLEAN DEFAULT false,
                sector VARCHAR(30),
                regime VARCHAR(30),
                entry_hour INT DEFAULT 0,
                holding_days INT DEFAULT 0,
                stop_loss_pct FLOAT DEFAULT 0,
                stop_hit BOOLEAN DEFAULT false,
                target_hit BOOLEAN DEFAULT false,
                exit_reason VARCHAR(50),
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_signal_symbol ON signal_records(symbol);
            CREATE INDEX IF NOT EXISTS idx_signal_sector ON signal_records(sector);
        """)
        conn.commit()
    except Exception as exc:
        logger.debug("Table create: %s", exc)
    finally:
        try:
            conn.close()
        except Exception:
            pass


_IN_MEMORY_SIGNALS: list[SignalRecord] = []


def record_signal(record: SignalRecord) -> None:
    """Save a signal record to in-memory history and database if available."""
    # Auto-populate sector from SECTOR_MAP if missing
    if not record.sector and record.symbol:
        sym_clean = record.symbol.upper().split(":")[-1].replace(".NS", "").replace(".BO", "")
        record.sector = SECTOR_MAP.get(sym_clean, "")

    # Auto-populate entry_hour to current IST hour if unset
    if record.entry_hour == 0:
        ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
        record.entry_hour = ist_now.hour

    # Cache in memory
    _IN_MEMORY_SIGNALS.append(record)

    _ensure_table()
    conn = _get_db()
    if not conn:
        logger.debug("No Postgres connection — signal cached in-memory")
        return

    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO signal_records
            (symbol, signal, confidence, entry_price, exit_price, pnl, pnl_pct,
             won, sector, regime, entry_hour, holding_days, stop_loss_pct,
             stop_hit, target_hit, exit_reason)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                record.symbol,
                record.signal,
                record.confidence,
                record.entry_price,
                record.exit_price,
                record.pnl,
                record.pnl_pct,
                record.won,
                record.sector,
                record.regime,
                record.entry_hour,
                record.holding_days,
                record.stop_loss_pct,
                record.stop_hit,
                record.target_hit,
                record.exit_reason,
            ),
        )
        conn.commit()
        logger.info(
            "Signal recorded: %s %s %s pnl=%.2f",
            record.signal,
            record.symbol,
            "WIN" if record.won else "LOSS",
            record.pnl,
        )
    except Exception as exc:
        logger.warning("Failed to record signal: %s", exc)
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ── Multi-Tier Record Extraction ─────────────────────────────────────────────


def _get_all_records() -> list[dict]:
    """Retrieve all trade / signal records from Postgres, Supabase, or in-memory cache."""
    # Tier 1: Postgres
    conn = _get_db()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT symbol, signal, confidence, entry_price, exit_price, pnl, pnl_pct,
                       won, sector, regime, entry_hour, holding_days, stop_loss_pct,
                       stop_hit, target_hit, exit_reason
                FROM signal_records
            """)
            rows = cur.fetchall()
            if rows:
                return [
                    {
                        "symbol": r[0] or "",
                        "signal": r[1] or "BUY",
                        "confidence": int(r[2] or 50),
                        "entry_price": float(r[3] or 0.0),
                        "exit_price": float(r[4] or 0.0),
                        "pnl": float(r[5] or 0.0),
                        "pnl_pct": float(r[6] or 0.0),
                        "won": bool(r[7]),
                        "sector": r[8] or SECTOR_MAP.get(str(r[0] or "").upper(), "Other"),
                        "regime": r[9] or "normal",
                        "entry_hour": int(r[10] or 10),
                        "holding_days": int(r[11] or 0),
                        "stop_loss_pct": float(r[12] or 0.0),
                        "stop_hit": bool(r[13]),
                        "target_hit": bool(r[14]),
                        "exit_reason": r[15] or "",
                    }
                    for r in rows
                ]
        except Exception as exc:
            logger.debug("Postgres signal_records query failed: %s", exc)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # Tier 2: Supabase via get_safe_supabase()
    try:
        from skopaq.api.db_utils import get_safe_supabase

        client = get_safe_supabase()
        if client:
            res = client.table("trades").select("*").execute()
            rows = res.data or []
            if rows:
                results = []
                for r in rows:
                    raw_sym = str(r.get("symbol") or "")
                    sym = raw_sym.upper().split(":")[-1].replace(".NS", "").replace(".BO", "")
                    pnl = float(r.get("pnl") or 0.0)
                    pnl_pct = float(r.get("pnl_pct") or 0.0)
                    won = pnl > 0
                    conf = int(r.get("consensus_score") or 50)
                    sector = SECTOR_MAP.get(sym, "Other")
                    decision = r.get("agent_decision") or {}
                    if isinstance(decision, str):
                        try:
                            decision = json.loads(decision)
                        except Exception:
                            decision = {}
                    regime = decision.get("regime") or r.get("regime") or "normal"
                    exit_reason = str(r.get("exit_reason") or "")
                    stop_hit = "stop" in exit_reason.lower()
                    target_hit = "target" in exit_reason.lower()
                    entry_hour = 10
                    created_at_str = r.get("created_at") or ""
                    if created_at_str:
                        try:
                            dt = datetime.fromisoformat(str(created_at_str).replace("Z", "+00:00"))
                            entry_hour = dt.hour
                        except Exception:
                            entry_hour = 10
                    results.append({
                        "symbol": sym,
                        "signal": str(r.get("side") or "BUY"),
                        "confidence": conf,
                        "entry_price": float(r.get("entry_price") or 0.0),
                        "exit_price": float(r.get("exit_price") or 0.0),
                        "pnl": pnl,
                        "pnl_pct": pnl_pct,
                        "won": won,
                        "sector": sector,
                        "regime": regime,
                        "entry_hour": entry_hour,
                        "holding_days": int(r.get("holding_days") or 0),
                        "stop_loss_pct": float(r.get("stop_loss_pct") or 0.0),
                        "stop_hit": stop_hit,
                        "target_hit": target_hit,
                        "exit_reason": exit_reason,
                    })
                if results:
                    return results
    except Exception as exc:
        logger.debug("Supabase trades query for learning tracker failed: %s", exc)

    # Tier 3: In-memory signal buffer
    if _IN_MEMORY_SIGNALS:
        return [
            {
                "symbol": s.symbol.upper().split(":")[-1].replace(".NS", "").replace(".BO", ""),
                "signal": s.signal,
                "confidence": s.confidence,
                "entry_price": s.entry_price,
                "exit_price": s.exit_price,
                "pnl": s.pnl,
                "pnl_pct": s.pnl_pct,
                "won": s.won,
                "sector": s.sector or SECTOR_MAP.get(s.symbol.upper(), "Other"),
                "regime": s.regime or "normal",
                "entry_hour": s.entry_hour or 10,
                "holding_days": s.holding_days,
                "stop_loss_pct": s.stop_loss_pct,
                "stop_hit": s.stop_hit,
                "target_hit": s.target_hit,
                "exit_reason": s.exit_reason,
            }
            for s in _IN_MEMORY_SIGNALS
        ]

    return []


# ── Analytics ────────────────────────────────────────────────────────────────


def get_symbol_accuracy(symbol: str) -> dict:
    """Get win rate and stats for a specific symbol."""
    records = _get_all_records()
    clean_sym = symbol.upper().split(":")[-1].replace(".NS", "").replace(".BO", "")
    matches = [r for r in records if r["symbol"].upper() == clean_sym]
    if not matches:
        return {
            "symbol": symbol,
            "total_trades": 0,
            "wins": 0,
            "win_rate": 0.0,
            "avg_pnl": 0.0,
            "avg_pnl_pct": 0.0,
            "avg_confidence": 0.0,
            "avg_holding_days": 0.0,
        }

    total = len(matches)
    wins = sum(1 for r in matches if r["won"])
    avg_pnl = sum(r["pnl"] for r in matches) / total
    avg_pnl_pct = sum(r["pnl_pct"] for r in matches) / total
    avg_conf = sum(r["confidence"] for r in matches) / total
    avg_holding = sum(r["holding_days"] for r in matches) / total

    return {
        "symbol": symbol,
        "total_trades": total,
        "wins": wins,
        "win_rate": round(wins / total * 100, 1),
        "avg_pnl": round(avg_pnl, 2),
        "avg_pnl_pct": round(avg_pnl_pct, 2),
        "avg_confidence": round(avg_conf, 1),
        "avg_holding_days": round(avg_holding, 1),
    }


def get_confidence_calibration() -> list[dict]:
    """Check: when AI says X% confidence, does it win X% of the time?"""
    records = _get_all_records()
    if not records:
        return []

    buckets = {
        "0-40": {"total": 0, "wins": 0, "conf_sum": 0.0},
        "40-55": {"total": 0, "wins": 0, "conf_sum": 0.0},
        "55-70": {"total": 0, "wins": 0, "conf_sum": 0.0},
        "70-85": {"total": 0, "wins": 0, "conf_sum": 0.0},
        "85-100": {"total": 0, "wins": 0, "conf_sum": 0.0},
    }

    for r in records:
        conf = r["confidence"]
        if conf < 40:
            b = "0-40"
        elif conf < 55:
            b = "40-55"
        elif conf < 70:
            b = "55-70"
        elif conf < 85:
            b = "70-85"
        else:
            b = "85-100"

        buckets[b]["total"] += 1
        if r["won"]:
            buckets[b]["wins"] += 1
        buckets[b]["conf_sum"] += conf

    result = []
    for b_name in ["0-40", "40-55", "55-70", "70-85", "85-100"]:
        data = buckets[b_name]
        tot = data["total"]
        if tot == 0:
            continue
        wins = data["wins"]
        actual_win_rate = round(wins / tot * 100, 1)
        stated_conf = round(data["conf_sum"] / tot, 1)
        gap = round(stated_conf - actual_win_rate, 1)
        result.append({
            "confidence_range": b_name,
            "total": tot,
            "wins": wins,
            "actual_win_rate": actual_win_rate,
            "stated_confidence": stated_conf,
            "calibration_gap": gap,
        })
    return result


def get_sector_performance() -> list[dict]:
    """Get performance breakdown by sector."""
    records = _get_all_records()
    if not records:
        return []

    sectors: dict[str, dict] = {}
    for r in records:
        sec = r["sector"]
        if not sec:
            continue
        if sec not in sectors:
            sectors[sec] = {"trades": 0, "wins": 0, "total_pnl": 0.0, "pnl_pct_sum": 0.0}
        sectors[sec]["trades"] += 1
        if r["won"]:
            sectors[sec]["wins"] += 1
        sectors[sec]["total_pnl"] += r["pnl"]
        sectors[sec]["pnl_pct_sum"] += r["pnl_pct"]

    result = []
    for sec, d in sectors.items():
        tr = d["trades"]
        result.append({
            "sector": sec,
            "trades": tr,
            "wins": d["wins"],
            "win_rate": round(d["wins"] / tr * 100, 1) if tr > 0 else 0.0,
            "total_pnl": round(d["total_pnl"], 2),
            "avg_pnl_pct": round(d["pnl_pct_sum"] / tr, 2) if tr > 0 else 0.0,
        })
    result.sort(key=lambda x: x["total_pnl"], reverse=True)
    return result


def get_regime_performance() -> list[dict]:
    """Get performance by market regime."""
    records = _get_all_records()
    if not records:
        return []

    regimes: dict[str, dict] = {}
    for r in records:
        reg = r["regime"]
        if not reg:
            continue
        if reg not in regimes:
            regimes[reg] = {"trades": 0, "wins": 0, "total_pnl": 0.0}
        regimes[reg]["trades"] += 1
        if r["won"]:
            regimes[reg]["wins"] += 1
        regimes[reg]["total_pnl"] += r["pnl"]

    result = []
    for reg, d in regimes.items():
        tr = d["trades"]
        result.append({
            "regime": reg,
            "trades": tr,
            "win_rate": round(d["wins"] / tr * 100, 1) if tr > 0 else 0.0,
            "total_pnl": round(d["total_pnl"], 2),
        })
    result.sort(key=lambda x: x["total_pnl"], reverse=True)
    return result


def get_timing_patterns() -> list[dict]:
    """Get performance by entry hour."""
    records = _get_all_records()
    if not records:
        return []

    hours: dict[int, dict] = {}
    for r in records:
        h = r["entry_hour"]
        if h <= 0:
            continue
        if h not in hours:
            hours[h] = {"trades": 0, "wins": 0, "pnl_pct_sum": 0.0}
        hours[h]["trades"] += 1
        if r["won"]:
            hours[h]["wins"] += 1
        hours[h]["pnl_pct_sum"] += r["pnl_pct"]

    result = []
    for h in sorted(hours.keys()):
        d = hours[h]
        tr = d["trades"]
        result.append({
            "hour": f"{h}:00 IST",
            "trades": tr,
            "win_rate": round(d["wins"] / tr * 100, 1) if tr > 0 else 0.0,
            "avg_pnl_pct": round(d["pnl_pct_sum"] / tr, 2) if tr > 0 else 0.0,
        })
    return result


def get_stop_loss_analysis() -> dict:
    """Analyze stop-loss effectiveness."""
    records = _get_all_records()
    if not records:
        return {
            "stops_hit": 0,
            "total_trades": 0,
            "stop_hit_rate": 0.0,
            "avg_stop_loss": 0.0,
            "avg_win_when_not_stopped": 0.0,
        }

    stops_hit = sum(1 for r in records if r["stop_hit"])
    total = len(records)
    stop_losses = [r["pnl_pct"] for r in records if r["stop_hit"]]
    wins_not_stopped = [r["pnl_pct"] for r in records if not r["stop_hit"] and r["won"]]

    avg_stop = sum(stop_losses) / len(stop_losses) if stop_losses else 0.0
    avg_win = sum(wins_not_stopped) / len(wins_not_stopped) if wins_not_stopped else 0.0

    return {
        "stops_hit": stops_hit,
        "total_trades": total,
        "stop_hit_rate": round(stops_hit / total * 100, 1) if total > 0 else 0.0,
        "avg_stop_loss": round(avg_stop, 2),
        "avg_win_when_not_stopped": round(avg_win, 2),
    }


def generate_learning_insights() -> str:
    """Generate a comprehensive learning report for the AI."""
    try:
        records = _get_all_records()
        if not records:
            return "AI learning engine initialized. Collecting live market observations."

        if len(records) < 3:
            return f"Active trades recorded: {len(records)}. Need at least 3 completed trades to generate statistical insights."

        insights = []

        # Symbol accuracy
        symbols: dict[str, dict] = {}
        for r in records:
            sym = r["symbol"]
            if sym not in symbols:
                symbols[sym] = {"trades": 0, "wins": 0, "pnl_pct_sum": 0.0}
            symbols[sym]["trades"] += 1
            if r["won"]:
                symbols[sym]["wins"] += 1
            symbols[sym]["pnl_pct_sum"] += r["pnl_pct"]

        qualified_symbols = [
            (sym, d["trades"], d["wins"], d["pnl_pct_sum"] / d["trades"])
            for sym, d in symbols.items()
            if d["trades"] >= 3
        ]
        qualified_symbols.sort(key=lambda x: x[3], reverse=True)

        if qualified_symbols:
            best = qualified_symbols[0]
            insights.append(
                f"Best performing: {best[0]} ({best[2]}/{best[1]} wins, {best[3]:+.1f}% avg)"
            )
            if len(qualified_symbols) > 1:
                worst = qualified_symbols[-1]
                insights.append(
                    f"Worst performing: {worst[0]} ({worst[2]}/{worst[1]} wins, {worst[3]:+.1f}% avg)"
                )

        # Confidence calibration
        calibration = get_confidence_calibration()
        for c in calibration:
            if abs(c.get("calibration_gap", 0)) > 15:
                if c["calibration_gap"] > 0:
                    insights.append(
                        f"OVERCONFIDENT in {c['confidence_range']}% range: "
                        f"stated {c['stated_confidence']:.0f}% but actual {c['actual_win_rate']:.0f}%"
                    )
                else:
                    insights.append(
                        f"UNDERCONFIDENT in {c['confidence_range']}% range: "
                        f"stated {c['stated_confidence']:.0f}% but actual {c['actual_win_rate']:.0f}%"
                    )

        # Sector insights
        sectors = get_sector_performance()
        for s in sectors:
            if s.get("trades", 0) >= 3:
                if s.get("win_rate", 0) > 60:
                    insights.append(f"STRONG in {s['sector']}: {s['win_rate']:.0f}% win rate")
                elif s.get("win_rate", 0) < 35:
                    insights.append(f"WEAK in {s['sector']}: {s['win_rate']:.0f}% win rate — avoid")

        # Stop-loss analysis
        sl = get_stop_loss_analysis()
        if sl and sl.get("stop_hit_rate", 0) > 50:
            insights.append(
                f"STOP-LOSS TOO TIGHT: {sl['stop_hit_rate']:.0f}% of trades hit stop. "
                "Consider widening stops."
            )

        return "\n".join(insights) if insights else "AI learning engine initialized. Collecting live market observations."
    except Exception as exc:
        logger.debug("generate_learning_insights failed: %s", exc)
        return "AI learning engine initialized. Collecting live market observations."

