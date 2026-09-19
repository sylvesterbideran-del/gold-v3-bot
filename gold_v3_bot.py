"""
GOLD V3 - EMA 9 / 21 / 50 + RSI + Pullback + 3% Tokevedelem
Telegram jelzo + /status endpoint felhohoz
Python 3.10+
"""

import os
import time
import requests
import pandas as pd
import threading
from datetime import datetime
from flask import Flask, jsonify

# ================= KONFIG - 1-ES VALASZTAS - IDE IRD AZ ID-KAT =================
# Egyszeruen ide ird be es mentsd el igy: gold_v3_bot.py
TELEGRAM_TOKEN = "8990882185:AAFqtCm9ZDHk62-n9vhFcg4Rv6QlK99wE6A"
TELEGRAM_CHAT_ID = "7995386347"
# ================= KONFIG VEGE =================

# Trading beallitasok - ne piszkald
BINANCE_SYMBOL = "PAXGUSDT"
INTERVAL = "2m"
EMA_FAST = 9
EMA_MID = 21
EMA_SLOW = 50
RSI_PERIOD = 14
RSI_LONG_MIN = 55
RSI_SHORT_MAX = 45
TOKE_BUKO_PERCENT = 3.0
LEVERAGE = 200

# ================= STATUS TAROLO =================
bot_status = {
    "bot": "GOLD V3 - EMA 9/21/50",
    "fut": True,
    "allapot": "✅ Fut",
    "utolso_ellenorzes": "még nem futott",
    "utolso_jel": "még nincs jel",
    "mai_jelek": 0,
    "toke_vedelem": f"{TOKE_BUKO_PERCENT}% aktiv ({LEVERAGE}x)",
    "ema_beallitas": f"{EMA_FAST} / {EMA_MID} / {EMA_SLOW}",
    "szimbolum": BINANCE_SYMBOL,
    "idokeret": INTERVAL,
    "frissitve": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
}

# ================= FLASK STATUS ENDPOINT =================
app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({"uzenet": "Gold V3 fut", "status_link": "/status"})

@app.route("/status")
def status():
    bot_status["frissitve"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return jsonify(bot_status)

def start_flask():
    # Railway / Render automatikusan ad PORT-ot
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

# ================= SEGEDFUGGVENYEK =================
def send_telegram(uzenet):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[TELEGRAM SKIP - NINCS TOKEN/CHAT_ID] {uzenet}")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": uzenet}, timeout=10)
    except Exception as e:
        print(f"Telegram hiba: {e}")

def get_klines(limit=200):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={BINANCE_SYMBOL}&interval={INTERVAL}&limit={limit}"
        r = requests.get(url, timeout=10).json()
        df = pd.DataFrame(r, columns=["time","open","high","low","close","vol","ct","qvol","trades","taker_base","taker_quote","ignore"])
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        return df
    except Exception as e:
        print(f"Binance hiba: {e}")
        return None

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def analyze():
    df = get_klines()
    if df is None or len(df) < 60:
        return None

    df["ema9"] = df["close"].ewm(span=EMA_FAST).mean()
    df["ema21"] = df["close"].ewm(span=EMA_MID).mean()
    df["ema50"] = df["close"].ewm(span=EMA_SLOW).mean()
    df["rsi"] = calc_rsi(df["close"], RSI_PERIOD)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    bot_status["utolso_ellenorzes"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bot_status["aktualis_ar"] = float(last["close"])
    bot_status["rsi"] = round(float(last["rsi"]), 2) if pd.notna(last["rsi"]) else None

    # Trend szures
    uptrend = last["ema9"] > last["ema21"] > last["ema50"]
    downtrend = last["ema9"] < last["ema21"] < last["ema50"]

    # Pullback: ar visszahuz EMA21-ig
    pullback_long = abs(last["close"] - last["ema21"]) / last["close"] < 0.0015 and last["close"] > last["ema21"]
    pullback_short = abs(last["close"] - last["ema21"]) / last["close"] < 0.0015 and last["close"] < last["ema21"]

    jel = None

    if uptrend and pullback_long and last["rsi"] > RSI_LONG_MIN:
        jel = "LONG"
    elif downtrend and pullback_short and last["rsi"] < RSI_SHORT_MAX:
        jel = "SHORT"

    # Zarasi logika
    trend_vege_long = last["close"] < last["ema21"] or last["rsi"] < 45
    trend_vege_short = last["close"] > last["ema21"] or last["rsi"] > 55

    return {
        "ar": float(last["close"]),
        "ema9": float(last["ema9"]),
        "ema21": float(last["ema21"]),
        "ema50": float(last["ema50"]),
        "rsi": float(last["rsi"]),
        "uptrend": uptrend,
        "downtrend": downtrend,
        "jel": jel,
        "trend_vege_long": trend_vege_long,
        "trend_vege_short": trend_vege_short
    }

# ================= FO CIKLUS =================
def main_loop():
    print(f"🚀 GOLD V3 indul - EMA {EMA_FAST}/{EMA_MID}/{EMA_SLOW} - {TOKE_BUKO_PERCENT}% tokevedelem")
    send_telegram(f"🚀 GOLD V3 elindult\nEMA {EMA_FAST}/{EMA_MID}/{EMA_SLOW} | {TOKE_BUKO_PERCENT}% stop | {BINANCE_SYMBOL}")

    while True:
        try:
            res = analyze()
            if not res:
                time.sleep(30)
                continue

            print(f"[{bot_status['utolso_ellenorzes']}] Ar: {res['ar']:.2f} | RSI: {res['rsi']:.1f} | Trend: {'UP' if res['uptrend'] else 'DOWN' if res['downtrend'] else 'OLDAL'}")

            if res["jel"]:
                bot_status["mai_jelek"] += 1
                bot_status["utolso_jel"] = f"{res['jel']} {res['ar']:.2f} - {datetime.now().strftime('%H:%M:%S')}"

                # Stop szamitas 20x-re
                stop_tav_ar_percent = TOKE_BUKO_PERCENT / LEVERAGE  # 3%/20 = 0.15%
                if res["jel"] == "LONG":
                    stop_ar = res["ar"] * (1 - stop_tav_ar_percent/100)
                else:
                    stop_ar = res["ar"] * (1 + stop_tav_ar_percent/100)

                uzenet = f"""
🟢 {res['jel']} JEL - GOLD V3
💰 Ár: {res['ar']:.2f}
📊 EMA9: {res['ema9']:.2f} | EMA21: {res['ema21']:.2f} | EMA50: {res['ema50']:.2f}
📈 RSI: {res['rsi']:.1f}
🛡️ Stop: {stop_ar:.2f} (-{TOKE_BUKO_PERCENT}% tőke / -{stop_tav_ar_percent:.2f}% ár)
⏰ Idő: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
🔗 /status élő
                """
                send_telegram(uzenet)
                # Anti-spam: jel utan varj 5 percet
                time.sleep(300)

            time.sleep(120)  # 2 percenkent ellenorzes

        except Exception as e:
            print(f"Hiba a loopban: {e}")
            bot_status["allapot"] = f"⚠️ Hiba: {e}"
            time.sleep(30)

# ================= INDITAS =================
if __name__ == "__main__":
    # Flask kulon szalon
    t = threading.Thread(target=start_flask, daemon=True)
    t.start()
    # Bot fo ciklus
    main_loop()
