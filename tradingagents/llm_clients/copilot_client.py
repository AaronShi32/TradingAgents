"""GitHub Copilot LLM client.

Uses the GitHub Copilot Chat API (api.githubcopilot.com) which is
OpenAI-compatible. Requires a GitHub user token (ghu_*) stored in
``~/.cc-switch/copilot_auth.json`` or via the ``GITHUB_COPILOT_TOKEN``
environment variable.

The Copilot session token is short-lived and refreshed automatically.
"""

import json
import os
import time
import logging
from pathlib import Path
from typing import Any, Optional

import requests

from .openai_client import NormalizedChatOpenAI, _PASSTHROUGH_KWARGS
from .base_client import BaseLLMClient

logger = logging.getLogger(__name__)

_COPILOT_API_URL = "https://api.githubcopilot.com"
_GITHUB_TOKEN_URL = "https://api.github.com/copilot_internal/v2/token"

# Required headers for Copilot API
_COPILOT_HEADERS = {
    "Copilot-Integration-Id": "vscode-chat",
    "Editor-Version": "vscode/1.90.0",
    "Editor-Plugin-Version": "copilot/1.0.0",
}


def _load_github_token() -> str:
    """Load the GitHub user token (ghu_*) from env or cc-switch config."""
    token = os.environ.get("GITHUB_COPILOT_TOKEN")
    if token:
        return token

    cc_switch_auth = Path.home() / ".cc-switch" / "copilot_auth.json"
    if cc_switch_auth.exists():
        try:
            data = json.loads(cc_switch_auth.read_text())
            accounts = data.get("accounts", {})
            default_id = data.get("default_account_id")
            if default_id and default_id in accounts:
                return accounts[default_id]["github_token"]
            # Fall back to first account
            for acc in accounts.values():
                return acc["github_token"]
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to parse cc-switch auth: %s", e)

    raise RuntimeError(
        "No GitHub Copilot token found. Set GITHUB_COPILOT_TOKEN env var "
        "or install CC-Switch with a logged-in GitHub account."
    )


class CopilotTokenManager:
    """Manages short-lived Copilot session tokens with auto-refresh."""

    def __init__(self, github_token: str):
        self._github_token = github_token
        self._session_token: Optional[str] = None
        self._expires_at: float = 0

    def get_token(self) -> str:
        """Return a valid session token, refreshing if needed."""
        # Refresh 5 minutes before expiry
        if self._session_token and time.time() < self._expires_at - 300:
            return self._session_token

        resp = requests.get(
            _GITHUB_TOKEN_URL,
            headers={
                "Authorization": f"token {self._github_token}",
                **_COPILOT_HEADERS,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        self._session_token = data["token"]
        self._expires_at = data.get("expires_at", time.time() + 1800)
        logger.info("Copilot token refreshed, expires at %s", self._expires_at)
        return self._session_token


# Module-level singleton to share across deep/quick clients
_token_manager: Optional[CopilotTokenManager] = None


def _get_token_manager() -> CopilotTokenManager:
    global _token_manager
    if _token_manager is None:
        github_token = _load_github_token()
        _token_manager = CopilotTokenManager(github_token)
    return _token_manager


class CopilotClient(BaseLLMClient):
    """Client for GitHub Copilot Chat API."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured ChatOpenAI pointing to Copilot API."""
        token_mgr = _get_token_manager()
        token = token_mgr.get_token()

        llm_kwargs = {
            "model": self.model,
            "base_url": self.base_url or _COPILOT_API_URL,
            "api_key": token,
            "default_headers": _COPILOT_HEADERS,
        }

        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        return NormalizedChatOpenAI(**llm_kwargs)

    def validate_model(self) -> bool:
        return True
