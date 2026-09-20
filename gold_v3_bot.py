import time
import requests
import pandas as pd
import numpy as np
import threading
import os
from datetime import datetime, timedelta, timezone
from flask import Flask, jsonify
from flask_cors import CORS

BUDAPEST_OFFSET = 2
def now_budapest():
    return datetime.now(timezone.utc) + timedelta(hours=BUDAPEST_OFFSET)

def budapest_str(fmt="%Y-%m-%d %H:%M:%S"):
    return now_budapest().strftime(fmt)

BINANCE_SYMBOL = "XAUUSD"
YAHOO_SYMBOL = "XAUUSD=X"
INTERVAL = "2m"
EMA_FAST = 9
EMA_MID = 21
EMA_SLOW = 50
RSI_PERIOD = 14
RSI_LONG_MIN = 55
RSI_SHORT_MAX = 45
RSI_LONG_MAX = 75
RSI_SHORT_MIN = 25
LEVERAGE = 20
ATR_PERIOD = 14
ATR_MULT = 1.5
MAX_TOKE_BUKO = 6.0
MIN_ATR = 3.0

TELEGRAM_TOKEN = "8990882185:AAFqtCm9ZDHk62-n9vhFcg4Rv6QlK99wE6A"
TELEGRAM_CHAT_ID = "7995386347"

bot_status = {
    "bot": "GOLD V4.3.3 BUDAPEST FIX",
    "fut": True,
    "allapot": "Fut - V4.3.3 Budapest +2h",
    "utolso_ellenorzes": "meg nem futott",
    "utolso_jel": "meg nincs jel",
    "mai_jelek": 0,
    "toke_vedelem": f"ATR x{ATR_MULT} PRO (max {MAX_TOKE_BUKO}% | {LEVERAGE}x | MIN {MIN_ATR}$)",
    "ema_beallitas": f"{EMA_FAST} / {EMA_MID} / {EMA_SLOW}",
    "szimbolum": BINANCE_SYMBOL,
    "idokeret": INTERVAL,
    "forras": "Yahoo Finance XAUUSD=X 2m OHLC",
    "atr": None,
    "stop_tav": None,
    "aktiv_trade": "nincs aktiv trade",
    "aktiv_trade_reszletek": None,
    "frissitve": budapest_str('%Y-%m-%d %H:%M:%S')
}

utolso_jel_tipus = None
utolso_jel_ido = 0
aktiv_trade = None

app = Flask(__name__)
CORS(app)

