#!/bin/bash
# Resume the BTC orderbook collector after the machine was off/restarted.
# Safe to run even if a collector is already running (checks first).
set -e
cd "$(dirname "$0")/.."

if pgrep -f "collect_btc_orderbook.py" > /dev/null; then
    echo "Collector already running (PID $(pgrep -f collect_btc_orderbook.py))."
    exit 0
fi

nohup .venv/bin/python scripts/collect_btc_orderbook.py 5 > /tmp/btc_ob_collector.log 2>&1 &
disown
sleep 2
echo "Started collector, PID $(pgrep -f collect_btc_orderbook.py)"
tail -n 5 /tmp/btc_ob_collector.log
