"""
XAU/USD 15sec Scalp Strategy - TELEGRAM ALERT + RENDER DEPLOY
EMA 50/200 (1m trend) + EMA 9/20 (15s entry) + RSI
Küld Telegram üzenetet minden beszállónál.

RENDER-en futtatáshoz: https://dashboard.render.com
"""

import os
import time
import pandas as pd
import numpy as np
import requests
from datetime import datetime

# ========= CONFIG - Render Environment Variables-ból =========
# Render Dashboard -> Environment -> Add:
# TELEGRAM_BOT_TOKEN = 123456789:AAHxxx...
# TELEGRAM_CHAT_ID = 123456789
# SYMBOL = XAUUSD (opcionalis)

BOT_TOKEN = os.getenv "8990882185:AAFqtCm9ZDHk62-n9vhFcg4Rv6QlK99wE6A"
CHAT_ID = os.getenv "7995386347"
SYMBOL = os.getenv("SYMBOL", "XAUUSD")

# ========= TELEGRAM KÜLDÉS =========
def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print(f"[TELEGRAM SKIP] Nincs TOKEN/CHAT_ID. Üzenet: {message}")
        return False
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        print(f"Telegram status: {r.status_code} - {r.text[:200]}")
        return r.status_code == 200
    except Exception as e:
        print(f"Telegram hiba: {e}")
        return False

# ========= INDIKÁTOROK =========
def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# ========= STRATÉGIA LOGIKA =========
def check_signal(df_1m, df_15s):
    """
    df_1m: 1 perces close adatok
    df_15s: 15 sec close adatok
    Visszaad: dict signal vagy None
    """
    df_1m['ema50'] = ema(df_1m['close'], 50)
    df_1m['ema200'] = ema(df_1m['close'], 200)
    df_1m['trend'] = np.where(df_1m['close'] > df_1m['ema200'], 1, -1)

    df_15s['ema9'] = ema(df_15s['close'], 9)
    df_15s['ema20'] = ema(df_15s['close'], 20)
    df_15s['rsi'] = rsi(df_15s['close'], 14)

    if len(df_1m) < 200 or len(df_15s) < 20:
        return None

    trend = df_1m['trend'].iloc[-1]
    ema50_1m = df_1m['ema50'].iloc[-1]

    ema9_prev, ema9_curr = df_15s['ema9'].iloc[-2], df_15s['ema9'].iloc[-1]
    ema20_prev, ema20_curr = df_15s['ema20'].iloc[-2], df_15s['ema20'].iloc[-1]
    rsi_curr = df_15s['rsi'].iloc[-1]
    close_curr = df_15s['close'].iloc[-1]

    # SHORT
    if trend == -1:
        cross_down = ema9_prev > ema20_prev and ema9_curr < ema20_curr
        near_ema50 = abs(close_curr - ema50_1m) < 1.5
        if cross_down and near_ema50 and 30 < rsi_curr < 60:
            return {
                'type': '🔴 SELL',
                'price': close_curr,
                'sl': close_curr + 0.9,
                'tp': close_curr - 1.5,
                'rsi': round(rsi_curr, 1),
                'trend': 'BEAR (ár < EMA200 1M)',
                'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S CET")
            }

    # LONG
    if trend == 1:
        cross_up = ema9_prev < ema20_prev and ema9_curr > ema20_curr
        near_ema50 = abs(close_curr - ema50_1m) < 1.5
        if cross_up and near_ema50 and 40 < rsi_curr < 70:
            return {
                'type': '🟢 BUY',
                'price': close_curr,
                'sl': close_curr - 0.9,
                'tp': close_curr + 1.5,
                'rsi': round(rsi_curr, 1),
                'trend': 'BULL (ár > EMA200 1M)',
                'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S CET")
            }

    return None

# ========= DEMO FUTTATÁS RENDER-EN =========
def fetch_live_data_demo():
    """
    DEMO: random walk XAU ár generálás - cseréld le valódi API-ra
    Éleshez: TradingView webhook, TwelveData, Finnhub, stb.
    """
    # Itt jönne a valódi API - most demo random
    np.random.seed(int(time.time()) % 10000)
    base = 4365
    # 1M - utolsó 250 gyertya
    dates_1m = pd.date_range(end=datetime.now(), periods=250, freq="1min")
    price_1m = base + np.cumsum(np.random.randn(250) * 0.15)
    df_1m = pd.DataFrame({'close': price_1m}, index=dates_1m)
    
    # 15S - utolsó 100 gyertya
    dates_15s = pd.date_range(end=datetime.now(), periods=100, freq="15s")
    price_15s = price_1m[-1] + np.cumsum(np.random.randn(100) * 0.08)
    df_15s = pd.DataFrame({'close': price_15s}, index=dates_15s)
    
    return df_1m, df_15s

def main_loop():
    print(f"Bot indul - Symbol: {SYMBOL}")
    send_telegram(f"✅ *XAU Scalp Bot elindult Render-en*\nSymbol: {SYMBOL}\nIdő: {datetime.now().strftime('%H:%M:%S')}\nStratégia: 1M EMA50/200 + 15S EMA9/20")

    last_signal_time = 0

    while True:
        try:
            df_1m, df_15s = fetch_live_data_demo()
            signal = check_signal(df_1m, df_15s)

            if signal:
                # ne spammeljen 5 percenként max 1 jel
                if time.time() - last_signal_time > 300:
                    msg = (
                        f"{signal['type']} *{SYMBOL}*\n"
                        f"━━━━━━━━━━━━━━\n"
                        f"💰 Ár: `{signal['price']:.2f}`\n"
                        f"🛑 SL: `{signal['sl']:.2f}`\n"
                        f"🎯 TP: `{signal['tp']:.2f}`\n"
                        f"📊 RSI: `{signal['rsi']}`\n"
                        f"📈 Trend: {signal['trend']}\n"
                        f"⏰ {signal['time']}\n"
                        f"━━━━━━━━━━━━━━\n"
                        f"IQ: INVEST $75 x20 | RR 1:1.5"
                    )
                    send_telegram(msg)
                    last_signal_time = time.time()
                    print(f"SIGNAL KÜLDVE: {signal}")
                else:
                    print("Signal van, de 5 perc cooldown...")
            else:
                print(f"{datetime.now().strftime('%H:%M:%S')} - Nincs jel, 1M trend: {df_1m['trend'].iloc[-1] if len(df_1m)>0 else 'N/A'}")

            time.sleep(15)  # 15 sec-enként csekkol

        except Exception as e:
            print(f"Hiba a loopban: {e}")
            time.sleep(30)

if __name__ == "__main__":
    main_loop()
