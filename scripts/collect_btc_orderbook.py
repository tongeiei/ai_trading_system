"""Continuous BTC/USDT perp L2 order-book + trade-flow collector.

Forward-only data acquisition — orderbook depth cannot be backfilled, so
this needs to run for weeks/months before there's enough history for
research (see docs/research/BTC_EDGE_SEARCH.md Round 3's closing note).
Polls REST snapshots (not a websocket feed) for simplicity; sub-second
microstructure will be missed, but 5s resolution is enough for a first
pass at depth-imbalance / short-horizon drift research.

Writes one row per poll to a daily CSV (append), auto-rotating at UTC
midnight: data/raw/orderbook/BTCUSDT_orderbook_YYYY-MM-DD.csv

Run continuously (e.g. via cron/systemd/nohup), not just for the length
of one chat session:
    nohup .venv/bin/python scripts/collect_btc_orderbook.py > /tmp/btc_ob_collector.log 2>&1 &

Usage:
    python scripts/collect_btc_orderbook.py [poll_seconds]
"""
import csv
import sys
import time
import datetime as dt
from pathlib import Path

import ccxt

OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "raw" / "orderbook"
SYMBOL = "BTC/USDT"
DEPTH = 20
FIELDS = [
    "time_utc", "best_bid", "best_ask", "mid", "spread",
    "bid_qty_top5", "ask_qty_top5", "bid_qty_top20", "ask_qty_top20",
    "depth_imbalance_top5", "depth_imbalance_top20",
    "last_trade_price", "last_trade_side",
]


def current_path(now: dt.datetime) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUT_DIR / f"BTCUSDT_orderbook_{now.strftime('%Y-%m-%d')}.csv"


def poll_once(ex, writer):
    ob = ex.fetch_order_book(SYMBOL, limit=DEPTH)
    now = dt.datetime.now(dt.timezone.utc)
    bids, asks = ob["bids"], ob["asks"]
    if not bids or not asks:
        return
    best_bid, best_ask = bids[0][0], asks[0][0]
    mid = (best_bid + best_ask) / 2
    bid_q5 = sum(q for _, q in bids[:5])
    ask_q5 = sum(q for _, q in asks[:5])
    bid_q20 = sum(q for _, q in bids[:20])
    ask_q20 = sum(q for _, q in asks[:20])
    imb5 = (bid_q5 - ask_q5) / (bid_q5 + ask_q5) if (bid_q5 + ask_q5) > 0 else 0.0
    imb20 = (bid_q20 - ask_q20) / (bid_q20 + ask_q20) if (bid_q20 + ask_q20) > 0 else 0.0

    trades = ex.fetch_trades(SYMBOL, limit=1)
    last_price = trades[-1]["price"] if trades else None
    last_side = trades[-1]["side"] if trades else None

    writer.writerow({
        "time_utc": now.isoformat(), "best_bid": best_bid, "best_ask": best_ask,
        "mid": mid, "spread": best_ask - best_bid,
        "bid_qty_top5": bid_q5, "ask_qty_top5": ask_q5,
        "bid_qty_top20": bid_q20, "ask_qty_top20": ask_q20,
        "depth_imbalance_top5": imb5, "depth_imbalance_top20": imb20,
        "last_trade_price": last_price, "last_trade_side": last_side,
    })


def main(poll_seconds: float = 5.0):
    ex = ccxt.binanceusdm({"enableRateLimit": True})
    print(f"Collecting {SYMBOL} orderbook every {poll_seconds}s -> {OUT_DIR}")
    cur_date = None
    f = None
    writer = None
    n = 0
    t_report = time.time()
    while True:
        now = dt.datetime.now(dt.timezone.utc)
        if now.date() != cur_date:
            if f:
                f.close()
            cur_date = now.date()
            path = current_path(now)
            is_new = not path.exists()
            f = open(path, "a", newline="")
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            if is_new:
                writer.writeheader()
            print(f"  rotated to {path}")
        try:
            poll_once(ex, writer)
            f.flush()
            n += 1
        except Exception as e:
            print(f"  poll error: {e}", file=sys.stderr)
        if time.time() - t_report > 300:
            print(f"  {n} polls written so far (latest file: {current_path(now).name})")
            t_report = time.time()
        time.sleep(poll_seconds)


if __name__ == "__main__":
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    main(secs)
