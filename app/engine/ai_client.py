"""Claude API wrapper for cross-referencing and matching tasks."""

import hashlib
import json
import sqlite3
from pathlib import Path

import anthropic

from app.config import settings

# Pricing per million tokens (Sonnet 4.6)
INPUT_PRICE_PER_M = 3.00
OUTPUT_PRICE_PER_M = 15.00


class AIClient:
    """Thin wrapper around Claude API with response caching and usage tracking."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = model
        self._db_path = Path(settings.database_url.replace("sqlite:///", ""))
        self._ensure_cache_db()
        # Usage tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.api_calls = 0
        self.cache_hits = 0

    @property
    def total_cost_usd(self) -> float:
        return (
            self.total_input_tokens * INPUT_PRICE_PER_M / 1_000_000
            + self.total_output_tokens * OUTPUT_PRICE_PER_M / 1_000_000
        )

    def _ensure_cache_db(self):
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_cache (
                    cache_key TEXT PRIMARY KEY,
                    response TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def _cache_key(self, system: str, prompt: str) -> str:
        content = f"{self.model}:{system}:{prompt}"
        return hashlib.sha256(content.encode()).hexdigest()

    def _get_cached(self, key: str) -> str | None:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT response FROM ai_cache WHERE cache_key = ?", (key,)
            ).fetchone()
            return row[0] if row else None

    def _set_cached(self, key: str, response: str):
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO ai_cache (cache_key, response) VALUES (?, ?)",
                (key, response),
            )

    def ask(self, system: str, prompt: str, use_cache: bool = True) -> str:
        """Send a prompt to Claude and return the text response."""
        if use_cache:
            key = self._cache_key(system, prompt)
            cached = self._get_cached(key)
            if cached is not None:
                self.cache_hits += 1
                return cached

        message = self.client.messages.create(
            model=self.model,
            max_tokens=16384,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        response = message.content[0].text

        # Track usage
        self.api_calls += 1
        self.total_input_tokens += message.usage.input_tokens
        self.total_output_tokens += message.usage.output_tokens

        if use_cache:
            self._set_cached(key, response)

        return response

    def ask_json(self, system: str, prompt: str, use_cache: bool = True) -> dict | list:
        """Send a prompt to Claude and parse the response as JSON."""
        response = self.ask(system, prompt + "\n\nRespond with valid JSON only, no markdown.", use_cache)
        # Strip markdown code fences if present
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last lines (```json and ```)
            lines = [l for l in lines[1:] if not l.strip().startswith("```")]
            text = "\n".join(lines)
        return json.loads(text)
