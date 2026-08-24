"""Order execution — PROJECT_PLAN.md §12.2/§19.

Core principle: SL must be an exchange-native reduce-only stop-market order,
NOT a price level tracked in our own process memory. If our Python service
dies mid-position, the SL must still fire — that only works if the exchange
itself is holding the stop order, not us.
"""
import ccxt
from sqlalchemy.engine import Engine

from src.live.logging_store import log_signal, log_risk_decision, log_order, log_trade_open
from src.risk.sizing import ExchangeSpec, PositionRejected, compute_position_size


class OrderRejected(Exception):
    pass


def execute_signal_with_logging(
    exchange: ccxt.Exchange,
    engine: Engine,
    symbol: str,
    timeframe: str,
    action: str,
    regime: str,
    entry_price: float,
    sl_price: float,
    tp_price: float | None,
    risk_pct: float,
    equity: float,
    exchange_spec: ExchangeSpec,
) -> dict:
    """Full flow per §2/§9: log signal -> risk-check+size -> log decision ->
    execute -> log order -> log trade. Every step is logged BEFORE the next
    one happens, so a crash anywhere leaves a truthful trail, not a gap.
    """
    signal_id = log_signal(engine, symbol, timeframe, action, regime, sl_price, tp_price, risk_pct)

    try:
        qty = compute_position_size(equity, risk_pct, entry_price, sl_price, exchange_spec)
    except (PositionRejected, ValueError) as e:
        log_risk_decision(engine, signal_id, accepted=False, computed_qty=0.0,
                           equity_at_decision=equity, reject_layer="L6_SIZING", reject_reason=str(e))
        raise OrderRejected(f"risk sizing rejected: {e}") from e

    log_risk_decision(engine, signal_id, accepted=True, computed_qty=qty, equity_at_decision=equity)

    result = place_entry_with_sl(exchange, symbol, action, qty, sl_price)

    log_order(engine, signal_id, result["entry_order"]["id"], "entry",
              "buy" if action == "LONG" else "sell", qty, entry_price, result["entry_order"]["status"])
    log_order(engine, signal_id, result["sl_order"]["id"], "sl",
              "sell" if action == "LONG" else "buy", qty, sl_price, result["sl_order"]["status"],
              algo_order_id=result["sl_order"]["id"])

    trade_id = log_trade_open(engine, signal_id, symbol, entry_price, qty, sl_price, tp_price)

    return {**result, "signal_id": signal_id, "trade_id": trade_id, "qty": qty}


def place_entry_with_sl(
    exchange: ccxt.Exchange,
    symbol: str,
    action: str,      # "LONG" or "SHORT"
    qty: float,
    sl_price: float,
) -> dict:
    """Places a market entry, then a reduce-only stop-market SL. Returns both
    order responses. If the SL order fails to place, the entry is immediately
    closed — an unprotected position must never be left open (§9 principle:
    risk checks are not optional, ever).
    """
    side = "buy" if action == "LONG" else "sell"
    close_side = "sell" if action == "LONG" else "buy"

    entry_order = exchange.create_order(symbol, "market", side, qty)

    try:
        sl_order = exchange.create_order(
            symbol, "STOP_MARKET", close_side, qty,
            params={"stopPrice": sl_price, "reduceOnly": True},
        )
    except Exception as e:
        # unprotected position — close it immediately rather than leave it naked
        exchange.create_order(symbol, "market", close_side, qty, params={"reduceOnly": True})
        raise OrderRejected(f"SL placement failed, position force-closed to avoid unprotected exposure: {e}") from e

    return {"entry_order": entry_order, "sl_order": sl_order}


def fetch_open_algo_orders(exchange: ccxt.Exchange, symbol: str | None = None) -> list[dict]:
    """STOP_MARKET/TAKE_PROFIT_MARKET orders on Binance USDM futures are
    'conditional algo orders' with a SEPARATE id namespace (algoId, not
    orderId) — ccxt 4.7.0's fetch_open_orders/fetch_order do NOT see them.
    Discovered during §16 engineering testing: an SL placed via create_order
    looked successful (ccxt returned an id + status "open") but was
    invisible to fetch_open_orders and fetch_order raised OrderNotFound.

    Any reconciliation logic (§19) MUST call this too, or it will falsely
    conclude a protected position has no SL.
    """
    params = {"symbol": symbol.split("/")[0].replace(":USDT", "") + "USDT"} if symbol else {}
    raw = exchange.fapiPrivateGetOpenAlgoOrders(params)
    return raw


def cancel_all_and_flatten(exchange: ccxt.Exchange, symbol: str) -> None:
    """Emergency flatten: cancel all open orders (regular AND algo/conditional),
    close any open position at market. Used for cleanup after tests and as a
    kill-switch primitive (§9.3)."""
    open_orders = exchange.fetch_open_orders(symbol)
    for order in open_orders:
        exchange.cancel_order(order["id"], symbol)

    algo_orders = fetch_open_algo_orders(exchange, symbol)
    for algo in algo_orders:
        exchange.fapiPrivateDeleteAlgoOrder({"algoId": algo["algoId"]})

    positions = exchange.fetch_positions([symbol])
    for pos in positions:
        contracts = pos.get("contracts") or 0
        if contracts:
            side = "sell" if pos["side"] == "long" else "buy"
            exchange.create_order(symbol, "market", side, abs(contracts), params={"reduceOnly": True})
