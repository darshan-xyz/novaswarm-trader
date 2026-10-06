"""FastAPI router for agent BM25 memory stores and post-trade reflections."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from novaswarm.api.db_utils import get_safe_supabase
from novaswarm.db.repositories import MemoryRepository
from novaswarm.memory.reflection import load_recent_lessons, recall

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/memory", tags=["memory"])

CANONICAL_ROLES = [
    {"role": "bull_memory", "name": "Bullish Analyst Memory"},
    {"role": "bear_memory", "name": "Bearish Analyst Memory"},
    {"role": "trader_memory", "name": "Trading Execution Memory"},
    {"role": "invest_judge_memory", "name": "Investment Judge Memory"},
    {"role": "risk_manager_memory", "name": "Risk Management Memory"},
]


class MemoryQueryRequest(BaseModel):
    role: str = Field(..., description="Role memory store to query (e.g. bull_memory, risk_manager_memory)")
    query: str = Field(..., min_length=1, description="Search query string")
    top_k: int = Field(3, ge=1, le=20, description="Maximum number of relevant results")


class MemoryQueryResult(BaseModel):
    matched_situation: str
    recommendation: str
    similarity_score: float


class MemoryQueryResponse(BaseModel):
    query: str
    role: str
    results: List[MemoryQueryResult]


@router.get("/roles")
async def list_roles() -> dict:
    """List the 5 canonical agent memory stores, document counts, and last update timestamps."""
    client = get_safe_supabase()
    role_records: Dict[str, Any] = {}

    if client:
        try:
            repo = MemoryRepository(client)
            all_records = repo.get_all_roles()
            for r in all_records:
                role_records[r.role] = r
        except Exception as exc:
            logger.warning("Error fetching memory roles from Supabase: %s", exc)

    roles_data = []
    total_memories = 0

    for info in CANONICAL_ROLES:
        role_key = info["role"]
        record = role_records.get(role_key)
        count = len(record.documents) if record and record.documents else 0
        total_memories += count
        updated_at = record.updated_at.isoformat() if record and record.updated_at else None

        roles_data.append({
            "role": role_key,
            "name": info["name"],
            "count": count,
            "updated_at": updated_at,
        })

    return {
        "roles": roles_data,
        "total_memories": total_memories,
    }


@router.get("/role/{role}")
async def get_role_memories(
    role: str,
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    """Fetch stored situations and recommended actions for a specific agent role."""
    client = get_safe_supabase()
    if not client:
        return {"role": role, "entries": [], "count": 0}

    try:
        repo = MemoryRepository(client)
        rec = repo.get_by_role(role)
        if not rec or not rec.documents:
            return {"role": role, "entries": [], "count": 0}

        entries = []
        for doc, rec_act in zip(rec.documents[:limit], rec.recommendations[:limit]):
            entries.append({"situation": doc, "recommendation": rec_act})

        return {
            "role": role,
            "entries": entries,
            "count": len(entries),
        }
    except Exception as exc:
        logger.warning("Error fetching memory for role %s: %s", role, exc)
        return {"role": role, "entries": [], "count": 0}


@router.post("/query", response_model=MemoryQueryResponse)
async def query_memory(req: MemoryQueryRequest) -> MemoryQueryResponse:
    """Run BM25 search over an agent role's stored situation-recommendation pairs."""
    client = get_safe_supabase()
    if not client:
        return MemoryQueryResponse(query=req.query, role=req.role, results=[])

    try:
        repo = MemoryRepository(client)
        rec = repo.get_by_role(req.role)
        if not rec or not rec.documents:
            return MemoryQueryResponse(query=req.query, role=req.role, results=[])

        try:
            from novaswarm.memory.episodic import EpisodicLessonStore

            store = EpisodicLessonStore()
            store.set_memories(list(rec.documents), list(rec.recommendations))

            matches = store.get_memories(
                current_situation=req.query,
                n_matches=req.top_k,
                recency_weight=0.0,
                min_lexical_overlap=True,
            )

            results = []
            for match in matches:
                results.append(
                    MemoryQueryResult(
                        matched_situation=match.matched_situation,
                        recommendation=match.recommendation,
                        similarity_score=round(match.similarity_score, 4),
                    )
                )

            return MemoryQueryResponse(query=req.query, role=req.role, results=results)

        except Exception as bm_exc:
            logger.warning("BM25 scoring failed, falling back to substring match: %s", bm_exc)
            # Fallback simple substring scoring
            q_lower = req.query.lower()
            results = []
            for idx, doc in enumerate(rec.documents):
                if q_lower in doc.lower():
                    recommendation = rec.recommendations[idx] if idx < len(rec.recommendations) else ""
                    results.append(
                        MemoryQueryResult(
                            matched_situation=doc,
                            recommendation=recommendation,
                            similarity_score=1.0,
                        )
                    )
                    if len(results) >= req.top_k:
                        break
            return MemoryQueryResponse(query=req.query, role=req.role, results=results)

    except Exception as exc:
        logger.warning("Error querying memory for role %s: %s", req.role, exc)
        return MemoryQueryResponse(query=req.query, role=req.role, results=[])


@router.get("/reflections")
async def list_reflections(
    query: Optional[str] = None,
    symbol: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    """Retrieve post-trade reflections generated by closed trades."""
    client = get_safe_supabase()
    if not client:
        return {"reflections": [], "count": 0}

    try:
        if query:
            records = recall(client, query=query, limit=limit)
        else:
            records = load_recent_lessons(client, limit=limit)

        if symbol:
            records = [r for r in records if r.get("symbol", "").upper() == symbol.strip().upper()]

        return {
            "reflections": records,
            "count": len(records),
        }
    except Exception as exc:
        logger.warning("Error fetching reflections: %s", exc)
        return {"reflections": [], "count": 0}
