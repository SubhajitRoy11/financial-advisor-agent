"""
llm_client.py — Universal LLM Provider Client
-----------------------------------------------
Supports: Grok (xAI), Gemini (Google), Anthropic (Claude)

Pick provider via environment variable:
  $env:LLM_PROVIDER="gemini"      (Windows PowerShell)
  export LLM_PROVIDER=gemini      (Mac/Linux)

Set matching API key:
  $env:GEMINI_API_KEY="AIza..."
  $env:GROK_API_KEY="xai-..."
  $env:ANTHROPIC_API_KEY="sk-ant-..."

Free keys:
  Gemini    → https://aistudio.google.com  (free forever, recommended)
  Grok      → https://console.x.ai         (free monthly credits)
  Anthropic → https://console.anthropic.com ($5 free on signup)
"""

import os
import time
import requests
from requests.exceptions import (
    ConnectionError,
    Timeout,
    RequestException,
    HTTPError,
)


class LLMClient:

    PROVIDERS = {
        "grok": (
            "https://api.x.ai/v1/chat/completions",
            "grok-4-0709",
        ),
        "groq": (
            "https://api.groq.com/openai/v1/chat/completions",
            "llama-3.1-8b-instant",
        ),
        "gemini": (
            "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            "gemini-2.0-flash",
        ),
        "anthropic": (
            "https://api.anthropic.com/v1/messages",
            "claude-haiku-4-5-20251001",
        ),
    }

    def __init__(self, provider: str = None, model: str = None):
        self.provider = (provider or os.environ.get("LLM_PROVIDER", "gemini")).lower()

        if self.provider not in self.PROVIDERS:
            raise ValueError(
                f"Unknown provider '{self.provider}'. "
                f"Choose from: {list(self.PROVIDERS.keys())}"
            )

        default_url, default_model = self.PROVIDERS[self.provider]
        self.api_url = default_url
        self.model = model or os.environ.get("LLM_MODEL", default_model)
        self.api_key = self._load_api_key()

        print(f"[LLMClient] Provider: {self.provider.upper()} | Model: {self.model}")

    def _load_api_key(self) -> str:
        key_map = {
            "grok":      "GROK_API_KEY",
            "groq":      "GROQ_API_KEY",
            "gemini":    "GEMINI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
        }
        env_var = key_map[self.provider]
        key = os.environ.get(env_var, "").strip()
        if not key:
            raise EnvironmentError(
                f"\n{'='*60}\n"
                f"  ❌ Missing API key for provider '{self.provider.upper()}'\n"
                f"  Environment variable: {env_var}\n\n"
                f"  WINDOWS PowerShell:\n"
                f"    $env:{env_var}=\"your_key_here\"\n\n"
                f"  Mac/Linux:\n"
                f"    export {env_var}=\"your_key_here\"\n\n"
                f"  Get a free key:\n"
                f"    gemini     → https://aistudio.google.com\n"
                f"    grok/groq  → https://console.x.ai or https://console.groq.com\n"
                f"    anthropic  → https://console.anthropic.com\n"
                f"{'='*60}"
            )
        return key

    # ── Provider call methods ─────────────────────────────────────────────────

    def _call_grok(self, prompt: str, max_tokens: int) -> tuple[str, int]:
        """OpenAI-compatible format used by Grok, OpenAI, Groq, Together etc."""
        response = requests.post(
            self.api_url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            json={
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        text = data["choices"][0]["message"]["content"]
        tokens = data.get("usage", {}).get("completion_tokens", 0)
        return text, tokens

    def _call_gemini(self, prompt: str, max_tokens: int) -> tuple[str, int]:
        """Gemini: model in URL, API key as query param."""
        url = self.api_url.format(model=self.model)
        response = requests.post(
            url,
            params={"key": self.api_key},
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": max_tokens,
                    "temperature": 0.3,
                },
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        tokens = data.get("usageMetadata", {}).get("candidatesTokenCount", 0)
        return text, tokens

    def _call_anthropic(self, prompt: str, max_tokens: int) -> tuple[str, int]:
        """Anthropic: API key in header, special version header required."""
        response = requests.post(
            self.api_url,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        text = data["content"][0]["text"]
        tokens = data.get("usage", {}).get("output_tokens", 0)
        return text, tokens

    # ── Main call method with retry ───────────────────────────────────────────

    def call(self, prompt: str, max_tokens: int = 1500) -> tuple[str, int]:
        """
        Universal entry point with automatic retry on rate limits (429).

        WHY RETRY LOGIC EXISTS:
          Free API tiers have rate limits — e.g. Gemini free allows ~2 requests
          per minute. If you run all 3 portfolios fast, you hit the limit.
          Instead of crashing, we wait and retry automatically.

          This is called "exponential backoff" — a standard pattern in
          any production system that calls external APIs.

        Returns: (response_text, tokens_used)
        """
        dispatch = {
            "grok":      self._call_grok,
            "groq":      self._call_grok,
            "gemini":    self._call_gemini,
            "anthropic": self._call_anthropic,
        }

        max_retries = 3
        wait_seconds = [15, 30, 60]  # wait longer each retry

        for attempt in range(max_retries):
            try:
                return dispatch[self.provider](prompt, max_tokens)

            except (ConnectionError, Timeout) as e:
                # Network error — could be transient, retry
                if attempt < max_retries - 1:
                    wait = wait_seconds[attempt]
                    print(f"\n[LLMClient] Network error (connection/timeout). "
                          f"Waiting {wait}s before retry {attempt + 1}/{max_retries}...\n"
                          f"Error details: {str(e)[:200]}")
                    time.sleep(wait)
                    continue
                else:
                    raise RuntimeError(
                        f"[LLMClient] Network error after {max_retries} retries:\n{str(e)[:500]}\n\n"
                        f"Check:\n"
                        f"  1. Your internet connection\n"
                        f"  2. That {self.provider.upper()} API endpoint is accessible\n"
                        f"  3. Firewall/proxy settings if behind corporate network"
                    ) from e

            except HTTPError as e:
                status = e.response.status_code if e.response else 0

                if status == 429:
                    # Rate limit hit — wait and retry
                    wait = wait_seconds[attempt]
                    print(f"\n[LLMClient] Rate limit hit (429). "
                          f"Waiting {wait}s before retry "
                          f"{attempt + 1}/{max_retries}...")
                    time.sleep(wait)
                    continue  # go back to top of loop and try again

                elif status == 401:
                    raise RuntimeError(
                        f"[LLMClient] Invalid API key for {self.provider.upper()}.\n"
                        f"Check your key at the provider's console."
                    ) from e

                else:
                    body = e.response.text[:400] if e.response else ""
                    raise RuntimeError(
                        f"[LLMClient] {self.provider.upper()} API error {status}:\n{body}"
                    ) from e

            except RequestException as e:
                # Any other request library error
                raise RuntimeError(
                    f"[LLMClient] Request failed for {self.provider.upper()}:\n{str(e)[:500]}"
                ) from e

        raise RuntimeError(
            f"[LLMClient] Failed after {max_retries} retries due to rate limits.\n"
            f"Tip: Run one portfolio at a time:\n"
            f"  python main.py --portfolio PORTFOLIO_001 --no-llm-eval"
        )
