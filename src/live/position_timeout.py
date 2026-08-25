"""12h position timeout — mirrors triple_barrier.MAX_HOLD_BARS_M1 (§4.3) on
the live side. The exchange has no native "close after N hours" order type,
so this has to be enforced by the signal cycle checking on each run.

§16 bug: without this, live positions only ever exited via SL — never
matching the backtest's TIMEOUT-labeled outcomes (about 1 in 6 trades in
the historical data, see docs/FINDINGS.md).
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.engine import Engine

from src.data.db import trades as trades_table
from src.live.logging_store import log_trade_close
from src.live.order_executor import cancel_all_and_flatten

MAX_HOLD = timedelta(hours=12)  # matches triple_barrier.MAX_HOLD_BARS_M1


def close_expired_positions(exchange, engine: Engine, symbol: str) -> list[str]:
    """Force-closes any open trade (exit_time_utc is null) whose entry was
    more than MAX_HOLD ago. Returns list of trade_ids closed this call.
    """
    now = datetime.now(timezone.utc)
    with engine.connect() as conn:
        open_trades = conn.execute(
            select(trades_table).where(trades_table.c.exit_time_utc.is_(None))
        ).fetchall()

    closed_ids = []
    for trade in open_trades:
        entry_time = trade.entry_time_utc
        if entry_time.tzinfo is None:
            entry_time = entry_time.replace(tzinfo=timezone.utc)
        age = now - entry_time
        if age < MAX_HOLD:
            continue

        # position + protective orders are exchange-native; flatten cancels both
        ticker = exchange.fetch_ticker(symbol)
        exit_price = ticker["last"]
        cancel_all_and_flatten(exchange, symbol)

        sl_distance = abs(trade.entry_price - trade.sl_price)
        # trades table has no action column; infer direction from SL side —
        # LONG's SL sits below entry, SHORT's SL sits above (see v0_rules.py)
        is_long = trade.sl_price < trade.entry_price
        diff = (exit_price - trade.entry_price) if is_long else (trade.entry_price - exit_price)
        r_multiple = diff / sl_distance if sl_distance else 0.0
        net_pnl = diff * trade.qty

        log_trade_close(engine, trade.trade_id, exit_price, "TIMEOUT", net_pnl, r_multiple)
        closed_ids.append(trade.trade_id)
        print(f"TIMEOUT close: trade_id={trade.trade_id}, age={age}, exit_price={exit_price}, r_multiple={r_multiple:.3f}")

    return closed_ids
