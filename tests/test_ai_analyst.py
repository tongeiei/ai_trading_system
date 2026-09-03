"""Tests for src/ai/analyst.py. No real network calls -- requests.post is
monkeypatched throughout, per docs/XAU_ARCHITECTURE_AUDIT.md P6's
"structured output must be validated for real" requirement, without spending
the (real, billed) API budget on every test run."""
import json

import pytest
import yaml

from src.ai import analyst as az


VALID_BODY = {
    "veto": False, "veto_reason": "", "thesis": "trend continuation",
    "invalidation": "close below swing low", "risk_factors": ["thin liquidity"],
}


def _response(status_code=200, content=None, finish_reason="stop", usage=None):
    class _Resp:
        def __init__(self):
            self.status_code = status_code
            self._content = content
            self._finish_reason = finish_reason
            self._usage = usage or {"prompt_tokens": 500, "completion_tokens": 100}

        def json(self):
            if self.status_code != 200:
                return {"error": {"message": "bad request"}}
            return {
                "choices": [{
                    "message": {"content": json.dumps(self._content or VALID_BODY)},
                    "finish_reason": self._finish_reason,
                }],
                "usage": self._usage,
            }

        @property
        def text(self):
            return json.dumps(self.json())

    return _Resp()


@pytest.fixture
def enabled_config(tmp_path, monkeypatch):
    cfg = {
        "llm": {
            "active": "kimi",
            "max_calls_per_month": 300, "timeout_seconds": 90, "max_retries": 1,
            "on_failure": "deterministic_only", "max_output_tokens": 4000,
            "max_input_chars": 24000, "max_calls_per_day": 20, "enabled": True,
            "providers": {
                "kimi": {
                    "base_url": "https://api.moonshot.ai/v1", "model": "kimi-k3",
                    "api_key_env": "MOONSHOT_API_KEY", "supports_strict_schema": True,
                    "temperature": 1, "rpm_limit": 3,
                    "price_in_per_mtok": 3.0, "price_in_cached_per_mtok": 0.3,
                    "price_out_per_mtok": 15.0,
                },
                "deepseek": {
                    "base_url": "https://api.deepseek.com/v1", "model": "deepseek-v4-flash",
                    "api_key_env": "DEEPSEEK_API_KEY", "supports_strict_schema": False,
                    "temperature": 0, "rpm_limit": 60,
                    "price_in_per_mtok": 0.14, "price_in_cached_per_mtok": 0.0028,
                    "price_out_per_mtok": 0.28,
                },
            },
        }
    }
    path = tmp_path / "xau.yaml"
    path.write_text(yaml.dump(cfg), encoding="utf-8")
    monkeypatch.setattr(az, "CONFIG_PATH", path)
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-ds")
    return cfg


def _scorecard():
    return az.ScorecardInput(
        symbol="XAUUSD", timeframe="M15", direction="LONG", setup_name="liquidity_sweep",
        trend=82, structure=76, momentum=71, volatility=88, session=91, risk=85,
        final_score=82, context="London open, spread 26 points",
    )


def test_review_disabled_raises(tmp_path, monkeypatch):
    cfg = {"llm": {"active": "kimi", "enabled": False, "providers": {"kimi": {}}}}
    path = tmp_path / "xau.yaml"
    path.write_text(yaml.dump(cfg), encoding="utf-8")
    monkeypatch.setattr(az, "CONFIG_PATH", path)
    with pytest.raises(az.AnalystDisabledError):
        az.review(_scorecard())


def test_review_missing_api_key_raises(enabled_config, monkeypatch):
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    with pytest.raises(az.AnalystConfigError):
        az.review(_scorecard())


def test_review_unknown_provider_raises(enabled_config):
    with pytest.raises(az.AnalystConfigError):
        az.review(_scorecard(), provider="not-a-real-provider")


def test_review_success_strict_schema_provider(enabled_config, monkeypatch):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append((url, json))
        return _response()

    monkeypatch.setattr(az.requests, "post", fake_post)
    result = az.review(_scorecard())

    assert result.ok
    assert result.veto is False
    assert result.thesis == "trend continuation"
    assert result.attempts == 1
    assert result.cost_usd > 0
    assert "response_format" in calls[0][1]
    assert calls[0][1]["response_format"]["type"] == "json_schema"


def test_review_json_mode_fallback_provider_appends_schema(enabled_config, monkeypatch):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append((url, json))
        return _response()

    monkeypatch.setattr(az.requests, "post", fake_post)
    result = az.review(_scorecard(), provider="deepseek")

    assert result.ok
    assert calls[0][1]["response_format"] == {"type": "json_object"}
    assert "Schema:" in calls[0][1]["messages"][0]["content"]


def test_review_retries_once_on_429_then_succeeds(enabled_config, monkeypatch):
    responses = [_response(status_code=429), _response()]

    def fake_post(url, headers, json, timeout):
        return responses.pop(0)

    monkeypatch.setattr(az.requests, "post", fake_post)
    result = az.review(_scorecard())

    assert result.ok
    assert result.attempts == 2


def test_review_gives_up_after_max_retries(enabled_config, monkeypatch):
    def fake_post(url, headers, json, timeout):
        return _response(status_code=503)

    monkeypatch.setattr(az.requests, "post", fake_post)
    result = az.review(_scorecard())  # max_retries=1 -> 2 attempts total

    assert not result.ok
    assert result.attempts == 2
    assert "503" in result.error


def test_review_does_not_retry_non_retryable_http_error(enabled_config, monkeypatch):
    def fake_post(url, headers, json, timeout):
        return _response(status_code=400)

    monkeypatch.setattr(az.requests, "post", fake_post)
    result = az.review(_scorecard())

    assert not result.ok
    assert result.attempts == 1


def test_review_truncated_output_not_retried(enabled_config, monkeypatch):
    def fake_post(url, headers, json, timeout):
        return _response(finish_reason="length")

    monkeypatch.setattr(az.requests, "post", fake_post)
    result = az.review(_scorecard())

    assert not result.ok
    assert result.attempts == 1
    assert "max_tokens" in result.error


def test_review_schema_violation_is_retried(enabled_config, monkeypatch):
    bad = {"veto": False}  # missing required fields
    responses = [_response(content=bad), _response()]

    def fake_post(url, headers, json, timeout):
        return responses.pop(0)

    monkeypatch.setattr(az.requests, "post", fake_post)
    result = az.review(_scorecard())

    assert result.ok
    assert result.attempts == 2


def test_cost_usd_accounts_for_cached_tokens():
    provider = {"price_in_per_mtok": 3.0, "price_in_cached_per_mtok": 0.3, "price_out_per_mtok": 15.0}
    usage = {"prompt_tokens": 1000, "prompt_cache_hit_tokens": 400, "completion_tokens": 200}
    cost = az._cost_usd(usage, provider)
    expected = (600 / 1e6 * 3.0) + (400 / 1e6 * 0.3) + (200 / 1e6 * 15.0)
    assert cost == pytest.approx(expected)
