import pandas as pd
from bot_config import logger
from utils.utils import escape_markdown_v2, get_val
from analysis.smc_analyzer import get_smc_signals

def generate_sol_alerts(data_frames_by_timeframe: dict, pair_name_for_alert: str) -> str:
    alerts = []
    escaped_pair_name = escape_markdown_v2(pair_name_for_alert)
    logger.info(f"Memulai generate_sol_alerts untuk {pair_name_for_alert} dengan timeframe: {list(data_frames_by_timeframe.keys())}")

    df_5m = data_frames_by_timeframe.get("5m")
    df_1H = data_frames_by_timeframe.get("1H")
    df_15m = data_frames_by_timeframe.get("15m")

    last_5m = df_5m.iloc[-1] if df_5m is not None and not df_5m.empty else None
    last_1H = df_1H.iloc[-1] if df_1H is not None and not df_1H.empty else None
    last_15m = df_15m.iloc[-1] if df_15m is not None and not df_15m.empty else None

    # === Aturan 1: Oversold 5m + konfirmasi 1H ===
    if last_5m is not None and last_1H is not None:
        rsi_5m = last_5m.get('rsi', 100)
        ema20_5m = last_5m.get('ema_20', float('inf'))
        close_5m = last_5m.get('close', 0)
        is_bullish_eng_5m = last_5m.get('bullish_engulfing', False)
        is_hammer_5m = last_5m.get('hammer', False)

        rsi_1H = last_1H.get('rsi', 100)
        ema50_1H = last_1H.get('ema_50', float('inf'))
        close_1H = last_1H.get('close', 0)

        if rsi_5m < 25 and close_5m < ema20_5m * 0.995:
            if rsi_1H < 35 and close_1H > ema50_1H and (is_bullish_eng_5m or is_hammer_5m):
                alerts.append(f"🔥 *SOL Alert BUY Potensial (Agresif)*:\n  RSI 5m ({rsi_5m:.1f}) & 1H ({rsi_1H:.1f}) rendah. Pola Bullish 5m. 1H di atas EMA50.\n  Harga 5m: {get_val(last_5m, 'close')}")

    # === Aturan 2: MACD cross di 5m + tren kuat di 1H ===
    if df_5m is not None and len(df_5m) >= 2 and last_1H is not None:
        prev_5m = df_5m.iloc[-2]
        macd_5m_curr = last_5m.get('macd', 0)
        signal_5m_curr = last_5m.get('macd_signal', 1)
        macd_5m_prev = prev_5m.get('macd', 1)
        signal_5m_prev = prev_5m.get('macd_signal', 0)

        close_1H = last_1H.get('close', 0)
        ema20_1H = last_1H.get('ema_20', float('inf'))
        macd_1H_val = last_1H.get('macd', -1)

        if macd_5m_prev < signal_5m_prev and macd_5m_curr > signal_5m_curr and \
           close_1H > ema20_1H and macd_1H_val > 0:
            alerts.append(f"📈 *Sinyal BUY {escaped_pair_name}*:\n  MACD cross bullish di 5m. Tren 1H mendukung (di atas EMA20 & MACD > 0).\n  Harga 5m: {get_val(last_5m, 'close')}")

    # === Aturan 3: Breakout di 15m dengan volume ===
    if last_15m is not None and df_15m is not None and len(df_15m) >= 21 and last_1H is not None:
        close_15m = last_15m.get('close', 0)
        high_prev_10_15m = df_15m['high'].iloc[-11:-1].max() if len(df_15m) >= 11 else close_15m
        volume_15m = last_15m.get('volume', 0)
        avg_vol_15m = df_15m['volume'].iloc[-21:-1].mean()

        close_1H = last_1H.get('close', 0)
        ema20_1H = last_1H.get('ema_20', float('inf'))

        if close_15m > high_prev_10_15m and volume_15m > 1.8 * avg_vol_15m and avg_vol_15m > 0 and close_1H > ema20_1H:
            temp_series_high_15m = pd.Series({'val': high_prev_10_15m})
            alerts.append(f"🚀 *SOL Alert BUY Breakout (15m)*:\n  Tembus resistensi 15m ({get_val(temp_series_high_15m, 'val')}) dengan volume. Tren 1H mendukung.\n  Harga 15m: {get_val(last_15m, 'close')}")

    # === Tambahan: Struktur Market (SMC) ===
    for tf, df in data_frames_by_timeframe.items():
        if df is None or df.empty:
            continue

        try:
            smc = get_smc_signals(df)
            last_smc = smc.iloc[-1]

            smc_parts = []
            if last_smc['bos']:
                smc_parts.append("📈 *BOS* (Break of Structure)")
            if last_smc['choch']:
                smc_parts.append("⚠️ *CHoCH* (Change of Character)")
            if last_smc['liquidity_sweep']:
                smc_parts.append("🧨 *Sweep Likuiditas*")

            if smc_parts:
                alerts.append(f"📊 *SMC Deteksi ({tf})*: " + ", ".join(smc_parts))

        except Exception as e:
            logger.warning(f"Gagal menganalisis SMC pada timeframe {tf}: {e}")

    if not alerts:
        logger.info(f"Tidak ada sinyal otomatis khusus yang terdeteksi untuk {pair_name_for_alert}.")
        return ""

    logger.info(f"Sinyal otomatis SOL terdeteksi: {alerts}")
    return "\n\n".join(alerts)
