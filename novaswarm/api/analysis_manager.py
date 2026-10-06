"""ThreadPoolExecutor-based background analysis job runner and SSE event dispatcher."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

from novaswarm.api.analysis_models import AnalysisJobStatus, DecisionCard

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AnalysisJob:
    """Represents a running or completed stock analysis job with replayable event stream."""

    def __init__(
        self,
        job_id: str,
        symbol: str,
        trade_date: str,
        asset_class: str,
        urgency: str = "medium",
        lookback_days: int = 30,
        selected_analysts: Optional[List[str]] = None,
    ):
        self.job_id = job_id
        self.symbol = symbol.upper()
        self.trade_date = trade_date
        self.asset_class = asset_class
        self.urgency = urgency
        self.lookback_days = lookback_days
        self.selected_analysts = selected_analysts or ["market", "social", "news", "fundamentals"]
        self.status = "pending"  # pending, running, completed, failed
        self.agent_statuses: Dict[str, str] = {
            "market_analyst": "pending",
            "social_analyst": "pending",
            "news_analyst": "pending",
            "fundamentals_analyst": "pending",
            "bull_researcher": "pending",
            "bear_researcher": "pending",
            "research_manager": "pending",
            "trader": "pending",
            "aggressive_debator": "pending",
            "conservative_debator": "pending",
            "neutral_debator": "pending",
            "risk_judge": "pending",
            "portfolio_manager": "pending",
            "technical_analyst": "pending",
            "sentiment_analyst": "pending",
            "macro_analyst": "pending",
            "valuation_analyst": "pending",
        }
        self.reports: Dict[str, str] = {}
        self.events: List[Dict[str, Any]] = []
        self.decision: Optional[DecisionCard] = None
        self.error: Optional[str] = None
        self.duration_seconds: float = 0.0
        self.subscribers: List[Any] = []
        self.created_at = _utc_now_iso()
        self.updated_at = self.created_at

    def emit_event(
        self,
        event_type: str,
        data: Dict[str, Any],
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        """Thread-safe event emission to replay buffer and connected SSE subscriber queues."""
        timestamp = _utc_now_iso()
        payload = {
            "event": event_type,
            "data": data,
            "timestamp": timestamp,
        }
        self.events.append(payload)
        self.updated_at = timestamp

        if self.subscribers:
            for item in list(self.subscribers):
                try:
                    if isinstance(item, tuple):
                        q, q_loop = item
                        q_loop.call_soon_threadsafe(q.put_nowait, payload)
                    elif loop:
                        loop.call_soon_threadsafe(item.put_nowait, payload)
                except Exception as exc:
                    logger.debug("Failed to dispatch event to queue: %s", exc)

    def to_status(self) -> AnalysisJobStatus:
        """Convert to Pydantic status schema."""
        return AnalysisJobStatus(
            job_id=self.job_id,
            status=self.status,
            symbol=self.symbol,
            trade_date=self.trade_date,
            agent_statuses=self.agent_statuses,
            reports=self.reports,
            decision=self.decision,
            duration_seconds=round(self.duration_seconds, 2),
            error=self.error,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class AnalysisJobManager:
    """Manages analysis jobs and background worker thread pool."""

    _instance: Optional["AnalysisJobManager"] = None

    def __init__(self) -> None:
        self._jobs: Dict[str, AnalysisJob] = {}
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="analysis_worker")

    @classmethod
    def get_instance(cls) -> "AnalysisJobManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (useful for isolated unit testing)."""
        if cls._instance is not None:
            cls._instance._executor.shutdown(wait=False)
            cls._instance = None

    def create_job(
        self,
        symbol: str,
        trade_date: str,
        asset_class: str,
        urgency: str = "medium",
        lookback_days: int = 30,
        selected_analysts: Optional[List[str]] = None,
    ) -> AnalysisJob:
        job_id = str(uuid4())
        job = AnalysisJob(
            job_id=job_id,
            symbol=symbol,
            trade_date=trade_date,
            asset_class=asset_class,
            urgency=urgency,
            lookback_days=lookback_days,
            selected_analysts=selected_analysts,
        )
        self._jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[AnalysisJob]:
        return self._jobs.get(job_id)

    def list_jobs(self, limit: int = 20) -> List[AnalysisJob]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)[:limit]


