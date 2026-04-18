"""Token counter and cost estimator for the Claude API.

Wraps Anthropic's /v1/messages/count_tokens endpoint so you can
pre-flight every request: know the token count and dollar cost
BEFORE you burn rate-limit budget or get an oversize-context error.

Usage:
    from token_counter import count_tokens, estimate_cost, check_fits

    tokens = count_tokens(messages, model="claude-sonnet-4-5")
    cost = estimate_cost(input_tokens=tokens, output_tokens=500,
                         model="claude-sonnet-4-5")
    ok, reason = check_fits(tokens, model="claude-sonnet-4-5")
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

try:
    import anthropic  # type: ignore[import-not-found]
except ImportError as _exc:  # pragma: no cover
    anthropic = None
    _IMPORT_ERR = _exc
else:
    _IMPORT_ERR = None


# Per-million-token pricing in USD. Keep in sync with
# https://www.anthropic.com/pricing
PRICING: Dict[str, Dict[str, float]] = {
    "claude-opus-4-5":    {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-5":  {"input":  3.00, "output": 15.00},
    "claude-haiku-4-5":   {"input":  0.80, "output":  4.00},
    "claude-3-5-sonnet":  {"input":  3.00, "output": 15.00},
    "claude-3-5-haiku":   {"input":  0.80, "output":  4.00},
}

# Context window sizes in tokens.
CONTEXT_WINDOW: Dict[str, int] = {
    "claude-opus-4-5":    200_000,
    "claude-sonnet-4-5":  200_000,
    "claude-haiku-4-5":   200_000,
    "claude-3-5-sonnet":  200_000,
    "claude-3-5-haiku":   200_000,
}


@dataclass(frozen=True)
class CostBreakdown:
    input_cost_usd: float
    output_cost_usd: float
    total_usd: float


def _client() -> "anthropic.Anthropic":
    if anthropic is None:
        raise RuntimeError(
            f"anthropic package not installed: {_IMPORT_ERR}. "
            "Install with: pip install anthropic"
        )
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set")
    return anthropic.Anthropic(api_key=api_key)


def _resolve_model_key(model: str) -> str:
    """Map a full model string (e.g. 'claude-sonnet-4-5-20250929')
    to its pricing-table key."""
    for key in PRICING:
        if model.startswith(key):
            return key
    raise KeyError(f"Unknown model for pricing: {model!r}")


def count_tokens(
    messages: List[Dict[str, Any]],
    model: str,
    system: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
) -> int:
    """Return the input token count for a Claude API request.

    Uses Anthropic's server-side token counter — the authoritative source.
    """
    client = _client()
    kwargs: Dict[str, Any] = {"model": model, "messages": messages}
    if system is not None:
        kwargs["system"] = system
    if tools is not None:
        kwargs["tools"] = tools
    result = client.messages.count_tokens(**kwargs)
    return int(result.input_tokens)


def estimate_cost(
    input_tokens: int,
    output_tokens: int,
    model: str,
) -> CostBreakdown:
    """Estimate USD cost for a request. Output tokens are typically
    unknown up front — pass your max_tokens ceiling for worst case."""
    key = _resolve_model_key(model)
    rates = PRICING[key]
    input_cost = (input_tokens / 1_000_000) * rates["input"]
    output_cost = (output_tokens / 1_000_000) * rates["output"]
    return CostBreakdown(
        input_cost_usd=round(input_cost, 6),
        output_cost_usd=round(output_cost, 6),
        total_usd=round(input_cost + output_cost, 6),
    )


def check_fits(
    input_tokens: int,
    model: str,
    max_output_tokens: int = 4096,
) -> Tuple[bool, str]:
    """Confirm the request fits the model's context window.

    Returns (ok, reason) where reason is empty on success.
    """
    key = _resolve_model_key(model)
    window = CONTEXT_WINDOW[key]
    needed = input_tokens + max_output_tokens
    if needed <= window:
        return True, ""
    return False, (
        f"request needs {needed:,} tokens but {model} has a "
        f"{window:,}-token window (overflow: {needed - window:,})"
    )


__all__ = [
    "CostBreakdown",
    "PRICING",
    "CONTEXT_WINDOW",
    "count_tokens",
    "estimate_cost",
    "check_fits",
]