@app.route("/")
def home():
    try:
        with open("status.html", "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return jsonify({"uzenet": "Gold V4.3.3 Budapest fut", "status_link": "/status", "hiba": str(e)})

@app.route("/status")
def status():
    bot_status["frissitve"] = budapest_str('%Y-%m-%d %H:%M:%S')
    resp = jsonify(bot_status)
    resp.headers.add('Access-Control-Allow-Origin', '*')
    return resp

@app.route("/ping")
def ping():
    return jsonify({"status": "alive", "time": now_budapest().isoformat(), "bot": "GOLD V4.3.3 BUDAPEST"})

@app.route("/health")
def health():
    return "OK", 200

def self_ping_loop():
    time.sleep(60)
    while True:
        try:
            render_url = os.environ.get("RENDER_EXTERNAL_URL", "")
            if render_url:
                url = render_url.rstrip("/") + "/ping"
                requests.get(url, timeout=10)
            else:
                port = int(os.environ.get("PORT", 5000))
                requests.get(f"http://localhost:{port}/ping", timeout=5)
        except Exception as e:
            print(f"[SELF-PING hiba] {e}")
        time.sleep(600)

@app.route("/status.html")
def status_html_file():
    try:
        with open("status.html", "r", encoding="utf-8") as f:
            return f.read()
    except:
        return "status.html nem talalhato", 404

def start_flask():
    port = int(os.environ.get("PORT", 5000))
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

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calc_atr(df, period=14):
    df["prev_close"] = df["close"].shift(1)
    df["tr1"] = df["high"] - df["low"]
    df["tr2"] = (df["high"] - df["prev_close"]).abs()
    df["tr3"] = (df["low"] - df["prev_close"]).abs()
    df["tr"] = df[["tr1","tr2","tr3"]].max(axis=1)
    atr = df["tr"].rolling(window=period).mean()
    return atr

def get_klines(limit=200):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{YAHOO_SYMBOL}?range=5d&interval=2m"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=15)
        j = resp.json()
        if "chart" in j and j["chart"]["result"]:
            result = j["chart"]["result"][0]
            timestamps = result["timestamp"]
            quote = result["indicators"]["quote"][0]
            closes = quote["close"]
            highs = quote["high"]
            lows = quote["low"]
            opens = quote["open"]
            data = []
            for t,o,h,l,c in zip(timestamps, opens, highs, lows, closes):
                if c is not None and h is not None and l is not None:
                    data.append({"time": t, "open": o, "high": h, "low": l, "close": c})
            if len(data) < 60:
                raise Exception(f"Keves adat: {len(data)}")
            df = pd.DataFrame(data)
            for col in ["open","high","low","close"]:
                df[col] = df[col].astype(float)
            return df
        else:
            raise Exception(f"Yahoo hibas")
    except Exception as e1:
        print(f"Yahoo hiba: {e1}, backup PAXG")
        try:
            url = f"https://data-api.binance.vision/api/v3/klines?symbol=PAXGUSDT&interval=3m&limit={limit}"
            r = requests.get(url, timeout=10).json()
            if isinstance(r, dict) and "msg" in r:
                return None
            df = pd.DataFrame(r, columns=["time","open","high","low","close","vol","ct","qvol","trades","taker_base","taker_quote","ignore"])
            for col in ["open","high","low","close"]:
                df[col] = df[col].astype(float)
            bot_status["forras"] = "PAXGUSDT proxy ATR (XAUUSD kozeli)"
            bot_status["szimbolum"] = "XAUUSD (PAXG proxy ATR)"
            return df
        except Exception as e2:
            print(f"Backup hiba: {e2}")
            return None

def analyze():
    df = get_klines()
    if df is None or len(df) < 60:
        bot_status["allapot"] = "Hiba - nincs adat"
        return None
    df["ema9"] = df["close"].ewm(span=EMA_FAST).mean()
    df["ema21"] = df["close"].ewm(span=EMA_MID).mean()
    df["ema50"] = df["close"].ewm(span=EMA_SLOW).mean()
    df["rsi"] = calc_rsi(df["close"], RSI_PERIOD)
    df["atr"] = calc_atr(df, ATR_PERIOD)
    last = df.iloc[-1]
    if pd.isna(last["rsi"]) or pd.isna(last["atr"]):
        return None
    bot_status["utolso_ellenorzes"] = budapest_str('%Y-%m-%d %H:%M:%S')
    bot_status["aktualis_ar"] = float(last["close"])
    bot_status["rsi"] = float(last["rsi"])
    bot_status["atr"] = float(last["atr"])
    raw_atr = float(last["atr"])
    atr = max(raw_atr, MIN_ATR)
    stop_dist_price = atr * ATR_MULT
    max_dist = float(last["close"]) * (MAX_TOKE_BUKO / LEVERAGE) / 100.0
    if stop_dist_price > max_dist:
        stop_dist_price = max_dist
        atr = stop_dist_price / ATR_MULT
        bot_status["stop_tav"] = f"{stop_dist_price:.2f}$ (MAX {MAX_TOKE_BUKO}% cap | raw {raw_atr:.2f}$)"
    else:
        bot_status["stop_tav"] = f"{stop_dist_price:.2f}$ (ATR {atr:.2f} x{ATR_MULT} | raw {raw_atr:.2f}$)"
    toke_buko_atr = (stop_dist_price / float(last["close"]) * 100) * LEVERAGE
    bot_status["toke_vedelem"] = f"ATR x{ATR_MULT} = {stop_dist_price:.2f}$ ({toke_buko_atr:.1f}% toke | {LEVERAGE}x | MIN {MIN_ATR}$)"
    uptrend = last["ema9"] > last["ema21"] > last["ema50"]
    downtrend = last["ema9"] < last["ema21"] < last["ema50"]
    pullback_long = abs(last["close"] - last["ema21"]) / last["close"] < 0.0015 and last["close"] > last["ema21"]
    pullback_short = abs(last["close"] - last["ema21"]) / last["close"] < 0.0015 and last["close"] < last["ema21"]
    jel = None
    if uptrend and pullback_long and last["rsi"] > RSI_LONG_MIN and last["rsi"] < RSI_LONG_MAX:
        jel = "LONG"
    elif downtrend and pullback_short and last["rsi"] < RSI_SHORT_MAX and last["rsi"] > RSI_SHORT_MIN:
        jel = "SHORT"
    return {
        "ar": float(last["close"]),
        "high": float(last["high"]),
        "low": float(last["low"]),
        "ema9": float(last["ema9"]),
        "ema21": float(last["ema21"]),
        "ema50": float(last["ema50"]),
        "rsi": float(last["rsi"]),
        "atr": float(last["atr"]),
        "atr_used": atr,
        "stop_dist": stop_dist_price,
        "toke_pct": toke_buko_atr,
        "uptrend": uptrend,
        "downtrend": downtrend,
        "jel": jel
    }

def check_aktiv_trade(res):
    global aktiv_trade
    if not aktiv_trade:
        return None
    current_high = res["high"]
    current_low = res["low"]
    current_price = res["ar"]
    tipus = aktiv_trade["tipus"]
    belepo = aktiv_trade["belepo"]
    stop = aktiv_trade["stop"]
    tp = aktiv_trade["tp"]
    toke_pct = aktiv_trade["toke_pct"]
    hit = None
    if tipus == "LONG":
        if current_low <= stop:
            hit = "STOP"
            uzenet = f"STOP TALALAT - {tipus} Belepo: {belepo:.2f} Stop: {stop:.2f} Ar: {current_price:.2f} Veszteseg: {toke_pct:.1f}% toke {budapest_str('%H:%M:%S')} Zard a poziciot!"
        elif current_high >= tp:
            hit = "TP"
            uzenet = f"TP TALALAT - {tipus} Belepo: {belepo:.2f} TP: {tp:.2f} Ar: {current_price:.2f} Nyereseg: +{toke_pct*2:.1f}% toke {budapest_str('%H:%M:%S')}"
    else:
        if current_high >= stop:
            hit = "STOP"
            uzenet = f"STOP TALALAT - {tipus} Belepo: {belepo:.2f} Stop: {stop:.2f} Ar: {current_price:.2f} Veszteseg: {toke_pct:.1f}% toke {budapest_str('%H:%M:%S')}"
        elif current_low <= tp:
            hit = "TP"
            uzenet = f"TP TALALAT - {tipus} Belepo: {belepo:.2f} TP: {tp:.2f} Ar: {current_price:.2f} Nyereseg: +{toke_pct*2:.1f}% toke {budapest_str('%H:%M:%S')}"
    if hit:
        send_telegram(uzenet)
        print(f"[{hit} TALALAT] {tipus} {belepo:.2f} -> {current_price:.2f}")
        bot_status["aktiv_trade"] = f"LEZART {hit} - {tipus} {belepo:.2f} -> {current_price:.2f}"
        bot_status["aktiv_trade_reszletek"] = None
        aktiv_trade = None
        return hit
    else:
        pnl_now = ((current_price - belepo)/belepo*100*LEVERAGE) if tipus=="LONG" else ((belepo - current_price)/belepo*100*LEVERAGE)
        bot_status["aktiv_trade"] = f"AKTIV {tipus} {belepo:.2f} -> {current_price:.2f} ({pnl_now:+.1f}%) Stop:{stop:.2f} TP:{tp:.2f}"
        return None

def main_loop():
    global utolso_jel_tipus, utolso_jel_ido, aktiv_trade
    print(f"GOLD V4.3.3 BUDAPEST FIX indul - ATR x{ATR_MULT} MIN {MIN_ATR}$")
    send_telegram(f"GOLD V4.3.3 BUDAPEST FIX elindult EMA {EMA_FAST}/{EMA_MID}/{EMA_SLOW} ATR x{ATR_MULT} MIN {MIN_ATR}$ max {MAX_TOKE_BUKO}% - STOP/TP figyelo AKTIV")
    while True:
        try:
            res = analyze()
            if not res:
                time.sleep(30)
                continue
            print(f"[{bot_status['utolso_ellenorzes']}] Ar: {res['ar']:.2f} ATR: {res['atr']:.2f} Stop: {res['stop_dist']:.2f} RSI: {res['rsi']:.1f} Jel: {res['jel']} Aktiv: {aktiv_trade['tipus'] if aktiv_trade else 'nincs'}")
            check_aktiv_trade(res)
            if res["jel"]:
                most = time.time()
                if res["jel"] == utolso_jel_tipus and (most - utolso_jel_ido) < 1800:
                    print(f"[SKIP] {res['jel']} mar volt")
                else:
                    bot_status["mai_jelek"] += 1
                    bot_status["utolso_jel"] = f"{res['jel']} {res['ar']:.2f} ATR:{res['atr']:.2f} - {budapest_str('%H:%M:%S')}"
                    utolso_jel_tipus = res["jel"]
                    utolso_jel_ido = most
                    stop_ar = res["ar"] + res["stop_dist"] if res["jel"]=="SHORT" else res["ar"] - res["stop_dist"]
                    tp_ar = res["ar"] - res["stop_dist"]*2 if res["jel"]=="SHORT" else res["ar"] + res["stop_dist"]*2
                    toke_pct = res["toke_pct"]
                    aktiv_trade = {
                        "tipus": res["jel"],
                        "belepo": res["ar"],
                        "stop": stop_ar,
                        "tp": tp_ar,
                        "atr": res["atr_used"],
                        "toke_pct": toke_pct,
                        "ido": budapest_str('%Y-%m-%d %H:%M:%S')
                    }
                    bot_status["aktiv_trade"] = f"AKTIV {res['jel']} {res['ar']:.2f} Stop:{stop_ar:.2f} TP:{tp_ar:.2f} ({toke_pct:.1f}% -> +{toke_pct*2:.1f}%)"
                    bot_status["aktiv_trade_reszletek"] = aktiv_trade
                    uzenet = f"{res['jel']} JEL - XAUUSD V4.3.3 BUDAPEST Ar: {res['ar']:.2f} ATR: {res['atr_used']:.2f} x{ATR_MULT} = {res['stop_dist']:.2f}$ RSI: {res['rsi']:.1f} Stop: {stop_ar:.2f} ({toke_pct:.1f}% toke) TP: {tp_ar:.2f} (+{toke_pct*2:.1f}% RR 1:2) STOP/TP jelzest kuldok! {LEVERAGE}x LEV = RISK"
                    send_telegram(uzenet)
                    print(f"[JEL KULDVE V4.3.3] {res['jel']} Stop {stop_ar:.2f} TP {tp_ar:.2f}")
            time.sleep(120)
        except Exception as e:
            print(f"Hiba: {e}")
            import traceback; traceback.print_exc()
            time.sleep(30)

if __name__ == "__main__":
    t = threading.Thread(target=start_flask, daemon=True)
    t.start()
    tp = threading.Thread(target=self_ping_loop, daemon=True)
    tp.start()
    main_loop()
