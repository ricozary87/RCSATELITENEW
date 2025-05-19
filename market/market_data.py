import requests
import pandas as pd
import ta
from bot_config import logger
from utils.utils import escape_markdown_v2, get_val

def fetch_okx_candles(pair="SOL-USDT", interval="1H", limit=220):
    url = f"https://www.okx.com/api/v5/market/candles?instId={pair}&bar={interval}&limit={limit}"
    logger.info(f"Fetching OKX candles for {pair}, interval {interval}, limit {limit}")
    try:
        res = requests.get(url, timeout=15)
        res.raise_for_status()
        data_list = res.json().get('data', [])
        
        if not data_list:
            logger.warning(f"Tidak ada data candlestick dari OKX untuk {pair} interval {interval}.")
            return pd.DataFrame()
        
        df = pd.DataFrame(data_list, columns=['ts', 'open', 'high', 'low', 'close', 'volume', 'volCcy', 'volCcyQuote', 'confirm'])
        df.sort_values('ts', ascending=True, inplace=True)
        df['ts'] = pd.to_datetime(pd.to_numeric(df['ts']), unit='ms')
        
        numeric_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(subset=numeric_cols, inplace=True)

        if df.empty:
            logger.warning(f"Data kosong setelah konversi numerik untuk {pair} interval {interval}.")
            return pd.DataFrame()

        logger.info(f"Berhasil mengambil {len(df)} candle untuk {pair} interval {interval}")
        return df[['ts', 'open', 'high', 'low', 'close', 'volume']]
    except Exception as e:
        logger.error(f"Gagal fetch OKX candles: {e}")
        return pd.DataFrame()

def analyze_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or len(df) < 2:
        logger.warning("DataFrame kosong / tidak cukup untuk analisis indikator.")
        return df
    try:
        df['rsi'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()
        macd = ta.trend.MACD(close=df['close'])
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['macd_hist'] = macd.macd_diff()

        for w in [9, 20, 50, 100, 200]:
            df[f'ema_{w}'] = ta.trend.EMAIndicator(close=df['close'], window=w).ema_indicator()

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
            df['hammer'] = ((df['high'] - df['low']) > 3 * abs(df['open'] - df['close'])) & \
                           ((df['close'] - df['low']) / range_hl > 0.6) & \
                           ((df['open'] - df['low']) / range_hl > 0.6)
            df['shooting_star'] = ((df['high'] - df['low']) > 3 * abs(df['open'] - df['close'])) & \
                                  ((df['high'] - df['close']) / range_hl > 0.6) & \
                                  ((df['high'] - df['open']) / range_hl > 0.6)
    except Exception as e:
        logger.error(f"Error saat menghitung indikator teknikal: {e}", exc_info=True)
    return df

def check_extreme_alert(df: pd.DataFrame, pair_name: str) -> str:
    if df.empty or len(df) < 2:
        return ""
    
    last = df.iloc[-1]
    escaped_name = escape_markdown_v2(pair_name)
    messages = []

    # Volume spike
    if len(df) >= 21:
        avg_vol = df['volume'].iloc[-21:-1].mean()
        if avg_vol > 0 and last['volume'] > 2 * avg_vol:
            ratio = last['volume'] / avg_vol
            messages.append(f"• Lonjakan Volume ({ratio:.1f}x)! Vol: {last['volume']:.2f} (avg: {avg_vol:.2f})")

    # Harga naik/turun signifikan
    if last['open'] > 0:
        change_pct = ((last['close'] - last['open']) / last['open']) * 100
        if abs(change_pct) > 1.5:
            arah = "naik" if change_pct > 0 else "turun"
            candle = "hijau" if change_pct > 0 else "merah"
            messages.append(f"• Harga {arah} tajam ({change_pct:.2f}%)! Candle {candle} besar terdeteksi.")

    # Breakout/breakdown
    if len(df) >= 6:
        high5 = df['high'].iloc[-6:-1].max()
        low5 = df['low'].iloc[-6:-1].min()
        if last['close'] > high5 and (pd.isna(last.get('ema_20')) or last['close'] > last.get('ema_20', 0)):
            messages.append(f"• Breakout dari resistance ({get_val(pd.Series({'val': high5}), 'val', p=2)}) & di atas EMA20.")
        elif last['close'] < low5 and (pd.isna(last.get('ema_20')) or last['close'] < last.get('ema_20', float('inf'))):
            messages.append(f"• Breakdown dari support ({get_val(pd.Series({'val': low5}), 'val', p=2)}) & di bawah EMA20.")

    if messages:
        return f"🚨 *PERINGATAN EKSTREM: {escaped_name}*\n" + "\n".join(messages)
    return ""
