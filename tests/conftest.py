"""Shared test fixtures."""

import os

import pytest

# Ensure tests don't accidentally use real credentials
os.environ.setdefault("NOVASWARM_TRADING_MODE", "paper")
os.environ.setdefault("NOVASWARM_SUPABASE_URL", "")
os.environ.setdefault("NOVASWARM_SUPABASE_SERVICE_KEY", "")
