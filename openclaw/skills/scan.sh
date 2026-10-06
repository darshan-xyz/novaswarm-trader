#!/bin/bash
# OpenClaw skill: Scan market for trading candidates
# Usage: scan.sh
set -e
cd "$(dirname "$0")/../.."
python3 -c "
import asyncio
from novaswarm.config import NovaSwarmConfig
from novaswarm.chat.session import build_infrastructure
from novaswarm.chat.tools import init_tools, scan_market

async def main():
    config = NovaSwarmConfig()
    infra = build_infrastructure(config)
    init_tools(infra)
    result = await scan_market.ainvoke({'max_candidates': 5})
    print(result)

asyncio.run(main())
"
