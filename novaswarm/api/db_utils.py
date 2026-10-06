"""Database utilities and resilient Supabase connection helper for API routers."""

from __future__ import annotations

import logging
from typing import Optional
from supabase import Client

logger = logging.getLogger(__name__)


def get_safe_supabase() -> Optional[Client]:
    """Retrieve Supabase client singleton or return None if unconfigured or unreachable.

    Ensures API endpoints degrade gracefully without throwing 500 errors when
    running in local-only / offline environments without Supabase credentials.
    """
    try:
        from novaswarm.db.client import get_supabase
        return get_supabase()
    except Exception as exc:
        logger.debug("Supabase not available: %s", exc)
        return None
