"""FastAPI router for system configuration, model tiering, strategy DNA, and self-healing logs."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from novaswarm import __version__
from novaswarm.api.db_utils import get_safe_supabase
from novaswarm.config import NovaSwarmConfig
from novaswarm.db.models import HealingEventRecord
from novaswarm.db.repositories import HealingRepository, StrategyRepository
from novaswarm.llm.model_tier import _ROLE_PREFERENCES

logger = logging.getLogger(__name__)


def _sec(val) -> str:
    """Safely extract string value from a SecretStr, str, or None."""
    if val is None:
        return ""
    if hasattr(val, "get_secret_value"):
        return val.get_secret_value()
    return str(val)


router = APIRouter(prefix="/api/system", tags=["system"])

DEFAULT_DNA_YAML = """\
version: v1.0.0
strategy_name: NovaSwarmMultiAgentTrendBreakout
asset_class: equity
exchange: NSE
parameters:
  atr_multiplier: 2.0
  atr_period: 14
  risk_per_trade_pct: 0.01
  max_positions: 5
  max_debate_rounds: 1
  max_risk_rounds: 1
  min_confidence: 70
  entry_filters:
    - 50_sma_above_200_sma
    - rsi_between_45_and_68
    - macd_bullish_cross
"""


class HealingLogRequest(BaseModel):
    component: str = Field(..., description="System component (e.g. broker, websocket, database, scanner)")
    event_type: str = Field(..., description="Event type (e.g. disconnect, token_refresh, rate_limit)")
    description: Optional[str] = Field(None, description="Detailed description of the issue")
    action_taken: Optional[str] = Field(None, description="Self-healing or corrective action applied")
    resolved: bool = Field(True, description="Whether the event has been resolved")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context metadata")


class HealingLogResponse(BaseModel):
    status: str
    event: Dict[str, Any]


@router.get("/config")
async def get_system_config() -> dict:
    """Safe, sanitized overview of active configuration parameters and secret presence flags."""
    config = NovaSwarmConfig()

    return {
        "version": __version__,
        "environment": os.environ.get("ENVIRONMENT", "development"),
        "trading_mode": config.trading_mode,
        "broker_mode": config.trading_mode,
        "asset_class": config.asset_class,
        "initial_paper_capital": config.initial_paper_capital,
        "risk_per_trade_pct": config.risk_per_trade_pct,
        "atr_multiplier": config.atr_multiplier,
        "atr_period": config.atr_period,
        "scanner": {
            "enabled": config.scanner_enabled,
            "cycle_seconds": config.scanner_cycle_seconds,
            "max_candidates": config.scanner_max_candidates,
        },
        "scanner_intervals": {
            "market_hours_sec": config.scanner_cycle_seconds,
            "off_hours_sec": config.scanner_cycle_seconds * 5,
        },
        "risk_limits": {
            "max_drawdown_pct": 3.0,
            "daily_loss_limit_inr": 30000.0,
            "max_position_size_inr": 250000.0,
            "max_sector_concentration_pct": config.max_sector_concentration_pct * 100,
        },
        "reflection": {
            "enabled": config.reflection_enabled,
            "max_memory_entries": config.reflection_max_memory_entries,
        },
        "services": {
            "supabase": bool(config.supabase_url and _sec(config.supabase_service_key)),
            "redis": bool(config.upstash_redis_url and _sec(config.upstash_redis_token)),
            "google_ai": bool(_sec(config.google_api_key)),
            "anthropic": bool(_sec(config.anthropic_api_key)),
            "perplexity": bool(_sec(config.perplexity_api_key)),
            "xai": bool(_sec(config.xai_api_key)),
            "openrouter": bool(_sec(config.openrouter_api_key)),
            "indstocks": bool(_sec(config.indstocks_token)),
            "kite": bool(config.kite_api_key),
        },
    }


@router.get("/models")
async def get_model_mappings() -> dict:
    """Active LLM role-to-model tiering, provider configuration status, and fallback chains."""
    config = NovaSwarmConfig()
    role_titles = {
        "market_analyst": "Market Analyst",
        "social_analyst": "Social Media Analyst",
        "news_analyst": "News & Macro Analyst",
        "fundamentals_analyst": "Fundamentals Analyst",
        "bull_researcher": "Bull Researcher",
        "bear_researcher": "Bear Researcher",
        "research_manager": "Research Manager (Judge)",
        "risk_manager": "Risk Manager (Judge)",
        "trader": "Trading Strategy Generator",
        "aggressive_debator": "Aggressive Risk Debater",
        "neutral_debator": "Neutral Risk Debater",
        "conservative_debator": "Conservative Risk Debater",
        "sell_analyst": "Exit & Sell Analyst",
        "chat_brain": "AI Chat Assistant Brain",
    }

    def _has_key(provider: str) -> bool:
        if provider == "google":
            return bool(_sec(config.google_api_key) or os.environ.get("GOOGLE_API_KEY"))
        if provider == "anthropic":
            return bool(_sec(config.anthropic_api_key) or os.environ.get("ANTHROPIC_API_KEY"))
        if provider == "xai":
            return bool(_sec(config.xai_api_key) or os.environ.get("XAI_API_KEY"))
        if provider == "openrouter":
            return bool(_sec(config.openrouter_api_key) or os.environ.get("OPENROUTER_API_KEY"))
        if provider == "perplexity":
            return bool(_sec(config.perplexity_api_key) or os.environ.get("PERPLEXITY_API_KEY"))
        if provider == "ollama":
            return os.environ.get("NOVASWARM_OLLAMA_ENABLED", "").lower() in ("1", "true", "yes")
        return False

    roles_list = []
    for role, prefs in _ROLE_PREFERENCES.items():
        primary_provider, primary_model = prefs[0]
        fallback_provider, fallback_model = prefs[1] if len(prefs) > 1 else (None, None)

        primary_configured = _has_key(primary_provider)
        status = "configured" if primary_configured else ("fallback" if fallback_provider and _has_key(fallback_provider) else "unconfigured")

        roles_list.append({
            "role": role,
            "name": role_titles.get(role, role.replace("_", " ").title()),
            "primary_model": primary_model,
            "primary_provider": primary_provider,
            "fallback_model": fallback_model,
            "fallback_provider": fallback_provider,
            "status": status,
            "primary_configured": primary_configured,
        })

    return {
        "roles": roles_list,
        "total_roles": len(roles_list),
    }


@router.get("/strategies")
async def get_strategies() -> dict:
    """Active Strategy DNA version, historical evolutions, and base parameter YAML."""
    client = get_safe_supabase()
    active_strat = None
    history: List[dict] = []

    if client:
        try:
            repo = StrategyRepository(client)
            active_strat = repo.get_active()
            raw_history = repo.get_history(limit=20)
            history = [s.model_dump(mode="json") for s in raw_history]
        except Exception as exc:
            logger.warning("Error fetching strategies from DB: %s", exc)

    return {
        "active_strategy": active_strat.model_dump(mode="json") if active_strat else None,
        "history": history,
        "dna_yaml": active_strat.dna_yaml if active_strat else DEFAULT_DNA_YAML,
    }


@router.get("/healing")
async def get_healing_events(
    limit: int = Query(50, ge=1, le=200),
    component: Optional[str] = None,
) -> dict:
    """Log of automated self-healing events (broker reconnects, token refreshes, rate-limit recovery)."""
    client = get_safe_supabase()
    if not client:
        return {"events": [], "unresolved_count": 0}

    try:
        repo = HealingRepository(client)
        events = repo.get_recent(limit=limit, component=component)
        unresolved = repo.get_unresolved()
        return {
            "events": [e.model_dump(mode="json") for e in events],
            "unresolved_count": len(unresolved),
        }
    except Exception as exc:
        logger.warning("Error fetching healing events: %s", exc)
        return {"events": [], "unresolved_count": 0}


@router.post("/healing/log", response_model=HealingLogResponse)
async def log_healing_event(req: HealingLogRequest) -> HealingLogResponse:
    """Record an external or manual self-healing event in the infrastructure audit log."""
    client = get_safe_supabase()
    record_dict = {
        "component": req.component,
        "event_type": req.event_type,
        "description": req.description,
        "action_taken": req.action_taken,
        "resolved": req.resolved,
        "metadata": req.metadata,
    }

    if client:
        try:
            repo = HealingRepository(client)
            record = HealingEventRecord(**record_dict)
            saved = repo.insert(record)
            return HealingLogResponse(status="success", event=saved.model_dump(mode="json"))
        except Exception as exc:
            logger.warning("Error logging healing event to DB: %s", exc)

    return HealingLogResponse(status="acknowledged_in_memory", event=record_dict)
