"""Centralised credit gate for all API sources.

Every integration must call CreditManager.check_and_spend(provider) before
each API call. This is the single credit gate — never implement per-integration
credit checks independently.
"""

import logging
from core.database import log_api_usage, get_monthly_api_credits

logger = logging.getLogger(__name__)

# Maps provider name → (config section, config key) for monthly limits
_LIMIT_KEYS: dict[str, tuple[str, str]] = {
    "apollo":      ("apollo",      "monthly_credit_limit"),
    "hunter":      ("hunter",      "monthly_search_limit"),
    "lusha":       ("lusha",       "monthly_credit_limit"),
    "snov":        ("snov",        "monthly_credit_limit"),
    "getprospect": ("getprospect", "monthly_credit_limit"),
}

_DEFAULT_LIMITS: dict[str, int] = {
    "apollo":      75,
    "hunter":      50,
    "lusha":       40,
    "snov":        50,
    "getprospect": 50,
}


class CreditLimitReached(Exception):
    """Raised when a provider's monthly credit limit would be exceeded."""


class CreditManager:
    """Single gate for all API credit checks and spend logging.

    Usage in integrations:
        self.credits.check_and_spend("lusha", purpose="contact_resolution")
        # make the API call
    """

    def __init__(self, config: dict):
        self.config = config

    def get_limit(self, provider: str) -> int:
        """Return the configured monthly credit limit for a provider."""
        section, key = _LIMIT_KEYS.get(provider, (provider, "monthly_credit_limit"))
        return int(
            self.config.get(section, {}).get(key, _DEFAULT_LIMITS.get(provider, 0))
        )

    def get_used(self, provider: str) -> int:
        """Return credits consumed by provider in the current calendar month."""
        return get_monthly_api_credits(provider)

    def get_remaining(self, provider: str) -> int:
        """Return credits still available for provider this month."""
        return max(0, self.get_limit(provider) - self.get_used(provider))

    def check_and_spend(
        self,
        provider: str,
        cost: int = 1,
        purpose: str = "api_call",
    ) -> None:
        """Gate every API call through this method.

        Raises CreditLimitReached if the call would exceed the monthly limit.
        Logs the spend to api_usage on success so remaining credits stay accurate.
        """
        used = self.get_used(provider)
        limit = self.get_limit(provider)
        if used + cost > limit:
            raise CreditLimitReached(
                f"{provider} credit limit reached "
                f"({used}/{limit} used this month). Resets on the 1st."
            )
        log_api_usage(
            provider=provider,
            model=provider,
            purpose=purpose,
            input_tokens=cost,
            output_tokens=0,
            cost_usd=0.0,
        )
        logger.debug(
            "%s: spent %d credit(s) — %d/%d used this month",
            provider, cost, used + cost, limit,
        )

    def get_all_balances(self) -> dict[str, dict]:
        """Return {provider: {limit, used, remaining}} for all tracked sources."""
        return {
            p: {
                "limit":     self.get_limit(p),
                "used":      self.get_used(p),
                "remaining": self.get_remaining(p),
            }
            for p in _LIMIT_KEYS
        }

    def allocate_budget(
        self,
        target_leads: int,
        override: dict | None = None,
    ) -> dict[str, int]:
        """Calculate per-source credit budget for a campaign run.

        If override is provided (manual values from wizard Step 6), those
        values are used directly. Otherwise, allocate up to 60% of each
        source's remaining credits, spread to cover ~2.5x the target lead
        count to account for misses.
        """
        if override:
            return {p: max(0, int(override.get(p, 0))) for p in _LIMIT_KEYS}

        attempts_needed = max(int(target_leads * 2.5), 10)
        budget: dict[str, int] = {}
        for provider in _LIMIT_KEYS:
            remaining = self.get_remaining(provider)
            cap = int(remaining * 0.6)
            budget[provider] = min(cap, attempts_needed)

        logger.info("Auto-allocated budget for %d leads: %s", target_leads, budget)
        return budget
