"""Unit tests for the native INDstocks data provider (skopaq.data.indstocks).

Tests:
- Async-to-sync runner bridge (_run_async)
- Provider instantiation and token validation
- Custom error hierarchy
"""

from __future__ import annotations

import pytest

from skopaq.data.indstocks import (
    INDstocksError,
    INDstocksAuthError,
    INDstocksSymbolNotFoundError,
    INDstocksDataProvider,
    _run_async,
)


class TestRunAsyncBridge:
    def test_run_async_executes_coroutine(self):
        async def simple_coro():
            return 42

        result = _run_async(simple_coro())
        assert result == 42

    def test_run_async_propagates_exception(self):
        async def failing_coro():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            _run_async(failing_coro())


class TestINDstocksDataProvider:
    def test_provider_init(self):
        provider = INDstocksDataProvider()
        assert provider is not None

    def test_error_hierarchy(self):
        assert issubclass(INDstocksAuthError, INDstocksError)
        assert issubclass(INDstocksSymbolNotFoundError, INDstocksError)
