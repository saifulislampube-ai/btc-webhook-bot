from flask import Flask, request, jsonify
from pybit.unified_trading import HTTP
import os

app = Flask(__name__)

API_KEY = os.environ.get("BYBIT_API_KEY", "")
API_SECRET = os.environ.get("BYBIT_API_SECRET", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "mysecret123")
TESTNET = os.environ.get("TESTNET", "true").lower() == "true"

session = HTTP(
    testnet=TESTNET,
    api_key=API_KEY,
    api_secret=API_SECRET,
)

def get_balance():
    try:
        result = session.get_wallet_balance(accountType="CONTRACT", coin="USDT")
        balance = result["result"]["list"][0]["coin"][0]["availableToWithdraw"]
        return float(balance)
    except Exception as e:
        print(f"Balance error: {e}")
        return 0

def calculate_qty(symbol, usdt_amount, leverage=5):
    try:
        ticker = session.get_tickers(category="linear", symbol=symbol)
        price = float(ticker["result"]["list"][0]["lastPrice"])
        qty = (usdt_amount * leverage) / price
        if "BTC" in symbol:
            qty = round(qty, 3)
        elif "ETH" in symbol:
            qty = round(qty, 2)
        else:
            qty = round(qty, 1)
        return qty, price
    except Exception as e:
        print(f"Qty error: {e}")
        return 0, 0

def set_leverage(symbol, leverage):
    try:
        session.set_leverage(
            category="linear",
            symbol=symbol,
            buyLeverage=str(leverage),
            sellLeverage=str(leverage),
        )
    except Exception as e:
        print(f"Leverage error: {e}")

def place_order(symbol, side, qty, sl_percent=1.5, tp_percent=3.0, leverage=5):
    try:
        set_leverage(symbol, leverage)
        ticker = session.get_tickers(category="linear", symbol=symbol)
        price = float(ticker["result"]["list"][0]["lastPrice"])
        if side == "Buy":
            sl_price = round(price * (1 - sl_percent / 100), 2)
            tp_price = round(price * (1 + tp_percent / 100), 2)
        else:
            sl_price = round(price * (1 + sl_percent / 100), 2)
            tp_price = round(price * (1 - tp_percent / 100), 2)
        result = session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            orderType="Market",
            qty=str(qty),
            stopLoss=str(sl_price),
            takeProfit=str(tp_price),
            slTriggerBy="MarkPrice",
            tpTriggerBy="MarkPrice",
        )
        return result
    except Exception as e:
        return {"error": str(e)}

def close_position(symbol):
    try:
        pos = session.get_positions(category="linear", symbol=symbol)
        positions = pos["result"]["list"]
        if not positions or float(positions[0]["size"]) == 0:
            return {"msg": "No open position"}
        size = positions[0]["size"]
        side = positions[0]["side"]
        close_side = "Sell" if side == "Buy" else "Buy"
        result = session.place_order(
            category="linear",
            symbol=symbol,
            side=close_side,
            orderType="Market",
            qty=size,
            reduceOnly=True,
        )
        return result
    except Exception as e:
        return {"error": str(e)}

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if not data:
        return jsonify({"error": "No data"}), 400
    if data.get("secret") != WEBHOOK_SECRET:
        return jsonify({"error": "Unauthorized"}), 403
    action = data.get("action", "").lower()
    symbol = data.get("symbol", "BTCUSDT")
    risk_percent = float(data.get("risk_percent", 2))
    leverage = int(data.get("leverage", 5))
    sl_percent = float(data.get("sl_percent", 1.5))
    tp_percent = float(data.get("tp_percent", 3.0))
    if action == "close":
        result = close_position(symbol)
        return jsonify({"status": "closed", "result": result})
    if action in ["buy", "sell"]:
        balance = get_balance()
        if balance < 10:
            return jsonify({"error": f"Low balance: {balance}"}), 400
        usdt_to_use = balance * (risk_percent / 100)
        qty, price = calculate_qty(symbol, usdt_to_use, leverage)
        if qty <= 0:
            return jsonify({"error": "Qty error"}), 400
        side = "Buy" if action == "buy" else "Sell"
        result = place_order(symbol, side, qty, sl_percent, tp_percent, leverage)
        return jsonify({"status": "order_placed", "qty": qty, "price": price})
    return jsonify({"error": "Unknown action"}), 400

@app.route("/status", methods=["GET"])
def status():
    balance = get_balance()
    return jsonify({"status": "running", "testnet": TESTNET, "balance_usdt": balance})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
