"""NovaSwarm Intelligence: Specialist Analysts.

Stage 1 parallel specialist analyst prompts and intelligence modules.
"""

from novaswarm.intelligence.analysts.derivatives import DERIVATIVES_PROMPT, DERIVATIVES_SYSTEM_PROMPT
from novaswarm.intelligence.analysts.macro import MACRO_PROMPT, MACRO_SYSTEM_PROMPT
from novaswarm.intelligence.analysts.network import NETWORK_PROMPT, NETWORK_SYSTEM_PROMPT
from novaswarm.intelligence.analysts.sentiment import SENTIMENT_PROMPT, SENTIMENT_SYSTEM_PROMPT
from novaswarm.intelligence.analysts.technical import TECHNICAL_PROMPT, TECHNICAL_SYSTEM_PROMPT
from novaswarm.intelligence.analysts.tokenomics import TOKENOMICS_PROMPT, TOKENOMICS_SYSTEM_PROMPT
from novaswarm.intelligence.analysts.valuation import VALUATION_PROMPT, VALUATION_SYSTEM_PROMPT

__all__ = [
    "TECHNICAL_PROMPT",
    "TECHNICAL_SYSTEM_PROMPT",
    "SENTIMENT_PROMPT",
    "SENTIMENT_SYSTEM_PROMPT",
    "MACRO_PROMPT",
    "MACRO_SYSTEM_PROMPT",
    "VALUATION_PROMPT",
    "VALUATION_SYSTEM_PROMPT",
    "NETWORK_PROMPT",
    "NETWORK_SYSTEM_PROMPT",
    "TOKENOMICS_PROMPT",
    "TOKENOMICS_SYSTEM_PROMPT",
    "DERIVATIVES_PROMPT",
    "DERIVATIVES_SYSTEM_PROMPT",
]
