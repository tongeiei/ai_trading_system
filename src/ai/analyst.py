"""Strong AI Agent (Macro/veto/thesis layer) client -- docs/XAU_ARCHITECTURE_AUDIT.md
P6/§16. Reuses the exact schema/prompt/payload contract validated by
scripts/spike_llm_connectivity.py (see that script for the connectivity
measurements this is built on: Kimi K3 median ~47s latency, ~$0.028/call).

Provider-agnostic: reads config/xau.yaml, speaks the OpenAI-compatible
/chat/completions shape every candidate provider (Kimi, DeepSeek, OpenAI)
supports. Swapping providers is a one-line config edit (`llm.active`), never
a code change here (§16.8.2).

Scope note: the six setup-quality scorecard columns (Trend/Structure/Momentum/
Volatility/Session/Risk + Final Score) are computed deterministically in
Python elsewhere (src/ai/scorecard.py, not yet built) and passed IN as
`ScorecardInput` -- this module's LLM call can only veto a setup and write
its journal narrative (thesis/invalidation/risk_factors), never change or
see-and-raise a score. That's a hard contract, not a prompt suggestion: the
schema below has no score field for the model to fill in.

NOT wired into any live/backtest path yet -- this is the client only.
Callers are responsible for:
  - respecting `on_failure` (deterministic_only | no_new_trade) from
    config/xau.yaml when `review()` returns ok=False -- this module has no
    opinion on that, it's a Risk Engine decision (P6/P7+).
  - tracking `max_calls_per_day`/`max_calls_per_month` against a persistent
    call log -- this module is stateless and makes no attempt to do that.
`enabled: false` in config/xau.yaml IS enforced here, hard, as
AnalystDisabledError -- see the module-level guardrail comment there for why.
"""
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests
import yaml
from jsonschema import ValidationError, validate

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "xau.yaml"

# The real P6 output contract, after Macro was dropped (news/calendar source
# cut from scope, §15 item 10): the LLM scores NOTHING, all six scorecard
# columns are Python-owned. Kept strict (additionalProperties: false) so a
# drifting model fails loudly here rather than silently inside the trading
# loop. Identical to scripts/spike_llm_connectivity.py's ANALYST_SCHEMA --
# keep the two in sync if this ever changes.
ANALYST_SCHEMA = {
    "type": "object",
    "properties": {
        "veto": {"type": "boolean"},
        "veto_reason": {"type": "string"},
        "thesis": {"type": "string"},
        "invalidation": {"type": "string"},
        "risk_factors": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["veto", "veto_reason", "thesis", "invalidation", "risk_factors"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You are a risk-reviewing analyst for a rule-based XAU/USD trading system. "
    "The six setup-quality scores are computed deterministically in Python and are "
    "NOT yours to change. You may only (a) veto a setup, (b) explain why, and "
    "(c) write the thesis, invalidation level and risk factors for the journal. "
    "You can never raise a score or argue a setup is better than the numbers say. "
    "Respond only with JSON matching the given schema."
)


class AnalystDisabledError(RuntimeError):
    """config/xau.yaml's llm.enabled is False. Hard, unconditional gate --
    per the config's own comment, this exists specifically so an accidental
    LLM call inside a loop over 20 years of backtest bars cannot bill. There
    is deliberately no bypass parameter: flip `enabled: true` in the config
    file (a human, reviewed action) to allow calls, not a code-level flag."""


class AnalystConfigError(RuntimeError):
    """config/xau.yaml or the active provider's API key is missing/invalid."""


@dataclass
class ScorecardInput:
    """The Python-computed inputs the analyst reviews. Mirrors the synthetic
    prompt already validated in scripts/spike_llm_connectivity.py."""
    symbol: str
    timeframe: str
    direction: str          # "LONG" | "SHORT"
    setup_name: str
    trend: float
    structure: float
    momentum: float
    volatility: float
    session: float
    risk: float
    final_score: float
    context: str = ""        # free text: session/spread/atr_percentile/etc.


@dataclass
class AnalystReview:
    ok: bool
    provider: str
    model: str
    veto: Optional[bool] = None
    veto_reason: Optional[str] = None
    thesis: Optional[str] = None
    invalidation: Optional[str] = None
    risk_factors: list = field(default_factory=list)
    latency_s: Optional[float] = None
    cost_usd: Optional[float] = None
    usage: dict = field(default_factory=dict)
    attempts: int = 0
    error: Optional[str] = None   # set when ok=False


def load_llm_config() -> dict:
    if not CONFIG_PATH.exists():
        raise AnalystConfigError(f"{CONFIG_PATH} not found")
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))["llm"]


def _resolve_provider(cfg: dict, provider_name: Optional[str]) -> tuple[str, dict]:
    name = provider_name or cfg["active"]
    if name not in cfg["providers"]:
        raise AnalystConfigError(f"unknown provider {name!r}; config/xau.yaml has: {list(cfg['providers'])}")
    return name, cfg["providers"][name]


def _api_key(provider_cfg: dict) -> str:
    """Reads the key from the already-loaded process environment. This module
    deliberately does NOT call load_dotenv() itself -- doing so as a side
    effect of importing/calling into an AI client risks silently picking up
    a real key during a test run (this bit us during development: an
    unconditional load_dotenv() here caused a "missing key" test to instead
    find the real key and make live, billed API calls). The application
    entry point (a script, the future live/backtest caller) is responsible
    for calling load_dotenv(".env") once, same as
    scripts/spike_llm_connectivity.py already does in its own main()."""
    key = os.getenv(provider_cfg["api_key_env"])
    if not key:
        raise AnalystConfigError(
            f"{provider_cfg['api_key_env']} is not set -- copy .env.example to .env, "
            f"paste the key there, and call dotenv.load_dotenv() before review()"
        )
    return key


