"""Pytest configuration and fixtures for SkopaqTrader E2E tests."""

from __future__ import annotations

import pytest

from tests.e2e.client import E2EClient


def pytest_addoption(parser):
    """Register CLI flags for E2E testing."""
    parser.addoption(
        "--mode",
        action="store",
        default="mock",
        help="E2E execution mode: 'mock' (default in-process) or 'live' (network)",
    )
    parser.addoption(
        "--backend-url",
        action="store",
        default="http://localhost:8000",
        help="Base URL for backend REST/SSE API (used in live mode)",
    )
    parser.addoption(
        "--frontend-url",
        action="store",
        default="http://localhost:3000",
        help="Base URL for frontend Next.js server (used in live mode)",
    )
    parser.addoption(
        "--e2e-timeout",
        action="store",
        default=30.0,
        type=float,
        help="Per-request/stream timeout in seconds",
    )


@pytest.fixture(scope="session")
def e2e_mode(request) -> str:
    return request.config.getoption("--mode")


@pytest.fixture(scope="session")
def backend_url(request) -> str:
    return request.config.getoption("--backend-url")


@pytest.fixture(scope="session")
def frontend_url(request) -> str:
    return request.config.getoption("--frontend-url")


@pytest.fixture(scope="session")
def e2e_timeout(request) -> float:
    return request.config.getoption("--e2e-timeout")


@pytest.fixture
def client(e2e_mode, backend_url, frontend_url, e2e_timeout):
    """Fixture providing an isolated E2EClient per test."""
    e2e_client = E2EClient(
        mode=e2e_mode,
        backend_url=backend_url,
        frontend_url=frontend_url,
        timeout=e2e_timeout,
    )
    try:
        yield e2e_client
    finally:
        e2e_client.close()
