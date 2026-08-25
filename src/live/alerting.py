"""LINE Messaging API alerts — PROJECT_PLAN.md §18 "Alerting ครบ 4 ระดับ".

LINE Notify was shut down (end of March 2025) — this uses the LINE
Messaging API instead: a LINE Official Account's channel access token
pushes messages to a fixed userId/groupId via /v2/bot/message/push.

INFO/WARN not sent by default (would spam every 15-min NO_TRADE cycle) —
only ERROR/CRITICAL and actual trade events page. Adjust ALERT_LEVELS if
you want more/less noise.
"""
import os

import requests

CHANNEL_ACCESS_TOKEN_ENV = "LINE_CHANNEL_ACCESS_TOKEN"
TARGET_ID_ENV = "LINE_TARGET_ID"  # userId or groupId to push to
PUSH_URL = "https://api.line.me/v2/bot/message/push"
TIMEOUT_SEC = 10


def _send(content: str) -> bool:
    token = os.getenv(CHANNEL_ACCESS_TOKEN_ENV)
    target_id = os.getenv(TARGET_ID_ENV)
    if not token or not target_id:
        print(f"[alerting] {CHANNEL_ACCESS_TOKEN_ENV}/{TARGET_ID_ENV} not set, skipping alert: {content}")
        return False
    try:
        resp = requests.post(
            PUSH_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"to": target_id, "messages": [{"type": "text", "text": content}]},
            timeout=TIMEOUT_SEC,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        # alerting must never crash the signal cycle — log and move on
        print(f"[alerting] failed to send LINE alert: {e}")
        return False


def alert_trade_opened(symbol: str, action: str, qty: float, entry_price: float,
                        sl_price: float, tp_price: float | None, risk_pct: float) -> bool:
    tp_str = f"{tp_price:.2f}" if tp_price else "n/a"
    return _send(
        f"🟢 TRADE OPENED — {symbol}\n"
        f"{action} {qty} @ {entry_price:.2f} | SL {sl_price:.2f} | TP {tp_str} | risk {risk_pct:.2%}"
    )


def alert_trade_closed(symbol: str, exit_reason: str, exit_price: float, r_multiple: float) -> bool:
    emoji = "✅" if r_multiple > 0 else "❌"
    return _send(
        f"{emoji} TRADE CLOSED — {symbol}\n"
        f"exit={exit_reason} @ {exit_price:.2f} | result={r_multiple:+.2f}R"
    )


def alert_critical(message: str) -> bool:
    return _send(f"🚨 CRITICAL — {message}")


def alert_error(message: str) -> bool:
    return _send(f"⚠️ ERROR — {message}")
