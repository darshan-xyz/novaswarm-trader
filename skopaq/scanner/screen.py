"""LLM-based screening — multi-model prompts for candidate selection.

Supports three screening modes:

- **technical** (Gemini Flash): Price/volume metrics analysis
- **news** (Perplexity Sonar): Breaking news and event-driven signals
- **social** (Grok): Social media sentiment and retail buzz

Each mode produces ``ScannerCandidate`` objects with a ``source`` tag in
the metrics dict so downstream systems know which model flagged it.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from skopaq.scanner.models import ScannerCandidate, ScannerMetrics

logger = logging.getLogger(__name__)

# ── Prompt Templates ──────────────────────────────────────────────────

SCREEN_PROMPT_TEMPLATE = """\
You are a stock screener for the Indian equity market (NSE).
Analyze the following NIFTY stocks and identify up to {max_candidates} \
candidates that show the strongest trading signals RIGHT NOW.

For each candidate, provide:
- symbol: the stock symbol
- reason: one-line explanation (max 100 chars)
- urgency: "high" or "normal"

Return ONLY valid JSON — an array of objects.  No markdown, no explanation.
If no stocks are interesting, return an empty array [].

Current market metrics:
{metrics_table}

Respond with JSON only:
"""

NEWS_SCREEN_PROMPT_TEMPLATE = """\
You are a financial news analyst for the Indian equity market (NSE).
For the stocks below, identify up to {max_candidates} that have \
ACTIONABLE breaking news, earnings surprises, regulatory changes, \
or event-driven catalysts happening RIGHT NOW or in the last 24 hours.

For each candidate, provide:
- symbol: the stock symbol
- reason: one-line explanation of the NEWS event (max 100 chars)
- urgency: "high" if event is breaking/imminent, "normal" otherwise

Return ONLY valid JSON — an array of objects.  No markdown, no explanation.
If no stocks have newsworthy events, return an empty array [].

Stocks to check: {symbols}

Respond with JSON only:
"""

SOCIAL_SCREEN_PROMPT_TEMPLATE = """\
You are a social media sentiment analyst for the Indian equity market (NSE).
For the stocks below, identify up to {max_candidates} that show \
unusual social media activity, retail sentiment shifts, or trending \
discussions on Twitter/X, Reddit, or financial forums.

For each candidate, provide:
- symbol: the stock symbol
- reason: one-line explanation of the SOCIAL signal (max 100 chars)
- urgency: "high" if momentum is accelerating, "normal" otherwise

Return ONLY valid JSON — an array of objects.  No markdown, no explanation.
If no stocks have notable social signals, return an empty array [].

Stocks to check: {symbols}

Respond with JSON only:
"""


def format_metrics_table(metrics_list: list[ScannerMetrics]) -> str:
    """Format scanner metrics as a compact table for the LLM prompt."""
    lines = ["Symbol      | Change% | VolRatio | Gap%"]
    lines.append("-" * 45)
    for m in metrics_list:
        lines.append(
            f"{m.symbol:<12}| {m.change_pct:>+6.2f}% | {m.volume_ratio:>7.1f}x | {m.gap_pct:>+5.2f}%"
        )
    return "\n".join(lines)


def build_screen_prompt(
    metrics_list: list[ScannerMetrics],
    max_candidates: int = 5,
) -> str:
    """Build the technical screening prompt from a list of metrics."""
    table = format_metrics_table(metrics_list)
    return SCREEN_PROMPT_TEMPLATE.format(
        max_candidates=max_candidates,
        metrics_table=table,
    )


def build_news_prompt(
    symbols: list[str],
    max_candidates: int = 3,
) -> str:
    """Build a news-aware screening prompt for Perplexity Sonar.

    Perplexity Sonar is web-grounded — it can search the web in real time
    to find breaking news and event-driven catalysts.
    """
    return NEWS_SCREEN_PROMPT_TEMPLATE.format(
        max_candidates=max_candidates,
        symbols=", ".join(symbols),
    )


def build_social_prompt(
    symbols: list[str],
    max_candidates: int = 3,
) -> str:
    """Build a social sentiment screening prompt for Grok.

    Grok is used for social sentiment analysis — it excels at detecting
    retail sentiment shifts and trending discussions about stocks.
    """
    return SOCIAL_SCREEN_PROMPT_TEMPLATE.format(
        max_candidates=max_candidates,
        symbols=", ".join(symbols),
    )


def _try_parse_json(text: str) -> Any:
    """Try to parse JSON, recovering from common LLM truncation issues.

    Attempts in order:
    1. Direct parse
    2. Strip trailing commas before ] or }
    3. Extract JSON array between [ and ]
    4. Close truncated array/objects by appending missing brackets
    """
    text = text.strip()

    # 1. Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Strip trailing commas (common LLM quirk)
    cleaned = re.sub(r",\s*([}\]])", r"\1", text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 3. Find bracket range if embedded in text
    start_bracket = cleaned.find("[")
    if start_bracket != -1:
        bracketed = cleaned[start_bracket:]
        try:
            return json.loads(bracketed)
        except json.JSONDecodeError:
            pass

        # 4. Truncated response — try closing brackets on complete objects
        depth = 0
        last_complete = -1
        for i, ch in enumerate(bracketed):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    last_complete = i

        if last_complete > 0:
            truncated = bracketed[: last_complete + 1] + "]"
            try:
                return json.loads(truncated)
            except json.JSONDecodeError:
                pass

    return None


def parse_screen_response(response_text: str) -> list[ScannerCandidate]:
    """Parse the LLM JSON response into ScannerCandidate objects.

    Handles common LLM quirks: markdown code fences, trailing commas,
    extra whitespace, preambles, and **truncated responses** (cuts off mid-JSON).
    """
    text = response_text.strip()

    # Strip markdown code fence if present
    code_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if code_match:
        text = code_match.group(1).strip()
    elif text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(
            line for line in lines
            if not line.strip().startswith("```")
        ).strip()

    data = _try_parse_json(text)
    if data is None:
        logger.warning("Failed to parse scanner LLM response: %s", text[:200])
        return []

    if not isinstance(data, list):
        logger.warning("Scanner LLM response is not a list: %s", type(data))
        return []

    candidates = []
    for item in data:
        if not isinstance(item, dict):
            continue
        symbol = item.get("symbol", "")
        reason = item.get("reason", "")
        if not symbol:
            continue
        candidates.append(
            ScannerCandidate(
                symbol=symbol.upper(),
                reason=reason[:200],
                urgency=item.get("urgency", "normal"),
                metrics=item.get("metrics", {}),
            )
        )

    return candidates