def _build_user_prompt(sc: ScorecardInput) -> str:
    return (
        f"Setup under review:\n\n"
        f"  symbol: {sc.symbol}   timeframe: {sc.timeframe}   direction: {sc.direction}\n"
        f"  setup: {sc.setup_name}\n"
        f"  scorecard (Python, deterministic):\n"
        f"    Trend {sc.trend:.0f}  Structure {sc.structure:.0f}  Momentum {sc.momentum:.0f}  "
        f"Volatility {sc.volatility:.0f}  Session {sc.session:.0f}  Risk {sc.risk:.0f}\n"
        f"    Final Score {sc.final_score:.0f}  (gate: <60 no-trade, 60-75 small risk, >75 normal risk)\n"
        f"  context: {sc.context}\n\n"
        f"Review it. Veto only if you see something the six numbers cannot see."
    )


def _build_payload(provider_cfg: dict, cfg: dict, user_prompt: str) -> dict:
    payload = {
        "model": provider_cfg["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": provider_cfg["temperature"],
        "max_tokens": cfg["max_output_tokens"],
    }
    if provider_cfg.get("supports_strict_schema"):
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "analyst_review", "strict": True, "schema": ANALYST_SCHEMA},
        }
    else:
        payload["response_format"] = {"type": "json_object"}
        payload["messages"][0]["content"] += "\n\nSchema:\n" + json.dumps(ANALYST_SCHEMA)
    return payload


def _cost_usd(usage: dict, provider_cfg: dict) -> float:
    cached = usage.get("prompt_cache_hit_tokens") or usage.get("cached_tokens") or 0
    fresh = max(usage.get("prompt_tokens", 0) - cached, 0)
    return (
        fresh / 1e6 * provider_cfg["price_in_per_mtok"]
        + cached / 1e6 * provider_cfg["price_in_cached_per_mtok"]
        + usage.get("completion_tokens", 0) / 1e6 * provider_cfg["price_out_per_mtok"]
    )


class TruncatedError(Exception):
    """Output hit max_tokens -- our cap being too low, not a provider
    reliability issue. Not retried (retrying with the same cap just
    truncates again)."""


_RETRYABLE_HTTP = {429, 500, 502, 503, 504}


def _one_call(url: str, headers: dict, payload: dict, timeout: float):
    t0 = time.perf_counter()
    r = requests.post(url, headers=headers, json=payload, timeout=timeout)
    latency = time.perf_counter() - t0
    if r.status_code != 200:
        try:
            detail = r.json().get("error", r.json())
            detail = detail.get("message", detail) if isinstance(detail, dict) else detail
        except ValueError:
            detail = r.text[:200]
        err = requests.HTTPError(f"HTTP {r.status_code}: {detail}")
        err.status_code = r.status_code
        raise err
    body = r.json()
    choice = body["choices"][0]
    if choice.get("finish_reason") == "length":
        raise TruncatedError(
            f"hit max_tokens={payload['max_tokens']}; raise llm.max_output_tokens "
            f"in config/xau.yaml"
        )
    parsed = json.loads(choice["message"]["content"])
    validate(parsed, ANALYST_SCHEMA)
    return latency, parsed, body.get("usage", {})


def review(
    scorecard: ScorecardInput,
    provider: Optional[str] = None,
) -> AnalystReview:
    """Call the analyst for a single setup review. Reads config/xau.yaml for
    everything except the API key (from .env, per llm.providers.<name>.api_key_env).

    Raises AnalystDisabledError if llm.enabled is false (see that class's
    docstring -- there is no bypass). Raises AnalystConfigError for a missing
    config file, unknown provider, or missing API key -- these are setup
    mistakes the caller should fix, not something to silently degrade past.

    Transient failures (timeout, connection error, HTTP 429/5xx, malformed
    JSON, schema violation) are retried up to `llm.max_retries` times, per
    config/xau.yaml's comment ("transient only"). After retries are
    exhausted, returns AnalystReview(ok=False, error=...) rather than
    raising -- the caller applies `llm.on_failure` policy itself.
    """
    cfg = load_llm_config()
    if not cfg.get("enabled", False):
        raise AnalystDisabledError(
            "config/xau.yaml llm.enabled is false -- set it to true (deliberately, "
            "in the config file) before calling review()"
        )

    name, provider_cfg = _resolve_provider(cfg, provider)
    key = _api_key(provider_cfg)
    url = provider_cfg["base_url"].rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = _build_payload(provider_cfg, cfg, _build_user_prompt(scorecard))

    max_retries = cfg.get("max_retries", 0)
    last_error = None
    for attempt in range(1, max_retries + 2):  # first try + max_retries retries
        try:
            latency, parsed, usage = _one_call(url, headers, payload, cfg["timeout_seconds"])
            return AnalystReview(
                ok=True, provider=name, model=provider_cfg["model"],
                veto=parsed["veto"], veto_reason=parsed["veto_reason"],
                thesis=parsed["thesis"], invalidation=parsed["invalidation"],
                risk_factors=parsed["risk_factors"],
                latency_s=latency, cost_usd=_cost_usd(usage, provider_cfg),
                usage=usage, attempts=attempt,
            )
        except TruncatedError as e:
            last_error = str(e)
            break  # not retryable -- see TruncatedError docstring
        except requests.HTTPError as e:
            status = getattr(e, "status_code", None)
            last_error = str(e)
            if status not in _RETRYABLE_HTTP:
                break
        except (requests.RequestException, json.JSONDecodeError, ValidationError) as e:
            last_error = f"{type(e).__name__}: {e}"

    return AnalystReview(
        ok=False, provider=name, model=provider_cfg["model"],
        attempts=attempt, error=last_error,
    )
