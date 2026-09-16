"""OpenRouter chat client, standard library only.

One function, chat(), that sends an OpenAI-style request to OpenRouter and
returns the reply message plus what it cost. Retries the failures worth
retrying (rate limits, provider outages, network drops) and gives up fast on
the ones that aren't (a bad request, or running out of credit).
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

HERE = Path(__file__).resolve().parent
ENV_PATH = HERE / ".env"
API_URL = "https://openrouter.ai/api/v1/chat/completions"


class LLMError(Exception):
    pass


def load_env_file(path: Path) -> None:
    """Fold KEY=VALUE lines from a local .env into os.environ (never overwrites
    a variable already set). Shell startup files only load for an interactive
    login shell, so a local .env is the one place that works in every context."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


load_env_file(ENV_PATH)


def api_key_present() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY", "").strip())


def chat(
    model: str,
    messages: list[dict[str, Any]],
    tools: Optional[list[dict[str, Any]]] = None,
    max_tokens: int = 8000,
    provider: Optional[dict[str, Any]] = None,
    timeout: int = 300,
    retries: int = 4,
) -> dict[str, Any]:
    """Return {"message", "finish_reason", "usage", "cost", "provider"}."""
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise LLMError("OPENROUTER_API_KEY is not set. Put it in .env (see README).")

    body: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if tools:
        body["tools"] = tools
    if provider:
        body["provider"] = provider
    data = json.dumps(body).encode()
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "X-Title": "local-ai-eval",
    }

    delay = 5
    last = "no attempts made"
    for attempt in range(retries + 1):
        request = urllib.request.Request(API_URL, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            # 429 and 5xx are transient. Any other 4xx means the request itself
            # is wrong, or (402) the prepaid credit is gone, so retrying is waste.
            if e.code != 429 and e.code < 500:
                raise LLMError(f"HTTP {e.code}: {detail}") from None
            last = f"HTTP {e.code}: {detail}"
        except OSError as e:  # URLError, timeouts, dropped connections
            last = f"network: {e}"
        except ValueError as e:
            last = f"response was not JSON: {e}"
        else:
            # OpenRouter reports upstream provider failures inside a 200.
            if "error" in payload:
                last = f"provider error: {payload['error']}"
            elif not payload.get("choices"):
                last = "response had no choices"
            else:
                choice = payload["choices"][0]
                usage = payload.get("usage") or {}
                return {
                    "message": choice.get("message") or {},
                    "finish_reason": choice.get("finish_reason"),
                    "usage": usage,
                    "cost": usage.get("cost"),
                    "provider": payload.get("provider"),
                }
        if attempt < retries:
            time.sleep(delay)
            delay *= 2
    raise LLMError(f"gave up after {retries + 1} attempts: {last}")
