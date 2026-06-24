"""Runtime configuration for a scan."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_USER_AGENT = (
    "ConstructorScout/0.1 (+ecommerce discovery audit; respectful crawler)"
)
DEFAULT_MODEL = "claude-sonnet-4-6"


@dataclass
class Config:
    out_dir: str = "scout_output"
    user_agent: str = DEFAULT_USER_AGENT
    timeout: float = 15.0
    delay: float = 1.0          # politeness delay between requests (seconds)
    max_pages: int = 6          # pages crawled per site
    retries: int = 2
    respect_robots: bool = True

    # LLM
    use_llm: bool = True
    model: str = DEFAULT_MODEL
    api_key: str | None = None

    verbose: bool = False

    def resolved_api_key(self) -> str | None:
        return self.api_key or os.environ.get("ANTHROPIC_API_KEY")

    @property
    def llm_enabled(self) -> bool:
        return self.use_llm and bool(self.resolved_api_key())
