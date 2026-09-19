import time
import requests
import pandas as pd
import threading
from datetime import datetime
from flask import Flask, jsonify
from flask_cors import CORS
import os

BINANCE_SYMBOL = "PAXGUSDT"
INTERVAL = "2m"
EMA_FAST = 9
EMA_MID = 21
EMA_SLOW = 50
RSI_PERIOD = 14
RSI_LONG_MIN = 55
RSI_SHORT_MAX = 45
TOKE_BUKO_PERCENT = 3.0
LEVERAGE = 20

TELEGRAM_TOKEN = "8990882185:AAFqtCm9ZDHk62-n9vhFcg4Rv6QlK99wE6A"
TELEGRAM_CHAT_ID = "7995386347"

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

app = Flask(__name__)
CORS(app)

@app.route("/")
def home():
    try:
        with open("status.html", "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return jsonify({"uzenet": "Gold V3 fut", "status_link": "/status", "hiba": str(e), "tipp": "status.html nincs a repo-ban!"})

@app.route("/status")
def status():
    bot_status["frissitve"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    resp = jsonify(bot_status)
    resp.headers.add('Access-Control-Allow-Origin', '*')
    return resp

@app.route("/status.html")
def status_html_file():
    try:
        with open("status.html", "r", encoding="utf-8") as f:
            return f.read()
    except:
        return "status.html nem található", 404

def start_flask():
    port = int(os.environ.get("PORT", 5000))
    print(f"Flask indul port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)

def send_telegram(uzenet):
    if "IDE_A_TOKENOD" in TELEGRAM_TOKEN:
        print(f"[TELEGRAM SKIP] {uzenet}")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": uzenet}, timeout=10)
    except Exception as e:
        print(f"Telegram hiba: {e}")

def get_klines(limit=200):
    try:
        # Render-en a api.binance.com blokkolt, ezért data-api kell!
        url = f"https://data-api.binance.vision/api/v3/klines?symbol={BINANCE_SYMBOL}&interval={INTERVAL}&limit={limit}"
        r = requests.get(url, timeout=10).json()
        df = pd.DataFrame(r, columns=["time","open","high","low","close","vol","ct","qvol","trades","taker_base","taker_quote","ignore"])
        df["close"] = df["close"].astype(float)
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
    bot_status["utolso_ellenorzes"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bot_status["aktualis_ar"] = float(last["close"])
    bot_status["rsi"] = round(float(last["rsi"]), 2) if pd.notna(last["rsi"]) else None
    uptrend = last["ema9"] > last["ema21"] > last["ema50"]
    downtrend = last["ema9"] < last["ema21"] < last["ema50"]
    pullback_long = abs(last["close"] - last["ema21"]) / last["close"] < 0.0015 and last["close"] > last["ema21"]
    pullback_short = abs(last["close"] - last["ema21"]) / last["close"] < 0.0015 and last["close"] < last["ema21"]
    jel = None
    if uptrend and pullback_long and last["rsi"] > RSI_LONG_MIN:
        jel = "LONG"
    elif downtrend and pullback_short and last["rsi"] < RSI_SHORT_MAX:
        jel = "SHORT"
    return {"ar": float(last["close"]), "ema9": float(last["ema9"]), "ema21": float(last["ema21"]), "ema50": float(last["ema50"]), "rsi": float(last["rsi"]), "uptrend": uptrend, "downtrend": downtrend, "jel": jel}

def main_loop():
    print(f"GOLD V3 indul")
    send_telegram(f"GOLD V3 elindult EMA {EMA_FAST}/{EMA_MID}/{EMA_SLOW}")
    while True:
        try:
            res = analyze()
            if not res:
                time.sleep(30)
                continue
            print(f"[{bot_status['utolso_ellenorzes']}] Ar: {res['ar']:.2f} RSI: {res['rsi']:.1f}")
            if res["jel"]:
                bot_status["mai_jelek"] += 1
                bot_status["utolso_jel"] = f"{res['jel']} {res['ar']:.2f} - {datetime.now().strftime('%H:%M:%S')}"
                stop_pct = TOKE_BUKO_PERCENT / LEVERAGE
                stop_ar = res["ar"] * (1 - stop_pct/100) if res["jel"]=="LONG" else res["ar"] * (1 + stop_pct/100)
                uzenet = f"🟢 {res['jel']} JEL - GOLD V3\n💰 Ár: {res['ar']:.2f}\nRSI: {res['rsi']:.1f}\n🛡️ Stop: {stop_ar:.2f}"
                send_telegram(uzenet)
                time.sleep(300)
            time.sleep(120)
        except Exception as e:
            print(f"Hiba: {e}")
            time.sleep(30)

if __name__ == "__main__":
    t = threading.Thread(target=start_flask, daemon=True)
    t.start()
    main_loop()
