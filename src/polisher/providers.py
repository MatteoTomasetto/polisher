"""LLM back-ends: Anthropic, OpenAI-compatible (OpenAI, OpenRouter, LM Studio...) and Ollama."""
from __future__ import annotations

import os

import httpx


class ProviderError(Exception):
    pass


class Provider:
    name = "provider"

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def complete(self, system: str, user: str, *, temperature: float, max_tokens: int) -> str:
        raise NotImplementedError

    def _api_key(self) -> str:
        key = self.cfg.get("api_key")
        if not key:
            env = self.cfg.get("api_key_env", "")
            key = os.environ.get(env, "") if env else ""
        if not key:
            raise ProviderError(
                f"No API key for {self.name}. Set the {self.cfg.get('api_key_env', 'API key')} "
                "environment variable or 'api_key' in config.toml."
            )
        return key

    def _post(self, url: str, headers: dict, payload: dict) -> dict:
        try:
            response = httpx.post(
                url, headers=headers, json=payload, timeout=float(self.cfg.get("timeout", 60))
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:500]
            if self.name == "openrouter" and exc.response.status_code == 401:
                raise ProviderError(
                    "OpenRouter rejected the API key (HTTP 401). Check that your config.toml "
                    "[providers.openrouter] section contains the current key as api_key = "
                    '"sk-or-v1-..."' + " OR that OPENROUTER_API_KEY is set in the environment "
                    "of the process that launches Polisher. If the key was revoked or copied "
                    "incorrectly, create a new one at openrouter.ai/keys. "
                    f"Provider response: {body}"
                ) from exc
            raise ProviderError(f"{self.name} returned {exc.response.status_code}: {body}") from exc
        except httpx.ConnectError as exc:
            raise ProviderError(f"Cannot reach {url}. Is the server running?") from exc
        except httpx.TimeoutException as exc:
            raise ProviderError(f"{self.name} timed out. Try again or use a faster model.") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"{self.name} request failed: {exc}") from exc


class AnthropicProvider(Provider):
    name = "anthropic"

    def complete(self, system, user, *, temperature, max_tokens):
        base = self.cfg.get("base_url", "https://api.anthropic.com").rstrip("/")
        data = self._post(
            f"{base}/v1/messages",
            {
                "x-api-key": self._api_key(),
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            {
                "model": self.cfg["model"],
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
        try:
            return "".join(b["text"] for b in data["content"] if b.get("type") == "text")
        except (KeyError, TypeError) as exc:
            raise ProviderError(f"Unexpected response from anthropic: {str(data)[:200]}") from exc


class OpenAIProvider(Provider):
    name = "openai"

    def complete(self, system, user, *, temperature, max_tokens):
        base = self.cfg.get("base_url", "https://api.openai.com/v1").rstrip("/")
        headers = {"content-type": "application/json"}
        if self.cfg.get("api_key") or self.cfg.get("api_key_env"):
            try:
                headers["Authorization"] = f"Bearer {self._api_key()}"
            except ProviderError:
                if "api.openai.com" in base:
                    raise  # real OpenAI needs a key; local servers often don't
        data = self._post(
            f"{base}/chat/completions",
            headers,
            {
                "model": self.cfg["model"],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        try:
            content = data["choices"][0]["message"]["content"]
            # Some OpenAI-compatible providers return content as a list of text
            # blocks instead of a plain string.
            if isinstance(content, list):
                content = "".join(
                    block.get("text", "") for block in content
                    if isinstance(block, dict) and block.get("type", "text") == "text"
                )
            return content or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"Unexpected response from openai: {str(data)[:200]}") from exc


class OllamaProvider(Provider):
    name = "ollama"

    def complete(self, system, user, *, temperature, max_tokens):
        base = self.cfg.get("base_url", "http://localhost:11434").rstrip("/")
        data = self._post(
            f"{base}/api/chat",
            {"content-type": "application/json"},
            {
                "model": self.cfg["model"],
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        try:
            return data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise ProviderError(f"Unexpected response from ollama: {str(data)[:200]}") from exc


_KINDS = {"anthropic": AnthropicProvider, "openai": OpenAIProvider, "ollama": OllamaProvider}


def make_provider(name: str, cfg: dict) -> Provider:
    # A custom provider section may set kind = "openai" to reuse a back-end under its own name.
    kind = cfg.get("kind", name)
    if kind not in _KINDS:
        raise ProviderError(f"Unknown provider '{name}'. Use one of: {', '.join(_KINDS)}")
    provider = _KINDS[kind](cfg)
    provider.name = name
    return provider
