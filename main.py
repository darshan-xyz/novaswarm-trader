"""SkopaqTrader — Institutional Quantitative AI Multi-Agent Platform for Indian Equities.

Usage:
    python main.py analyze RELIANCE
    python main.py scan
    python main.py trade RELIANCE --shares 10
    python main.py serve
    python main.py chat
"""

from __future__ import annotations

import sys
from skopaq.cli.main import app

if __name__ == "__main__":
    app()
