#!/bin/bash
# OpenClaw skill: Get real-time stock quote
# Usage: quote.sh RELIANCE
set -e
cd "$(dirname "$0")/../.."
python3 -c "
import asyncio, sys
from novaswarm.config import NovaSwarmConfig
from novaswarm.chat.session import build_infrastructure
from novaswarm.chat.tools import init_tools, get_quote

async def main():
    config = NovaSwarmConfig()
    infra = build_infrastructure(config)
    init_tools(infra)
    result = await get_quote.ainvoke({'symbol': sys.argv[1]})
    print(result)

asyncio.run(main())
" "$1"
