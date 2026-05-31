"""Centralised credit gate for all API sources.

Every integration must call CreditManager.check_and_spend(provider) before
each API call. This is the single credit gate — never implement per-integration
credit checks independently.

Credit reset windows
--------------------
Apollo and Hunter reset on the 1st of each calendar month.
Lusha, Snov.io, and GetProspect use a rolling 30-day window tied to the
account signup date. The reset day is configured per-provider via
`credit_reset_day` in config.yaml — set it to the day of the month you
created your account (e.g. 15 if you signed up on the 15th).
"""

import calendar
import logging
from datetime import date
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

    def get_reset_day(self, provider: str) -> int:
        """Return the day-of-month on which this provider's credits reset (1–31)."""
        section = _LIMIT_KEYS.get(provider, (provider, ""))[0]
        return int(self.config.get(section, {}).get("credit_reset_day", 1))

    def _billing_period_start(self, provider: str) -> date:
        """Return the start date of the provider's current billing period."""
        reset_day = self.get_reset_day(provider)
        today = date.today()

        # Clamp reset_day to a valid day in the target month
        def _clamp(year: int, month: int) -> date:
            last = calendar.monthrange(year, month)[1]
            return date(year, month, min(reset_day, last))

        this_month_reset = _clamp(today.year, today.month)
        if today >= this_month_reset:
            return this_month_reset
        # Reset day hasn't arrived yet — billing period started last month
        prev_month = today.month - 1 or 12
        prev_year  = today.year if today.month > 1 else today.year - 1
        return _clamp(prev_year, prev_month)

    def _next_reset_date(self, provider: str) -> date:
        """Return the date of the provider's next credit reset."""
        reset_day = self.get_reset_day(provider)
        today = date.today()

        def _clamp(year: int, month: int) -> date:
            last = calendar.monthrange(year, month)[1]
            return date(year, month, min(reset_day, last))

        this_month_reset = _clamp(today.year, today.month)
        if today < this_month_reset:
            return this_month_reset
        next_month = today.month % 12 + 1
        next_year  = today.year + (1 if today.month == 12 else 0)
        return _clamp(next_year, next_month)

    def days_until_reset(self, provider: str) -> int:
        """Return calendar days until the provider's next credit reset."""
        return (self._next_reset_date(provider) - date.today()).days

    def get_used(self, provider: str) -> int:
        """Return credits consumed by provider in the current billing period."""
        period_start = self._billing_period_start(provider).isoformat()
        return get_monthly_api_credits(provider, period_start=period_start)

    def get_remaining(self, provider: str) -> int:
        """Return credits still available for provider this billing period."""
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
            reset = self._next_reset_date(provider)
            raise CreditLimitReached(
                f"{provider} credit limit reached "
                f"({used}/{limit} used this period). Resets {reset.isoformat()}."
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
        """Return {provider: {limit, used, remaining, days_until_reset}} for all sources."""
        result = {}
        for p in _LIMIT_KEYS:
            limit = self.get_limit(p)
            used  = self.get_used(p)
            result[p] = {
                "limit":            limit,
                "used":             used,
                "remaining":        max(0, limit - used),
                "days_until_reset": self.days_until_reset(p),
            }
        return result

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
