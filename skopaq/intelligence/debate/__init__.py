"""Skopaq Intelligence: Adversarial Debate.

Stage 2 adversarial thesis debate modules between Upside Advocate, Downside Advocate,
and Thesis Adjudicator.
"""

from skopaq.intelligence.debate.adjudicator import (
    THESIS_ADJUDICATOR_PROMPT,
    THESIS_ADJUDICATOR_SYSTEM_PROMPT,
)
from skopaq.intelligence.debate.advocate import (
    DOWNSIDE_ADVOCATE_PROMPT,
    DOWNSIDE_ADVOCATE_SYSTEM_PROMPT,
    UPSIDE_ADVOCATE_PROMPT,
    UPSIDE_ADVOCATE_SYSTEM_PROMPT,
)

__all__ = [
    "UPSIDE_ADVOCATE_PROMPT",
    "UPSIDE_ADVOCATE_SYSTEM_PROMPT",
    "DOWNSIDE_ADVOCATE_PROMPT",
    "DOWNSIDE_ADVOCATE_SYSTEM_PROMPT",
    "THESIS_ADJUDICATOR_PROMPT",
    "THESIS_ADJUDICATOR_SYSTEM_PROMPT",
]
