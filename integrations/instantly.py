"""Instantly.ai API client — email warmup integration."""

import logging
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)
BASE_URL = "https://api.instantly.ai/api/v1"


class InstantlyClient:
    def __init__(self, config: dict):
        email_cfg = config.get("email", {})
        self.api_key = email_cfg.get("instantly_api_key", "")
        self.campaign_id = email_cfg.get("instantly_campaign_id", "")
        if not self.api_key:
            logger.warning("Instantly API key not set — warmup integration disabled")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def _get(self, endpoint: str, params: dict = None) -> dict:
        params = params or {}
        params["api_key"] = self.api_key
        resp = requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def _post(self, endpoint: str, payload: dict) -> dict:
        payload["api_key"] = self.api_key
        resp = requests.post(f"{BASE_URL}/{endpoint}", json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def get_warmup_status(self) -> dict:
        """Return warmup status for the configured email account."""
        if not self.api_key:
            return {"status": "not_configured"}
        try:
            return self._get("account/warmup/get")
        except Exception as e:
            logger.error("Instantly warmup status failed: %s", e)
            return {"error": str(e)}

    def add_email_to_warmup(self, email: str, smtp_config: dict) -> bool:
        """Add an email account to the warming pool."""
        if not self.api_key:
            return False
        payload = {
            "email": email,
            "smtp_host": smtp_config.get("smtp_host", "smtp.gmail.com"),
            "smtp_port": smtp_config.get("smtp_port", 587),
            "smtp_username": email,
            "smtp_password": smtp_config.get("app_password", ""),
            "imap_host": "imap.gmail.com",
            "imap_port": 993,
            "imap_username": email,
            "imap_password": smtp_config.get("app_password", ""),
        }
        try:
            self._post("account/warmup/add", payload)
            logger.info("Added %s to Instantly warmup pool", email)
            return True
        except Exception as e:
            logger.error("Instantly add warmup failed: %s", e)
            return False
