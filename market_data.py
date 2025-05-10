# market_data.py
import requests
import pandas as pd
import ta
# Hapus 'import logging' jika ada atau 'logger = logging.getLogger(__name__)'
# Sebagai gantinya, impor instance logger yang sudah dikonfigurasi dari bot_config.py
from bot_config import logger
from utils import get_val # Pastikan utils.py juga sudah benar

# Tidak perlu lagi baris: logger = logging.getLogger(__name__)

# ... sisa fungsi fetch_okx_candles, analyze_indicators, check_extreme_alert ...
# Di dalam fungsi-fungsi ini, Anda bisa langsung menggunakan 'logger.info()', 'logger.error()', dll.

def fetch_okx_candles(pair="SOL-USDT", interval="1H", limit=220):
    url = f"https://www.okx.com/api/v5/market/candles?instId={pair}&bar={interval}&limit={limit}"
    logger.info(f"Fetching OKX candles for {pair}, interval {interval}, limit {limit}")
    try:
        res = requests.get(url, timeout=15)
        res.raise_for_status()
        data_response = res.json()
        data_list = data_response.get('data', [])
        
        if not data_list:
            logger.warning(f"Tidak ada data candlestick diterima dari OKX untuk {pair} interval {interval}.")
            return pd.DataFrame()
            
        df = pd.DataFrame(data_list, columns=['ts', 'open', 'high', 'low', 'close', 'volume', 'volCcy', 'volCcyQuote', 'confirm'])
        df.sort_values('ts', ascending=True, inplace=True)

        df['ts'] = pd.to_datetime(pd.to_numeric(df['ts']), unit='ms')
        
        numeric_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df.dropna(subset=numeric_cols, inplace=True)
        if df.empty:
            logger.warning(f"DataFrame kosong setelah konversi numerik dan dropna untuk {pair} interval {interval}.")
            return pd.DataFrame()

        logger.info(f"Berhasil mengambil {len(df)} candle untuk {pair} interval {interval}")
        return df[['ts', 'open', 'high', 'low', 'close', 'volume']]
    except requests.exceptions.RequestException as e:
        logger.error(f"Error koneksi saat fetch OKX untuk {pair} interval {interval}: {e}")
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"Error umum saat fetch OKX untuk {pair} interval {interval}: {e}")
        return pd.DataFrame()

def analyze_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or len(df) < 2:
        logger.warning("DataFrame kosong atau tidak cukup data untuk analisis indikator.")
        return df
    
    try:
        df['rsi'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()
        macd_indicator = ta.trend.MACD(close=df['close'], window_slow=26, window_fast=12, window_sign=9)
        df['macd'] = macd_indicator.macd()
        df['macd_signal'] = macd_indicator.macd_signal()
        df['macd_hist'] = macd_indicator.macd_diff()

        for window in [9, 20, 50, 100, 200]:
            if len(df) >= window:
                df[f'ema_{window}'] = ta.trend.EMAIndicator(close=df['close'], window=window).ema_indicator()
            else:
                df[f'ema_{window}'] = pd.NA

        if len(df) > 1:
            range_hl = df['high'] - df['low'] + 1e-9 
            df['doji'] = (abs(df['close'] - df['open']) / range_hl) < 0.1
            df['bullish_engulfing'] = (df['open'].shift(1) > df['close'].shift(1)) & \
                                      (df['open'] < df['close']) & \
                                      (df['open'] < df['close'].shift(1)) & \
                                      (df['close'] > df['open'].shift(1))
            df['bearish_engulfing'] = (df['open'].shift(1) < df['close'].shift(1)) & \
                                       (df['open'] > df['close']) & \
                                       (df['open'] > df['close'].shift(1)) & \
                                       (df['close'] < df['open'].shift(1))
            df['hammer'] = ((df['high'] - df['low']) > 3 * (df['open'] - df['close']).abs()) & \
                           ((df['close'] - df['low']) / range_hl > 0.6) & \
                           ((df['open'] - df['low']) / range_hl > 0.6)
            df['shooting_star'] = ((df['high'] - df['low']) > 3 * (df['open'] - df['close']).abs()) & \
                                  ((df['high'] - df['close']) / range_hl > 0.6) & \
                                  ((df['high'] - df['open']) / range_hl > 0.6)
        else:
            for col in ['doji', 'bullish_engulfing', 'bearish_engulfing', 'hammer', 'shooting_star']:
                df[col] = False
    except Exception as e:
        logger.error(f"Error saat analisa teknikal: {e}", exc_info=True)
    return df

def check_extreme_alert(df: pd.DataFrame, pair_name: str) -> str:
    # (Salin implementasi check_extreme_alert yang sudah diperbaiki ke sini)
    # Pastikan mengimpor escape_markdown_v2 dari utils.py jika belum
    from utils import escape_markdown_v2, get_val # Impor lagi jika perlu di sini

    if df.empty or len(df) < 2:
        return ""
    last_candle = df.iloc[-1]
    message_parts = []
    escaped_pair_name = escape_markdown_v2(pair_name)

    if len(df) >= 21:
        avg_vol_lookback = 20
        avg_vol = df['volume'].iloc[-(avg_vol_lookback + 1):-1].mean() 
        if last_candle['volume'] > 2 * avg_vol and avg_vol > 0 :
            vol_ratio = last_candle['volume'] / avg_vol if avg_vol > 0 else float('inf')
            message_parts.append(f"• Lonjakan Volume ({vol_ratio:.1f}x rata-rata)! Vol: {last_candle['volume']:.2f} (Rata-rata {avg_vol_lookback} bar: {avg_vol:.2f})")

    price_change_percent = ((last_candle['close'] - last_candle['open']) / last_candle['open']) * 100 if last_candle['open'] > 0 else 0
    if abs(price_change_percent) > 1.5:
        direction = "naik" if price_change_percent > 0 else "turun"
        candle_type = "hijau" if price_change_percent > 0 else "merah"
        message_parts.append(f"• Harga {direction} tajam ({price_change_percent:.2f}%)! Candle {candle_type} besar terdeteksi.")

    if len(df) >= 6:
        lookback_period = 5
        recent_high = df['high'].iloc[-(lookback_period + 1):-1].max()
        recent_low = df['low'].iloc[-(lookback_period + 1):-1].min()
        
        temp_series_high = pd.Series({'val': recent_high})
        temp_series_low = pd.Series({'val': recent_low})

        if last_candle['close'] > recent_high and (pd.isna(last_candle.get('ema_20')) or last_candle['close'] > last_candle.get('ema_20', 0)):
            message_parts.append(f"• Breakout dari resistance ({get_val(temp_series_high, 'val', p=2)}) & di atas EMA20.")
        elif last_candle['close'] < recent_low and (pd.isna(last_candle.get('ema_20')) or last_candle['close'] < last_candle.get('ema_20', float('inf'))):
             message_parts.append(f"• Breakdown dari support ({get_val(temp_series_low, 'val', p=2)}) & di bawah EMA20.")
    
    if message_parts:
        return f"🚨 *PERINGATAN EKSTREM: {escaped_pair_name}*\n" + "\n".join(message_parts) + "\n\n⚠️ _Perhatikan volatilitas tinggi & konfirmasi lebih lanjut diperlukan._"
    return ""
