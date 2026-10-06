"""Supabase client singleton.

Initializes the Supabase Python client once and provides it to the rest
of the application.  Uses the service_role key for backend operations
(bypasses RLS), which is appropriate since the Python backend is trusted.
"""

from __future__ import annotations

import logging
from typing import Optional

from supabase import Client, create_client

from skopaq.config import SkopaqConfig

logger = logging.getLogger(__name__)

_client: Optional[Client] = None


def _sec(val) -> str:
    """Safely extract string value from a SecretStr, str, or None."""
    if val is None:
        return ""
    if hasattr(val, "get_secret_value"):
        return val.get_secret_value()
    return str(val)


def get_supabase(config: Optional[SkopaqConfig] = None) -> Client:
    """Return the Supabase client singleton.

    On first call, ``config`` must be provided to initialise the client.
    Subsequent calls return the cached instance.
    """
    global _client
    if _client is not None:
        return _client

    if config is None:
        config = SkopaqConfig()

    if not config.supabase_url or not _sec(config.supabase_service_key):
        raise RuntimeError(
            "Supabase not configured. Set SKOPAQ_SUPABASE_URL and "
            "SKOPAQ_SUPABASE_SERVICE_KEY in your .env file."
        )

    _client = create_client(
        config.supabase_url,
        _sec(config.supabase_service_key),
    )
    logger.info("Supabase client initialised (%s)", config.supabase_url)
    return _client


def reset_client() -> None:
    """Reset the cached client (useful for testing)."""
    global _client
    _client = None
