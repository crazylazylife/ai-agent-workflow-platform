"""
LLM client. Talks to any provider exposing an
OpenAI-compatible Chat Completions API (OpenAI, Groq, OpenRouter, Ollama, Together, ...).

Config via .env: LLM_PROVIDER, LLM_API_KEY, optional LLM_BASE_URL / LLM_MODEL.
If the provider is "mock" — or a hosted provider is selected but no API key is set — it
falls back to a deterministic mock so the platform always runs at $0. Idempotency, the
model_usage ledger, and the OTel span are identical for mock and real.
"""
import time

from awp_shared.config import shared_settings
from awp_shared.db import SessionLocal
from awp_shared.models import ModelUsage
from awp_shared.telemetry import get_tracer

from idempotency import idempotent_get, idempotent_put

tracer = get_tracer("awp.llm")

# Base URLs for providers that don't need an explicit LLM_BASE_URL.
PROVIDER_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama": "http://localhost:11434/v1",
    "together": "https://api.together.xyz/v1",
    "anthropic": "https://api.anthropic.com/v1/",  # Claude via its OpenAI-compatible endpoint
}

# Known prices: (prompt $/1K, completion $/1K). Unknown / local models bill as $0.
PRICES = {
    "mock-gpt": (0.0005, 0.0015),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4o": (0.0025, 0.01),
    "claude-3-5-haiku-latest": (0.0008, 0.004),
    "claude-3-5-sonnet-latest": (0.003, 0.015),
    "llama-3.1-8b-instant": (0.00005, 0.00008),
}


def _effective_provider() -> str:
    """'mock' if configured as mock, or if a hosted provider lacks an API key."""
    p = shared_settings.llm_provider.lower()
    if p == "mock":
        return "mock"
    if p != "ollama" and not shared_settings.llm_api_key:
        return "mock"  # graceful fallback — no key, no charge
    return p


def _mock_complete(model: str, prompt: str):
    text = f"[{model}] response to: {prompt[:80]}"
    return text, max(1, len(prompt) // 4), max(1, len(text) // 4)


def _real_complete(provider: str, model: str, prompt: str):
    from openai import OpenAI  # lazy import: only needed for real providers

    base_url = shared_settings.llm_base_url or PROVIDER_BASE_URLS.get(provider)
    client = OpenAI(base_url=base_url, api_key=shared_settings.llm_api_key or "not-needed")
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.choices[0].message.content or ""
    usage = resp.usage
    return text, (getattr(usage, "prompt_tokens", 0) or 0), (getattr(usage, "completion_tokens", 0) or 0)


def call_llm(run_id, step_id, prompt: str, model: str | None = None) -> dict:
    model = model or shared_settings.llm_model
    provider = _effective_provider()

    with tracer.start_as_current_span("llm.call") as span:
        span.set_attribute("llm.provider", provider)
        span.set_attribute("llm.model", model)

        key = f"llm:{run_id}:{step_id}:{model}"
        found, cached = idempotent_get(key)
        if found:
            span.set_attribute("llm.cache_hit", True)
            return cached
        span.set_attribute("llm.cache_hit", False)

        t0 = time.perf_counter()
        if provider == "mock":
            text, prompt_tokens, completion_tokens = _mock_complete(model, prompt)
        else:
            text, prompt_tokens, completion_tokens = _real_complete(provider, model, prompt)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        pin, pout = PRICES.get(model, (0.0, 0.0))
        cost = (prompt_tokens / 1000) * pin + (completion_tokens / 1000) * pout
        span.set_attribute("llm.tokens", prompt_tokens + completion_tokens)
        span.set_attribute("llm.cost_usd", cost)

        result = {
            "text": text,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": cost,
        }
        idempotent_put(key, result)

        with SessionLocal() as db:
            db.add(ModelUsage(
                workflow_run_id=run_id,
                step_id=step_id,
                provider=provider,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost,
                latency_ms=latency_ms,
            ))
            db.commit()

        return result
