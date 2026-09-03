"""LLM connectivity + structured-output spike for the XAU P6 AI layer.

Mirrors the MT5 connectivity spike from P2: prove the dependency works on this
machine BEFORE building the phase on top of it. Answers the open item recorded
in docs/XAU_ARCHITECTURE_AUDIT.md 15.7 ("test structured JSON output stability")
and the hard requirement in 16.8.1 (schema must be validated for real, not
parsed hopefully).

Provider-agnostic: reads config/xau.yaml and talks the OpenAI-compatible
/chat/completions shape that Kimi, DeepSeek and OpenAI all speak. Swapping
providers is a config edit (16.8.2) -- this script never hardcodes one.

Sends no market data and places no orders. Read-only probe.

    python scripts/spike_llm_connectivity.py            # 5 calls, config default
    python scripts/spike_llm_connectivity.py -n 20      # measure schema stability
    python scripts/spike_llm_connectivity.py -p deepseek
"""
import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv
from jsonschema import ValidationError, validate

ROOT = Path(__file__).resolve().parents[1]

# The real P6 output contract, after Macro was dropped: the news/calendar source
# was cut from scope (15.10), so the LLM scores NOTHING. It may only veto and
# narrate -- all six scorecard columns are Python-owned. Kept strict
# (additionalProperties: false) so a drifting model fails loudly here rather
# than silently inside the trading loop.
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

# Synthetic setup -- this is a connectivity probe, not a backtest. The numbers
# are fixed so repeated runs are comparable and no real market data is needed.
USER_PROMPT = """Setup under review (synthetic, connectivity test only):

  symbol: XAUUSD   timeframe: M15   direction: LONG
  setup: liquidity_sweep reclaim of Asia session low
  scorecard (Python, deterministic):
    Trend 82  Structure 76  Momentum 71  Volatility 88  Session 91  Risk 85
    Final Score 82  (gate: <60 no-trade, 60-75 small risk, >75 normal risk)
  context: London open, spread 26 points, ATR percentile 0.74

Review it. Veto only if you see something the six numbers cannot see."""


def load_provider(name):
    cfg = yaml.safe_load((ROOT / "config" / "xau.yaml").read_text(encoding="utf-8"))["llm"]
    name = name or cfg["active"]
    if name not in cfg["providers"]:
        sys.exit(f"unknown provider {name!r}; config/xau.yaml has: {list(cfg['providers'])}")
    return name, cfg["providers"][name], cfg


def build_payload(provider, cfg):
    # max_tokens is a cost bound, not a formatting preference: output bills at
    # $15/Mtok on Kimi, so an unbounded ramble costs ~10x a normal call while
    # the call count -- the thing every other guardrail counts -- stays flat.
    payload = {
        "model": provider["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT},
        ],
        # Per-provider: Kimi K3 rejects anything but 1 (HTTP 400), so determinism
        # is not available there. Others take 0.
        "temperature": provider["temperature"],
        "max_tokens": cfg["max_output_tokens"],
    }
    if provider.get("supports_strict_schema"):
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "analyst_review", "strict": True, "schema": ANALYST_SCHEMA},
        }
    else:
        # DeepSeek-style JSON mode: no schema enforcement, so the local
        # validation below is the only thing between us and malformed output.
        payload["response_format"] = {"type": "json_object"}
        payload["messages"][0]["content"] += "\n\nSchema:\n" + json.dumps(ANALYST_SCHEMA)
    return payload


def cost_usd(usage, provider):
    cached = usage.get("prompt_cache_hit_tokens") or usage.get("cached_tokens") or 0
    fresh = max(usage.get("prompt_tokens", 0) - cached, 0)
    return (
        fresh / 1e6 * provider["price_in_per_mtok"]
        + cached / 1e6 * provider["price_in_cached_per_mtok"]
        + usage.get("completion_tokens", 0) / 1e6 * provider["price_out_per_mtok"]
    )


class TruncatedError(Exception):
    """Output hit max_tokens, so the JSON is cut mid-string. This is OUR cap
    being too low, not the provider's schema being unreliable -- conflating the
    two would make the spike recommend the wrong provider."""