def execute_analysis_worker(
    job: AnalysisJob,
    loop: asyncio.AbstractEventLoop,
    sleep_interval: float = 0.0,
) -> None:
    """Worker function executed inside the ThreadPoolExecutor running real NovaPipeline."""
    start_time = time.time()
    job.status = "running"

    async def _async_run() -> None:
        from novaswarm.config import NovaSwarmConfig
        from novaswarm.llm.client_factory import instantiate_model
        from novaswarm.llm.gateway import ProviderKeyMissingError
        from novaswarm.llm.env_bridge import bridge_env_vars
        from novaswarm.memory.episodic import EpisodicLessonStore
        from novaswarm.orchestration.engine import NovaPipeline

        config = NovaSwarmConfig()
        bridge_env_vars(config)

        # 1. Instantiate LLM
        provider = getattr(config, "llm_provider", "google")
        model = getattr(config, "deep_think_llm", "gemini-flash-lite-latest")
        if provider == "google" and model in ("gemini-2.0-flash", "gemini-3.8-flash", "gemini-flash-latest"):
            model = "gemini-flash-lite-latest"
        base_url = getattr(config, "backend_url", None)

        try:
            llm = instantiate_model(
                provider=provider,
                model=model,
                base_url=base_url,
                allow_fallback=True,
                fallback_provider="google",
                fallback_model="gemini-3.1-flash-lite",
            )
        except (ProviderKeyMissingError, Exception) as exc:
            err_msg = (
                f"LLM initialization failed ({exc}). "
                "Please configure a valid provider key (e.g. GEMINI_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY)."
            )
            logger.error("Analysis worker LLM setup failed for %s: %s", job.symbol, err_msg)
            job.status = "failed"
            job.error = err_msg
            job.duration_seconds = round(time.time() - start_time, 2)
            job.emit_event(
                "job_failed",
                {
                    "job_id": job.job_id,
                    "error": err_msg,
                    "timestamp": _utc_now_iso(),
                },
                loop=loop,
            )
            return

        # 2. Instantiate episodic memory & pipeline
        risk_memory = EpisodicLessonStore("risk_manager_memory")
        pipeline = NovaPipeline(
            llm_client=llm,
            memory_store=risk_memory,
            max_debate_rounds=1,
            max_risk_rounds=1,
            config={
                "asset_class": job.asset_class,
                "lookback_days": job.lookback_days,
                "urgency": job.urgency,
                "portfolio_equity": getattr(config, "initial_paper_capital", 100000.0),
            },
        )

        legacy_map = {
            "technical_analyst": "market_analyst",
            "sentiment_analyst": "social_analyst",
            "macro_analyst": "news_analyst",
            "valuation_analyst": "fundamentals_analyst",
        }

        # 3. Stream pipeline events
        async for event in pipeline.stream(
            symbol=job.symbol,
            trade_date=job.trade_date,
            selected_analysts=job.selected_analysts,
            asset_class=job.asset_class,
            urgency=job.urgency,
            lookback_days=job.lookback_days,
            job_id=job.job_id,
        ):
            event_type = event.get("event", "")
            data = event.get("data", {})

            # Update job state
            if event_type == "agent_status":
                agent_id = data.get("agent_id")
                status = data.get("status", "running")
                if agent_id:
                    job.agent_statuses[agent_id] = status
                    if agent_id in legacy_map:
                        job.agent_statuses[legacy_map[agent_id]] = status
            elif event_type == "agent_report":
                agent_id = data.get("agent_id")
                report_md = data.get("report_markdown", "")
                if agent_id:
                    job.reports[agent_id] = report_md
                    if agent_id in legacy_map:
                        job.reports[legacy_map[agent_id]] = report_md
            elif event_type == "decision_card":
                try:
                    job.decision = DecisionCard(**data)
                except Exception as card_exc:
                    logger.debug("Error parsing DecisionCard in worker: %s", card_exc)
            elif event_type == "job_completed":
                job.status = "completed"
                job.duration_seconds = float(data.get("duration_seconds", round(time.time() - start_time, 2)))
            elif event_type == "job_failed":
                job.status = "failed"
                job.error = data.get("error", "Analysis failed")
                job.duration_seconds = round(time.time() - start_time, 2)

            # Dispatch event to connected SSE subscribers
            job.emit_event(event_type, data, loop=loop)

    try:
        asyncio.run(_async_run())
    except Exception as exc:
        logger.exception("Analysis worker failed for job %s: %s", job.job_id, exc)
        job.status = "failed"
        job.error = str(exc)
        job.duration_seconds = round(time.time() - start_time, 2)
        job.emit_event(
            "job_failed",
            {
                "job_id": job.job_id,
                "error": str(exc),
                "timestamp": _utc_now_iso(),
            },
            loop=loop,
        )
