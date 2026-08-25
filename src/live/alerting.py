"""Discord webhook alerts — PROJECT_PLAN.md §18 "Alerting ครบ 4 ระดับ".

INFO/WARN not sent by default (would spam every 15-min NO_TRADE cycle) —
only ERROR/CRITICAL and actual trade events page. Adjust ALERT_LEVELS if
you want more/less noise.
"""
import os

import requests

WEBHOOK_URL_ENV = "DISCORD_WEBHOOK_URL"
TIMEOUT_SEC = 10


def _send(content: str) -> bool:
    webhook_url = os.getenv(WEBHOOK_URL_ENV)
    if not webhook_url:
        print(f"[alerting] {WEBHOOK_URL_ENV} not set, skipping alert: {content}")
        return False
    try:
        resp = requests.post(webhook_url, json={"content": content}, timeout=TIMEOUT_SEC)
        resp.raise_for_status()
        return True
    except Exception as e:
        # alerting must never crash the signal cycle — log and move on
        print(f"[alerting] failed to send Discord alert: {e}")
        return False


def alert_trade_opened(symbol: str, action: str, qty: float, entry_price: float,
                        sl_price: float, tp_price: float | None, risk_pct: float) -> None:
    tp_str = f"{tp_price:.2f}" if tp_price else "n/a"
    _send(
        f"🟢 **TRADE OPENED** — {symbol}\n"
        f"{action} {qty} @ {entry_price:.2f} | SL {sl_price:.2f} | TP {tp_str} | risk {risk_pct:.2%}"
    )


def alert_trade_closed(symbol: str, exit_reason: str, exit_price: float, r_multiple: float) -> None:
    emoji = "✅" if r_multiple > 0 else "❌"
    _send(
        f"{emoji} **TRADE CLOSED** — {symbol}\n"
        f"exit={exit_reason} @ {exit_price:.2f} | result={r_multiple:+.2f}R"
    )


def alert_critical(message: str) -> None:
    _send(f"🚨 **CRITICAL** — {message}")


def alert_error(message: str) -> None:
    _send(f"⚠️ **ERROR** — {message}")