def one_call(url, headers, payload, timeout):
    t0 = time.perf_counter()
    r = requests.post(url, headers=headers, json=payload, timeout=timeout)
    latency = time.perf_counter() - t0
    if r.status_code != 200:
        # raise_for_status() throws away the response body, which is the only
        # place the vendor says WHY. A bare "400 Bad Request" cost a full run.
        try:
            detail = r.json().get("error", r.json())
            detail = detail.get("message", detail) if isinstance(detail, dict) else detail
        except ValueError:
            detail = r.text[:200]
        raise requests.HTTPError(f"HTTP {r.status_code}: {detail}")
    body = r.json()
    choice = body["choices"][0]
    if choice.get("finish_reason") == "length":
        raise TruncatedError(
            f"hit max_tokens={payload['max_tokens']}; raise llm.max_output_tokens "
            f"in config/xau.yaml (and re-check the cost model -- output is the "
            f"expensive side)"
        )
    parsed = json.loads(choice["message"]["content"])  # raises on malformed JSON
    validate(parsed, ANALYST_SCHEMA)                   # raises on schema violation
    return latency, parsed, body.get("usage", {})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", "--calls", type=int, default=5)
    ap.add_argument("-p", "--provider", default=None)
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    name, provider, cfg = load_provider(args.provider)
    key = os.getenv(provider["api_key_env"])
    if not key:
        sys.exit(
            f"{provider['api_key_env']} is not set.\n"
            f"  1. create the key in the {name} console\n"
            f"  2. copy .env.example to .env and paste it there"
        )

    strict = "yes" if provider.get("supports_strict_schema") else "NO (json mode only)"
    print(f"provider={name}  model={provider['model']}  base_url={provider['base_url']}")
    print(f"strict json_schema={strict}")
    print(f"calls={args.calls}\n")

    url = provider["base_url"].rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = build_payload(provider, cfg)

    # Pace to the provider's RPM cap. Without this the spike generates its own
    # 429s and reports them as provider unreliability -- the same misdiagnosis
    # trap as truncation-vs-schema-failure above.
    spacing = 60.0 / provider["rpm_limit"] + 1.0
    print(f"rpm_limit={provider['rpm_limit']} -> {spacing:.0f}s between calls "
          f"(~{spacing * args.calls / 60:.1f} min total)\n")

    latencies, costs, failures = [], [], []
    truncated = 0
    first = None
    for i in range(1, args.calls + 1):
        if i > 1:
            time.sleep(spacing)
        try:
            latency, parsed, usage = one_call(url, headers, payload, cfg["timeout_seconds"])
        except TruncatedError as e:
            truncated += 1
            print(f"  {i:>3}  TRUNCATED    {e}")
            continue
        except (json.JSONDecodeError, ValidationError) as e:
            failures.append(f"call {i}: schema/parse -- {type(e).__name__}: {e}")
            print(f"  {i:>3}  SCHEMA FAIL  {type(e).__name__}")
            continue
        except requests.RequestException as e:
            failures.append(f"call {i}: transport -- {type(e).__name__}: {e}")
            print(f"  {i:>3}  HTTP FAIL    {type(e).__name__}: {e}")
            continue
        latencies.append(latency)
        costs.append(cost_usd(usage, provider))
        first = first or parsed
        print(f"  {i:>3}  ok  {latency:6.2f}s  in={usage.get('prompt_tokens', '?')} "
              f"out={usage.get('completion_tokens', '?')}  ${costs[-1]:.5f}")

    ok = len(latencies)
    print(f"\n--- {ok}/{args.calls} passed schema validation ---")
    if ok:
        cap = cfg["max_calls_per_month"]
        avg = statistics.mean(costs)
        print(f"latency   median {statistics.median(latencies):.2f}s   max {max(latencies):.2f}s")
        print(f"cost/call ${avg:.5f}   ->  100 calls/mo = ${avg * 100:.2f}"
              f"   |  3,700 calls/mo = ${avg * 3700:.2f}   (budget $10/mo)")
        print(f"config cap: {cap} calls/mo = ${avg * cap:.2f}")
        print("\nfirst valid response:")
        print(json.dumps(first, indent=2, ensure_ascii=False))
    for f in failures:
        print("  !", f)

    # 16.8.1: this layer is only usable if structured output is actually reliable.
    return 0 if ok == args.calls else 1


if __name__ == "__main__":
    raise SystemExit(main())
