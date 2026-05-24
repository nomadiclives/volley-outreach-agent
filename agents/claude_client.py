"""
Central Claude API wrapper — all calls go through here.
Tracks token usage and enforces monthly cost limits.
"""

import logging
import anthropic
from core.database import log_api_usage, get_monthly_claude_cost

logger = logging.getLogger(__name__)
_client: anthropic.Anthropic = None


def _get_client(config: dict) -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config["claude"]["api_key"])
    return _client


def claude_call(
    system_prompt: str,
    user_prompt: str,
    purpose: str,
    config: dict,
    max_tokens: int = None,
) -> str:
    """
    Make a Claude API call with cost tracking and budget enforcement.

    purpose: label for analytics e.g. 'icp_analysis', 'copywriting', 'reply_classification'
    Returns the text content of the response.
    Raises if monthly budget exceeded.
    """
    monthly_cost = get_monthly_claude_cost()
    soft_limit = config["claude"].get("monthly_cost_limit_usd", 4.00)

    if monthly_cost >= soft_limit:
        raise RuntimeError(
            f"Claude API soft limit reached: ${monthly_cost:.2f} of ${soft_limit:.2f} used this month. "
            f"Update claude.monthly_cost_limit_usd in config.yaml to continue."
        )

    client = _get_client(config)
    model = config["claude"]["model"]
    max_tok = max_tokens or config["claude"].get("max_tokens", 2000)

    response = client.messages.create(
        model=model,
        max_tokens=max_tok,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    # Haiku pricing: $0.80/M input, $4.00/M output
    cost_usd = (input_tokens * 0.0000008) + (output_tokens * 0.000004)

    log_api_usage(
        provider="anthropic",
        model=model,
        purpose=purpose,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
    )

    logger.debug(
        "Claude [%s] purpose=%s tokens=%d+%d cost=$%.4f",
        model, purpose, input_tokens, output_tokens, cost_usd,
    )

    return response.content[0].text
