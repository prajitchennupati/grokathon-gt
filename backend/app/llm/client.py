"""xAI (Grok) structured-output client with cache and canned fallbacks.

Every call:
  1. offline / no key        -> cached response, else canned fallback
  2. online                  -> Grok with a strict JSON schema, validated by Pydantic,
                                hard timeout; on any failure -> cache -> canned
Successful live responses are written to llm/cache/ if no entry exists yet (or always
when CLEARANCE_PRECACHE=1), so a demo that ran once online replays offline.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Generic, Optional, TypeVar

from pydantic import BaseModel, ValidationError

from ..config import settings

log = logging.getLogger("clearance.llm")
T = TypeVar("T", bound=BaseModel)


@dataclass
class LLMResult(Generic[T]):
    value: T
    source: str  # grok | cache | canned
    latency_ms: int
    error: str = ""


def _strict_schema(model: type[BaseModel]) -> dict:
    """Pydantic JSON schema tightened for strict structured outputs."""
    schema = model.model_json_schema()

    def fix(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
            node.pop("default", None)
            node.pop("title", None)
            for v in node.values():
                fix(v)
        elif isinstance(node, list):
            for v in node:
                fix(v)

    fix(schema)
    return schema


def cache_path(task: str, key: str) -> Path:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", key)[:80]
    digest = hashlib.sha1(key.encode()).hexdigest()[:8]
    return settings.cache_dir / task / f"{slug}-{digest}.json"


def read_cache(task: str, key: str, schema: type[T]) -> Optional[T]:
    p = cache_path(task, key)
    if not p.exists():
        return None
    try:
        return schema.model_validate(json.loads(p.read_text())["response"])
    except (OSError, ValueError, KeyError, ValidationError) as e:
        log.warning("bad cache entry %s: %s", p, e)
        return None


def write_cache(task: str, key: str, value: BaseModel) -> None:
    p = cache_path(task, key)
    if p.exists() and os.getenv("CLEARANCE_PRECACHE") != "1":
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "task": task, "key": key, "model": settings.xai_model, "created": time.time(),
        "response": value.model_dump(mode="json"),
    }, indent=2))


_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import AsyncOpenAI

        _client = AsyncOpenAI(api_key=settings.xai_api_key, base_url=settings.xai_base_url,
                              timeout=settings.llm_timeout_s, max_retries=0)
    return _client


async def _call_grok(system: str, user: str, schema: type[T]) -> T:
    resp = await _get_client().chat.completions.create(
        model=settings.xai_model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": schema.__name__, "schema": _strict_schema(schema), "strict": True},
        },
        temperature=0.2,
    )
    content = resp.choices[0].message.content or ""
    return schema.model_validate_json(content)


async def structured(task: str, cache_key: str, system: str, user: str, schema: type[T],
                     canned: Callable[[], T]) -> LLMResult[T]:
    started = time.monotonic()

    def ms() -> int:
        return int((time.monotonic() - started) * 1000)

    error = ""
    if settings.llm_enabled:
        try:
            value = await asyncio.wait_for(_call_grok(system, user, schema), timeout=settings.llm_timeout_s)
            write_cache(task, cache_key, value)
            return LLMResult(value, "grok", ms())
        except asyncio.TimeoutError:
            error = f"timeout after {settings.llm_timeout_s:.0f}s"
        except ValidationError as e:
            error = f"schema validation failed: {e.error_count()} errors"
        except Exception as e:  # network, auth, rate limit, bad JSON...
            error = f"{type(e).__name__}: {e}"[:300]
        log.warning("LLM %s failed (%s); falling back", task, error)
    elif not settings.offline:
        error = "XAI_API_KEY / XAI_MODEL not set"

    cached = read_cache(task, cache_key, schema)
    if cached is not None:
        return LLMResult(cached, "cache", ms(), error)
    return LLMResult(canned(), "canned", ms(), error)
