import os
import time
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# Store these in Render Environment Variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

recent_events = {}
DUPLICATE_WINDOW_SECONDS = 30


def clean_num(value):
    if value is None:
        return "N/A"
    try:
        num = float(value)
        return f"{num:.3f}".rstrip("0").rstrip(".")
    except Exception:
        return str(value)


def clean_lot(value):
    if value is None:
        return "N/A"
    try:
        num = float(value)
        return f"{num:.2f}"
    except Exception:
        return str(value)


def is_duplicate(event_id):
    now = time.time()

    old_keys = [
        key for key, timestamp in recent_events.items()
        if now - timestamp > DUPLICATE_WINDOW_SECONDS
    ]

    for key in old_keys:
        del recent_events[key]

    if event_id in recent_events:
        return True

    recent_events[event_id] = now
    return False


def format_entry_message(data):
    side = data.get("side", "UNKNOWN")

    return (
        f"XAUUSD {side} SIGNAL\n"
        f"Trade: {side}\n\n"
        f"Entry: {clean_num(data.get('entry'))}\n"
        f"Lot Size: {clean_lot(data.get('lot_size'))}\n"
        f"Risk: ${clean_num(data.get('risk_usd'))}\n"
        f"SL: {clean_num(data.get('sl'))}\n"
        f"TP1: {clean_num(data.get('tp1'))}\n"
        f"TP2: {clean_num(data.get('tp2'))}\n"
        f"TP3: {clean_num(data.get('tp3'))}\n"
        f"TP3.5: {clean_num(data.get('tp35'))}\n"
        f"Strategy: {data.get('version', 'v1.5J-RENDER')}\n"
        f"Timeframe: {data.get('timeframe', '15m')}"
    )


def format_level_message(data):
    side = data.get("side", "UNKNOWN")
    event = data.get("event", "unknown")
    version = data.get("version", "v1.5J-RENDER")
    timeframe = data.get("timeframe", "15m")
    price = clean_num(data.get("price"))

    event_labels = {
        "tp1_hit": "TP1 HIT",
        "tp2_hit": "TP2 HIT",
        "tp3_hit": "TP3 HIT",
        "tp35_hit": "TP3.5 HIT / FINAL TARGET",
        "sl_hit": "SL HIT",
        "time_exit": "TIME EXIT",
    }

    label = event_labels.get(event, event.upper())

    return (
        f"XAUUSD {side} {label}\n"
        f"Price: {price}\n"
        f"Strategy: {version}\n"
        f"Timeframe: {timeframe}"
    )


def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")

    if not TELEGRAM_CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_CHAT_ID")

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "disable_web_page_preview": True,
    }

    response = requests.post(url, json=payload, timeout=10)
    response.raise_for_status()

    return response.json()


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "ok": True,
        "status": "online",
        "service": "XAU v1.5J Telegram Webhook"
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "ok": True,
        "status": "healthy"
    })


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True, silent=False)

        if not isinstance(data, dict):
            return jsonify({"ok": False, "error": "Invalid JSON"}), 400

        event = data.get("event")
        side = data.get("side")
        trade_id = data.get("trade_id", "no_trade_id")

        if not event:
            return jsonify({"ok": False, "error": "Missing event"}), 400

        event_id = f"{trade_id}_{event}"

        if is_duplicate(event_id):
            return jsonify({
                "ok": True,
                "duplicate": True,
                "event": event,
                "side": side
            }), 200

        if event == "entry":
            message = format_entry_message(data)
        elif event in ["tp1_hit", "tp2_hit", "tp3_hit", "tp35_hit", "sl_hit", "time_exit"]:
            message = format_level_message(data)
        else:
            return jsonify({
                "ok": False,
                "error": f"Unknown event: {event}"
            }), 400

        telegram_response = send_telegram(message)

        return jsonify({
            "ok": True,
            "event": event,
            "side": side,
            "telegram": telegram_response
        }), 200

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
