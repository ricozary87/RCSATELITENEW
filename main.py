# main.py

import requests
import pandas as pd
import ta # Pastikan pustaka ta-lib terinstal dengan benar (sering jadi sumber masalah instalasi)
import time
import os
import logging
import threading
import re
from decimal import Decimal, InvalidOperation # Decimal saat ini tidak digunakan aktif, bisa dipertimbangkan untuk dihapus jika tidak ada rencana penggunaan
from openai import OpenAI
from dotenv import load_dotenv
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from telegram import Bot, ParseMode # Impor ParseMode untuk kejelasan

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load .env
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo") # Bisa ganti ke gpt-4 jika tersedia untuk hasil lebih baik
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID_STR = os.getenv("TELEGRAM_CHAT_ID")

if TELEGRAM_CHAT_ID_STR is None:
    logger.error("TELEGRAM_CHAT_ID tidak ditemukan di file .env.")
    TELEGRAM_CHAT_ID = None
else:
    try:
        TELEGRAM_CHAT_ID = int(TELEGRAM_CHAT_ID_STR)
    except ValueError:
        logger.error(f"TELEGRAM_CHAT_ID '{TELEGRAM_CHAT_ID_STR}' tidak valid.")
        TELEGRAM_CHAT_ID = None

# Init OpenAI
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
if not client:
    logger.warning("OPENAI_API_KEY tidak ditemukan atau kosong. Fitur AI tidak akan berfungsi.")


PAIRS = ["SOL-USDT", "BTC-USDT", "ETH-USDT", "XRP-USDT"] # Daftar koin utama

# Daftar timeframe yang didukung oleh OKX API (bar parameter) dan pemetaan dari input pengguna
# Sesuaikan ini berdasarkan dokumentasi OKX dan preferensi Anda
# Key: input pengguna (lowercase), Value: format OKX API
SUPPORTED_TF_MAP = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1H", "2h": "2H", "4h": "4H", "6h": "6H", "12h": "12H",
    "1d": "1D", "1w": "1W", "1mon": "1M", # '1M' OKX adalah 1 bulan kalender
    "3mon": "3M", "6mon": "6M", "1y": "1Y"
    # Tambahkan timeframe lain jika perlu
}


def escape_markdown_v2(text):
    if text is None:
        return ""
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', str(text))

def get_val(series, key, p=2, prefix="$", include_prefix=True):
    """Fungsi helper untuk mendapatkan dan memformat nilai dari Pandas Series (seperti baris DataFrame)."""
    val = series.get(key)
    if pd.isna(val):
        return "N/A"
    formatted_val = f"{float(val):.{p}f}" # Pastikan val adalah float untuk formatting
    return f"{prefix}{formatted_val}" if include_prefix else formatted_val
# main.py (lanjutan)

def fetch_okx_candles(pair="SOL-USDT", interval="1H", limit=220): # limit dinaikkan defaultnya
    # Pastikan 'interval' adalah format yang dikenali OKX dari SUPPORTED_TF_MAP
    url = f"https://www.okx.com/api/v5/market/candles?instId={pair}&bar={interval}&limit={limit}"
    logger.info(f"Fetching OKX candles for {pair}, interval {interval}, limit {limit}")
    try:
        res = requests.get(url, timeout=15) # Timeout sedikit dinaikkan
        res.raise_for_status()
        data_response = res.json()
        data_list = data_response.get('data', [])
        
        if not data_list:
            logger.warning(f"Tidak ada data candlestick diterima dari OKX untuk {pair} interval {interval}.")
            return pd.DataFrame()
            
        # Data OKX: [ts,o,h,l,c,vol,volCcy,volCcyQuote,confirm]
        # ts dalam milidetik string
        df = pd.DataFrame(data_list, columns=['ts', 'open', 'high', 'low', 'close', 'volume', 'volCcy', 'volCcyQuote', 'confirm'])
        df.sort_values('ts', ascending=True, inplace=True) # OKX kadang mengembalikan data terbaru dulu, kadang terlama. Pastikan urutan ascending.

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
    if df.empty or len(df) < 2: # Beberapa indikator butuh minimal 2 baris
        logger.warning("DataFrame kosong atau tidak cukup data untuk analisis indikator.")
        return df
    
    try:
        # RSI
        df['rsi'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()

        # MACD
        macd_indicator = ta.trend.MACD(close=df['close'], window_slow=26, window_fast=12, window_sign=9)
        df['macd'] = macd_indicator.macd()
        df['macd_signal'] = macd_indicator.macd_signal()
        df['macd_hist'] = macd_indicator.macd_diff() # Tambahkan histogram jika berguna

        # EMA
        for window in [9, 20, 50, 100, 200]:
            if len(df) >= window:
                df[f'ema_{window}'] = ta.trend.EMAIndicator(close=df['close'], window=window).ema_indicator()
            else:
                df[f'ema_{window}'] = pd.NA # atau np.nan

        # Pola Candlestick (membutuhkan minimal 2 baris data untuk shift(1))
        if len(df) > 1:
            # Tambahkan 1e-9 untuk menghindari pembagian dengan nol jika high == low
            range_hl = df['high'] - df['low'] + 1e-9 
            
            df['doji'] = (abs(df['close'] - df['open']) / range_hl) < 0.1

            # Bullish Engulfing: candle_sebelumnya bearish, candle_sekarang bullish & menelan candle_sebelumnya
            df['bullish_engulfing'] = (df['open'].shift(1) > df['close'].shift(1)) & \
                                      (df['open'] < df['close']) & \
                                      (df['open'] < df['close'].shift(1)) & \
                                      (df['close'] > df['open'].shift(1))
            
            # Bearish Engulfing: candle_sebelumnya bullish, candle_sekarang bearish & menelan candle_sebelumnya
            df['bearish_engulfing'] = (df['open'].shift(1) < df['close'].shift(1)) & \
                                       (df['open'] > df['close']) & \
                                       (df['open'] > df['close'].shift(1)) & \
                                       (df['close'] < df['open'].shift(1))

            # Hammer: badan kecil di atas, shadow bawah panjang (setelah downtrend - tidak dideteksi di sini)
            df['hammer'] = ((df['high'] - df['low']) > 3 * (df['open'] - df['close']).abs()) & \
                           ((df['close'] - df['low']) / range_hl > 0.6) & \
                           ((df['open'] - df['low']) / range_hl > 0.6)
            
            # Shooting Star: badan kecil di bawah, shadow atas panjang (setelah uptrend - tidak dideteksi di sini)
            df['shooting_star'] = ((df['high'] - df['low']) > 3 * (df['open'] - df['close']).abs()) & \
                                  ((df['high'] - df['close']) / range_hl > 0.6) & \
                                  ((df['high'] - df['open']) / range_hl > 0.6)
        else:
            for col in ['doji', 'bullish_engulfing', 'bearish_engulfing', 'hammer', 'shooting_star']:
                df[col] = False
                
    except Exception as e:
        logger.error(f"Error saat analisa teknikal: {e}", exc_info=True)
        # Kembalikan df apa adanya jika ada error parsial, atau df kosong?
        # Untuk sekarang, kembalikan df agar tidak menghentikan alur.
    return df

def check_extreme_alert(df: pd.DataFrame, pair_name: str) -> str:
    if df.empty or len(df) < 2:
        return ""
        
    last_candle = df.iloc[-1]
    message_parts = []
    escaped_pair_name = escape_markdown_v2(pair_name)

    # Volume Spike (cek jika cukup data untuk rata-rata)
    if len(df) >= 21: # butuh 20 candle sebelumnya + candle saat ini
        # Rata-rata volume dari 20 candle SEBELUMNYA (tidak termasuk candle saat ini)
        avg_vol_lookback = 20
        avg_vol = df['volume'].iloc[-(avg_vol_lookback + 1):-1].mean() 
        if last_candle['volume'] > 2 * avg_vol and avg_vol > 0 : # Hindari pembagian dengan nol jika avg_vol 0
            vol_ratio = last_candle['volume'] / avg_vol if avg_vol > 0 else float('inf')
            message_parts.append(f"• Lonjakan Volume ({vol_ratio:.1f}x rata-rata)! Vol: {last_candle['volume']:.2f} (Rata-rata {avg_vol_lookback} bar: {avg_vol:.2f})")

    # Perubahan Harga Signifikan dalam satu candle
    price_change_percent = ((last_candle['close'] - last_candle['open']) / last_candle['open']) * 100 if last_candle['open'] > 0 else 0
    if abs(price_change_percent) > 1.5: # Naik atau turun lebih dari 1.5%
        direction = "naik" if price_change_percent > 0 else "turun"
        candle_type = "hijau" if price_change_percent > 0 else "merah"
        message_parts.append(f"• Harga {direction} tajam ({price_change_percent:.2f}%)! Candle {candle_type} besar terdeteksi.")

    # Breakout/Breakdown dari high/low beberapa candle terakhir (misal 5 candle)
    if len(df) >= 6: # 5 candle sebelumnya + candle saat ini
        lookback_period = 5
        recent_high = df['high'].iloc[-(lookback_period + 1):-1].max()
        recent_low = df['low'].iloc[-(lookback_period + 1):-1].min()
        
        if last_candle['close'] > recent_high and last_candle.get('ema_20') is not pd.NA and last_candle['close'] > last_candle['ema_20']:
            message_parts.append(f"• Breakout dari resistance ({get_val(pd.Series({'val':recent_high}), 'val', p=2)}) & di atas EMA20.")
        elif last_candle['close'] < recent_low and last_candle.get('ema_20') is not pd.NA and last_candle['close'] < last_candle['ema_20']:
             message_parts.append(f"• Breakdown dari support ({get_val(pd.Series({'val':recent_low}), 'val', p=2)}) & di bawah EMA20.")
    
    if message_parts:
        return f"🚨 *PERINGATAN EKSTREM: {escaped_pair_name}*\n" + "\n".join(message_parts) + "\n\n⚠️ _Perhatikan volatilitas tinggi & konfirmasi lebih lanjut diperlukan._"
    return ""
# main.py (lanjutan)

def build_ai_analysis_prompt(df: pd.DataFrame, pair_name: str, timeframe_str: str) -> str:
    """Membangun prompt detail untuk OpenAI berdasarkan DataFrame dan timeframe."""
    if df.empty or len(df) < 1: # Cukup 1 baris terakhir untuk data saat ini
        return f"Tidak dapat membuat analisa untuk {pair_name} ({timeframe_str}), data tidak cukup."
    
    last_candle = df.iloc[-1]
    patterns = []
    for pattern_col, label in [('doji', "Doji"), ('bullish_engulfing', "Bullish Engulfing"),
                               ('bearish_engulfing', "Bearish Engulfing"), ('hammer', "Hammer"),
                               ('shooting_star', "Shooting Star")]:
        if last_candle.get(pattern_col, False): # get() untuk menghindari KeyError jika kolom tidak ada
            patterns.append(label)
    pattern_text = ", ".join(patterns) if patterns else "Tidak ada pola candlestick signifikan terdeteksi pada candle terakhir."

    # --- Data Teknis untuk Prompt ---
    # Ambil nilai mentah untuk contoh perhitungan yang lebih dinamis di prompt (jika diperlukan)
    harga_sekarang_val = last_candle.get('close', 0) 
    low_candle_val = last_candle.get('low', harga_sekarang_val * 0.99) # Fallback jika 'low' NA
    high_candle_val = last_candle.get('high', harga_sekarang_val * 1.01) # Fallback jika 'high' NA

    # String yang diformat untuk dimasukkan ke prompt
    harga_sekarang_str = get_val(last_candle, 'close')
    rsi_value_str = get_val(last_candle, 'rsi', include_prefix=False)
    macd_value_str = get_val(last_candle, 'macd', include_prefix=False)
    ema_9_str = get_val(last_candle, 'ema_9')
    ema_20_str = get_val(last_candle, 'ema_20')
    ema_50_str = get_val(last_candle, 'ema_50')
    ema_200_str = get_val(last_candle, 'ema_200')
    low_candle_str = get_val(last_candle, 'low') # Untuk contoh

    # --- Role Prompt ---
    role_prompt = (
        "Kamu adalah 'RC SATELLITE GPT SUPREME', seorang analis trading scalping dan intraday yang sangat berpengalaman. "
        "Kamu memberikan rekomendasi yang tajam, 'to the point', lugas, dan siap pakai. Fokus pada aksi dan strategi praktis, "
        "hindari bahasa teoritis atau kalimat-kalimat pengantar/penutup yang tidak perlu. Anggap audiensmu adalah trader aktif yang butuh keputusan cepat."
    )

    # --- Instruksi Inti & Permintaan Output ---
    instructions = f"""
Data Teknis Terkini untuk {pair_name} (Timeframe {escape_markdown_v2(timeframe_str)}):
- Harga Saat Ini: {harga_sekarang_str}
- RSI(14): {rsi_value_str}
- MACD: {macd_value_str}
- EMA (9/20/50/200): {ema_9_str} / {ema_20_str} / {ema_50_str} / {ema_200_str}
- Pola Candlestick Terdeteksi pada candle terakhir: {pattern_text}

Berikan rencana trading yang ringkas, actionable, dan siap pakai dalam BAHASA INDONESIA yang santai dan lugas (gaya trader profesional, bukan bahasa textbook atau laporan formal).

Tugas Utama Kamu (berdasarkan data di atas):
1.  Identifikasi STRATEGI UTAMA (BUY atau SELL) yang paling potensial saat ini.
2.  Sebutkan ZONA ENTRY yang jelas (bisa berupa rentang harga atau level kunci terdekat).
3.  Tentukan level TARGET PROFIT (TP1, dan TP2 jika relevan dan logis).
4.  Tentukan level STOP LOSS (SL) yang ketat namun masuk akal.
5.  Berikan SKENARIO ALTERNATIF (PLAN B) singkat: Apa yang harus dilakukan jika harga bergerak berlawanan dengan skenario utama (misalnya, breakout atau breakdown dari zona kunci)?

Gunakan Format Wajib Seperti Ini (sesuaikan angka, pair, dan strategi berdasarkan analisamu yang tajam):
- Pair: {pair_name} ({escape_markdown_v2(timeframe_str)})
- Strategi: [BUY/SELL]
- Zona Entry: $[angka] - $[angka] (atau sekitar $[angka])
- TP1: $[angka]
- TP2: $[angka] (opsional, tulis "N/A" jika tidak ada TP2 yang jelas)
- SL: $[angka]
- Plan B: [deskripsi ringkas aksi jika harga tidak sesuai ekspektasi, contoh: "Jika tembus support {low_candle_str}, pertimbangkan cut atau switch SELL target ke $[angka]. SL di atas {low_candle_str}."]

Contoh Gaya Bahasa dan Pendekatan Analisis (ADAPTASIKAN PENUH dengan data aktual, JANGAN hanya meniru angka atau kata-kata! Ini hanya CONTOH GAYA):
"Untuk {pair_name} di TF {escape_markdown_v2(timeframe_str)}, harga sekarang {harga_sekarang_str}. RSI {rsi_value_str}-an.
Kalau dari chart keliatan {pattern_text.lower() if patterns else 'lagi ranging aja nih'} dekat {ema_20_str}, dan ada sinyal konfirmasi (misal candle berikutnya menguat atau volume mendukung), gue sih condong ke spekulasi BUY.
Entry BUY coba di area {harga_sekarang_str} sampai {get_val(last_candle, 'low', p=df['close'].iloc[-1].size).lower()}.
SL ketat aja, di bawah {get_val(pd.Series({'val': low_candle_val * 0.995}), 'val', p=df['close'].iloc[-1].size).lower()} (misalnya).
TP1 incar ke {ema_50_str}, kalau kuat bisa lanjut TP2 ke {ema_200_str}.

Tapi, kalau ternyata harga malah longsor nembus support {low_candle_str}, jangan ngeyel BUY. Mending lepas atau bahkan bisa coba short sell kalau ada konfirmasi breakdown. Target sellnya bisa ke [sebutkan support logis berikutnya berdasarkan EMA atau histori, misal {get_val(pd.Series({'val': ema_200_val * 0.98}), 'val', p=df['close'].iloc[-1].size).lower()}]. SL untuk posisi short ini di atas {low_candle_str}."

LANGSUNG ke intinya, berikan output sesuai "Format Wajib". HINDARI kalimat pembuka/penutup seperti "Berikut adalah analisis..." atau "Selalu lakukan riset Anda sendiri...".
"""
    # Koreksi minor pada contoh gaya bahasa untuk p= pada get_val, asumsikan p didapat dari presisi harga.
    # Untuk contoh, p=2 atau p=4 mungkin lebih baik daripada df['close'].iloc[-1].size
    # Demi kesederhanaan, saya akan hardcode p sementara di contoh, atau hapus perhitungan dinamis di contoh.
    # Mari sederhanakan contoh agar tidak ada error:
    example_low_sl = f"{low_candle_val * 0.995:.{2}f}" # contoh p=2
    example_target_sell = f"{ema_200_val * 0.98:.{2}f}" if ema_200_val != 0 and not pd.isna(ema_200_val) else f"{harga_sekarang_val * 0.95:.{2}f}"


    # Memperbarui contoh gaya bahasa dengan p yang lebih aman/statis
    instructions_updated = instructions.replace(
        f"di bawah {get_val(pd.Series({'val': low_candle_val * 0.995}), 'val', p=df['close'].iloc[-1].size).lower()}",
        f"di bawah ${example_low_sl}"
    ).replace(
        f"misal {get_val(pd.Series({'val': ema_200_val * 0.98}), 'val', p=df['close'].iloc[-1].size).lower()}",
        f"misal ${example_target_sell}"
    ).replace( # Menghilangkan .lower() dari contoh harga karena get_val sudah memformat
        f"{get_val(last_candle, 'low', p=df['close'].iloc[-1].size).lower()}", 
        low_candle_str
    )


    final_prompt = f"{role_prompt}\n\n{instructions_updated}"
    return final_prompt

def get_ai_analysis(prompt: str) -> str:
    if not client:
        logger.warning("Klien OpenAI tidak aktif (API Key mungkin kosong). Mengembalikan pesan default.")
        return "Layanan AI tidak aktif saat ini."
    try:
        logger.info(f"Mengirim prompt ke OpenAI (panjang: {len(prompt)} karakter)...")
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5, # Sedikit diturunkan untuk lebih konsisten dengan format
            max_tokens=500,  # Output diharapkan tidak terlalu panjang, bisa disesuaikan
            timeout=45      # Timeout sedikit dinaikkan
        )
        analysis_content = response.choices[0].message.content.strip()
        logger.info("Berhasil menerima respons dari OpenAI.")
        return analysis_content
    except Exception as e:
        logger.error(f"Error saat menghubungi OpenAI API: {e}", exc_info=True)
        return "Terjadi kesalahan saat menghubungi layanan AI. Coba beberapa saat lagi."
# main.py (lanjutan)

def generate_sol_alerts(data_frames_by_timeframe: dict, pair_name_for_alert: str) -> str:
    """
    Menganalisis data multi-timeframe untuk SOL dan menghasilkan alert berdasarkan aturan custom.
    data_frames_by_timeframe: dict seperti {'5m': df_5m, '1H': df_1h}
                                Kunci adalah format OKX API (hasil standarisasi).
    pair_name_for_alert: nama pair (misal "SOL-USDT") untuk dimasukkan dalam pesan alert.
    """
    alerts = []
    escaped_pair_name = escape_markdown_v2(pair_name_for_alert)
    logger.info(f"Memulai generate_sol_alerts untuk {pair_name_for_alert} dengan timeframe: {list(data_frames_by_timeframe.keys())}")

    # --- CONTOH CARA MENGAKSES DATA ---
    # Selalu cek apakah DataFrame ada dan tidak kosong sebelum digunakan.
    # Gunakan key yang telah distandarisasi (misal, "5m", "1H")
    df_5m = data_frames_by_timeframe.get("5m")
    df_1H = data_frames_by_timeframe.get("1H")
    # df_15m = data_frames_by_timeframe.get("15m") 
    # df_4H = data_frames_by_timeframe.get("4H")

    last_5m = df_5m.iloc[-1] if df_5m is not None and not df_5m.empty else None
    last_1H = df_1H.iloc[-1] if df_1H is not None and not df_1H.empty else None
    # last_15m = df_15m.iloc[-1] if df_15m is not None and not df_15m.empty else None
    # last_4H = df_4H.iloc[-1] if df_4H is not None and not df_4H.empty else None

    # --- MULAI DEFINISIKAN ATURAN TRADING "LEBIH PEKA" ANDA UNTUK SOL DI SINI ---
    # Ini adalah contoh yang sangat sederhana. Kembangkan sesuai strategi Anda!

    # Contoh Aturan 1: Kondisi Oversold Agresif di TF Pendek dengan Konfirmasi TF Lebih Panjang
    if last_5m is not None and last_1H is not None:
        rsi_5m = last_5m.get('rsi', 100)
        ema20_5m = last_5m.get('ema_20', float('inf'))
        close_5m = last_5m.get('close', 0)
        
        rsi_1H = last_1H.get('rsi', 100)
        ema50_1H = last_1H.get('ema_50', float('inf')) # Misal, ingin 1H di atas support EMA50

        if rsi_5m < 20 and close_5m < ema20_5m * 0.995: # Harga di bawah EMA20 di 5m (misal, potensi pembalikan)
             if rsi_1H < 35 and last_1H.get('close',0) > ema50_1H : # 1H juga oversold tapi masih di atas EMA struktur
                alerts.append(f"🔥 *SOL Alert BUY Potensial (Agresif)*:\n  RSI 5m ({rsi_5m:.1f}) & 1H ({rsi_1H:.1f}) rendah. 5m di bawah EMA20, 1H di atas EMA50.\n  Harga 5m: {get_val(last_5m, 'close')}")

    # Contoh Aturan 2: Breakout di TF Pendek dengan Konfirmasi Volume & Tren di TF Panjang
    if last_15m is not None and last_1H is not None and len(df_15m) >=20: # Asumsikan 15m juga diminta
        # (Implementasikan logika breakout Anda di sini, misal menembus resistance lokal di 15m)
        # close_15m = last_15m.get('close')
        # high_prev_10_15m = df_15m['high'].iloc[-11:-1].max() # High 10 candle 15m sebelumnya
        # volume_15m = last_15m.get('volume')
        # avg_vol_15m = df_15m['volume'].iloc[-21:-1].mean()
        # close_1H = last_1H.get('close')
        # ema20_1H = last_1H.get('ema_20')
        #
        # if close_15m > high_prev_10_15m and volume_15m > 1.8 * avg_vol_15m and close_1H > ema20_1H:
        #     alerts.append(f"🚀 *SOL Alert BUY Breakout (15m)*:\n Tembus resistensi 15m dengan volume. Tren 1H mendukung.\n Harga 15m: {get_val(last_15m, 'close')}")
        pass # Hapus pass dan isi dengan logika Anda

    # Contoh Aturan 3: Divergence RSI/MACD (Ini lebih kompleks, butuh histori beberapa candle)
    # if ... (logika divergence) ... :
    #     alerts.append(f"⚠️ *SOL Alert Divergence Terdeteksi* ...")
    #     pass


    # --- AKHIR DARI DEFINISI ATURAN ---

    if not alerts:
        logger.info(f"Tidak ada sinyal otomatis khusus yang terdeteksi untuk {pair_name_for_alert}.")
        return "" # Kembalikan string kosong jika tidak ada alert
    
    logger.info(f"Sinyal otomatis SOL terdeteksi: {alerts}")
    return "\n\n".join(alerts)
# main.py (lanjutan)

def start(update, context):
    user = update.effective_user
    # Pastikan string f-string ini benar (sebelumnya ada SyntaxError jika multi-baris tanpa triple quotes)
    update.message.reply_html(f"Halo {user.mention_html()}!\nGunakan /sinyal NAMA_KOIN [tf1] [tf2]...")

def sinyal(update, context):
    args = context.args
    if not args:
        update.message.reply_text(
            "Format perintah: /sinyal NAMA_KOIN [tf1] [tf2] ...\n"
            "Contoh: /sinyal SOL 5m 1h\n"
            "Timeframe yang didukung: 1m, 5m, 15m, 30m, 1h, 4h, 1d, dll.\n"
            "Jika timeframe tidak diberikan, default ke 1H untuk analisis AI.",
            parse_mode=ParseMode.MARKDOWN_V2 # Gunakan ParseMode untuk pesan bantuan juga
        )
        return

    coin_name_arg = args[0].upper()
    requested_timeframes_input = args[1:] if len(args) > 1 else ["1h"] # Default ke "1h" (lowercase untuk map)

    target_pair = None
    for p_name in PAIRS:
        if p_name.startswith(coin_name_arg.split('-')[0]): # Memungkinkan input "SOL" atau "SOL-USDT"
            target_pair = p_name
            break
    
    if not target_pair:
        update.message.reply_text(f"Nama koin '{escape_markdown_v2(coin_name_arg)}' tidak ditemukan atau tidak didukung. Contoh: SOL, BTC.")
        return

    timeframes_to_process_okx = [] # Format OKX API
    user_friendly_tfs_display = []   # Format input pengguna untuk tampilan

    for tf_input in requested_timeframes_input:
        tf_lower = tf_input.lower() # Normalisasi input pengguna ke lowercase untuk dicocokkan dengan map
        if tf_lower in SUPPORTED_TF_MAP:
            okx_format_tf = SUPPORTED_TF_MAP[tf_lower]
            if okx_format_tf not in timeframes_to_process_okx: # Hindari duplikat
                 timeframes_to_process_okx.append(okx_format_tf)
                 user_friendly_tfs_display.append(tf_input) # Simpan format asli untuk display
        else:
            update.message.reply_text(f"Timeframe '{escape_markdown_v2(tf_input)}' tidak dikenal/didukung. Coba 1m, 5m, 1h, 4h, 1d.")
            return
            
    if not timeframes_to_process_okx:
        if len(args) == 1: # Hanya /sinyal NAMA_KOIN
            timeframes_to_process_okx = [SUPPORTED_TF_MAP["1h"]] # Default ke 1H jika tidak ada TF diberikan
            user_friendly_tfs_display = ["1h (Default)"]
        else: # Ada argumen TF tapi semuanya tidak valid
            update.message.reply_text("Tidak ada timeframe valid yang diproses.")
            return

    processing_message = None
    try:
        processing_message = update.message.reply_text(
            f"⏳ Menganalisis {escape_markdown_v2(target_pair)} untuk timeframe: {escape_markdown_v2(', '.join(user_friendly_tfs_display))}...",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except Exception as e_proc_msg: # Error jika pesan "Menganalisis" gagal dikirim
        logger.error(f"Gagal mengirim pesan 'Menganalisis...': {e_proc_msg}")


    combined_results_parts = []
    data_frames_collection = {} # Untuk menyimpan df per timeframe

    # Tahap 1: Ambil semua data dan simpan (khususnya jika SOL untuk MTF alert)
    for i, tf_okx in enumerate(timeframes_to_process_okx):
        user_tf_str_display = user_friendly_tfs_display[i]
        logger.info(f"Mengambil data untuk {target_pair} - TF {tf_okx} (display {user_tf_str_display})")
        df = fetch_okx_candles(target_pair, tf_okx, 220) # Sesuaikan limit jika perlu
        if not df.empty:
            df = analyze_indicators(df)
            data_frames_collection[tf_okx] = df # Kunci menggunakan format OKX
        else:
            logger.warning(f"Data kosong untuk {target_pair} - TF {tf_okx}")
            # Catat bahwa data untuk TF ini kosong, agar bisa diinfo ke pengguna
            data_frames_collection[tf_okx] = pd.DataFrame() 


    # Tahap 2: Generate Sinyal Otomatis KHUSUS untuk SOL jika ada data
    if target_pair == "SOL-USDT":
        # Filter hanya timeframe yang datanya berhasil diambil untuk SOL alerts
        valid_dfs_for_sol = {tf: df for tf, df in data_frames_collection.items() if not df.empty}
        if valid_dfs_for_sol:
            sol_auto_alerts_text = generate_sol_alerts(valid_dfs_for_sol, target_pair)
            if sol_auto_alerts_text:
                combined_results_parts.append(f"🚨 *Sinyal Otomatis untuk {escape_markdown_v2(target_pair)}*:\n{sol_auto_alerts_text}")
        elif not any(data_frames_collection.values()): # Jika semua df untuk SOL kosong
             combined_results_parts.append(f"ℹ️ _Tidak ada data yang cukup untuk menghasilkan sinyal otomatis {escape_markdown_v2(target_pair)}._")


    # Tahap 3: Generate Analisis AI untuk setiap timeframe yang berhasil diambil datanya
    for i, tf_okx in enumerate(timeframes_to_process_okx):
        user_tf_str_display = user_friendly_tfs_display[i]
        df = data_frames_collection.get(tf_okx)

        if df is None or df.empty: # Jika data tidak berhasil diambil di tahap 1
            combined_results_parts.append(f"⚠️ _{escape_markdown_v2(target_pair)} ({escape_markdown_v2(user_tf_str_display)}): Data tidak tersedia atau gagal diproses._")
            continue

        # Analisis AI (selalu jalankan, atau kondisional jika Anda mau)
        # if target_pair == "SOL-USDT" and sol_auto_alerts_text:
        #     logger.info(f"Skipping AI analysis for SOL {user_tf_str_display} as auto-alert was generated.")
        #     continue # Atau tampilkan AI sebagai tambahan

        logger.info(f"Membuat prompt AI untuk {target_pair} - TF {user_tf_str_display}")
        alert_tf_specific = check_extreme_alert(df, target_pair) 
        prompt_tf = build_ai_analysis_prompt(df, target_pair, user_tf_str_display)
        ai_analysis_tf_raw = get_ai_analysis(prompt_tf)
        escaped_ai_analysis_tf = escape_markdown_v2(ai_analysis_tf_raw)

        escaped_pair_tf_header = escape_markdown_v2(target_pair)
        header_tf_content = f"📡 *Analisis AI: {escaped_pair_tf_header} ({escape_markdown_v2(user_tf_str_display)})*"
        
        current_tf_analysis_text = ""
        if alert_tf_specific: # Alert umum dari check_extreme_alert
            current_tf_analysis_text += alert_tf_specific + "\n\n"
        current_tf_analysis_text += header_tf_content + "\n"
        current_tf_analysis_text += escaped_ai_analysis_tf
        
        combined_results_parts.append(current_tf_analysis_text)

    # Hapus pesan "Menganalisis..."
    if processing_message:
        try:
            context.bot.delete_message(chat_id=update.effective_chat.id, message_id=processing_message.message_id)
        except Exception as e_del_msg:
            logger.warning(f"Gagal menghapus pesan 'Menganalisis...': {e_del_msg}")

    if combined_results_parts:
        final_message_output = "\n\n---\n\n".join(combined_results_parts)
        
        max_msg_len = 4096 
        if len(final_message_output) > max_msg_len:
            logger.info(f"Pesan untuk {target_pair} terlalu panjang ({len(final_message_output)} chars), akan dibagi.")
            sent_something = False
            for i in range(0, len(final_message_output), max_msg_len):
                chunk = final_message_output[i:i+max_msg_len]
                try:
                    update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN_V2)
                    sent_something = True
                except Exception as e_chunk:
                    logger.error(f"GAGAL KIRIM chunk pesan MTF untuk {target_pair}: {e_chunk}. Gagal pada chunk dimulai: {chunk[:50]}...")
                    # Jika satu chunk gagal, mungkin yang lain juga. Kirim pesan error umum jika belum ada yg terkirim.
                    if not sent_something:
                         update.message.reply_text("Terjadi kesalahan saat mengirim sebagian analisis. Beberapa bagian mungkin hilang.", parse_mode=ParseMode.MARKDOWN_V2)
                    break 
        else:
            try:
                update.message.reply_text(final_message_output, parse_mode=ParseMode.MARKDOWN_V2)
            except Exception as e_final:
                logger.error(f"GAGAL KIRIM pesan gabungan MTF untuk {target_pair}: {e_final}. Awal pesan: {final_message_output[:100]}...")
                update.message.reply_text("Terjadi kesalahan saat mengirim analisis.", parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"Analisis MTF untuk {target_pair} ({', '.join(user_friendly_tfs_display)}) telah selesai diproses.")
    else:
        update.message.reply_text(f"Tidak ada analisis yang dapat dihasilkan untuk {escape_markdown_v2(target_pair)} dengan timeframe yang diminta.")
# main.py (lanjutan)

def loop_runner(bot: Bot, interval_minutes: int = 30):
    # loop_runner saat ini masih menggunakan logika lama (single TF 1H, tanpa alert SOL khusus MTF)
    # Jika Anda ingin loop_runner juga MTF & alert SOL, logikanya perlu diadaptasi serupa dengan fungsi sinyal.
    logger.info(f"Memulai loop_runner dengan interval {interval_minutes} menit.")
    while TELEGRAM_CHAT_ID: # Pastikan TELEGRAM_CHAT_ID sudah int
        logger.info(f"Memulai siklus loop_runner untuk semua PAIRS...")
        for current_pair_loop in PAIRS:
            try:
                logger.info(f"Loop runner: Memproses {current_pair_loop}...")
                # Menggunakan timeframe default 1H untuk loop_runner
                default_tf_loop = SUPPORTED_TF_MAP.get("1h", "1H") # Ambil format OKX untuk 1H
                user_tf_display_loop = "1H"

                df_loop = fetch_okx_candles(current_pair_loop, default_tf_loop, 220)
                
                if df_loop.empty:
                    logger.warning(f"Loop runner: Data kosong untuk {current_pair_loop} TF {user_tf_display_loop}.")
                    # Anda bisa mengirim notifikasi ke TELEGRAM_CHAT_ID jika data kosong, atau silent.
                    # bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"⚠️ Data tidak tersedia untuk {escape_markdown_v2(current_pair_loop)} ({escape_markdown_v2(user_tf_display_loop)}) di loop_runner.")
                    time.sleep(1) # Jeda singkat jika data kosong, sebelum lanjut ke pair berikutnya
                    continue
                
                df_loop = analyze_indicators(df_loop)
                
                msg_parts_loop = []

                # Alert Otomatis SOL jika ini adalah SOL-USDT
                if current_pair_loop == "SOL-USDT":
                    # Untuk loop_runner, kita mungkin hanya ingin alert dari satu set TF default, misal 5m dan 1H
                    # Jadi kita perlu fetch TF tambahan untuk SOL di sini jika belum ada.
                    # Atau, sederhananya, loop_runner bisa punya logika alert SOL yang lebih simpel atau tidak sama sekali.
                    # Untuk contoh ini, kita akan coba buat dia fetch data MTF untuk SOL juga.
                    sol_dfs_loop = {default_tf_loop: df_loop} # Mulai dengan df 1H yang sudah ada
                    
                    # Fetch TF tambahan yang dibutuhkan oleh generate_sol_alerts, misal '5m'
                    if "5m" not in sol_dfs_loop: # Hanya fetch jika belum ada
                        df_sol_5m_loop = fetch_okx_candles(current_pair_loop, SUPPORTED_TF_MAP.get("5m","5m"), 220)
                        if not df_sol_5m_loop.empty:
                            sol_dfs_loop[SUPPORTED_TF_MAP.get("5m","5m")] = analyze_indicators(df_sol_5m_loop)
                    
                    # (Tambahkan TF lain jika generate_sol_alerts Anda membutuhkannya)

                    valid_sol_dfs_loop = {tf: df for tf, df in sol_dfs_loop.items() if not df.empty}
                    if valid_sol_dfs_loop:
                        sol_alerts_loop = generate_sol_alerts(valid_sol_dfs_loop, current_pair_loop)
                        if sol_alerts_loop:
                            msg_parts_loop.append(f"🚨 *Sinyal Otomatis untuk {escape_markdown_v2(current_pair_loop)}*:\n{sol_alerts_loop}")

                # Analisis AI (selalu untuk semua koin di loop_runner)
                alert_content_loop = check_extreme_alert(df_loop, current_pair_loop)
                if alert_content_loop:
                     msg_parts_loop.append(alert_content_loop)

                prompt_loop = build_ai_analysis_prompt(df_loop, current_pair_loop, user_tf_display_loop)
                ai_analysis_raw_loop = get_ai_analysis(prompt_loop)
                escaped_ai_analysis_loop = escape_markdown_v2(ai_analysis_raw_loop)
                
                escaped_pair_header_loop = escape_markdown_v2(current_pair_loop)
                header_loop = f"📡 *Analisis AI: {escaped_pair_header_loop} ({escape_markdown_v2(user_tf_display_loop)})*"
                msg_parts_loop.append(f"{header_loop}\n{escaped_ai_analysis_loop}")

                final_msg_loop = "\n\n---\n\n".join(filter(None, msg_parts_loop)) # filter(None,...) untuk menghapus string kosong

                if final_msg_loop:
                    # Kirim pesan, tangani jika terlalu panjang
                    max_msg_len = 4096 
                    if len(final_msg_loop) > max_msg_len:
                        logger.info(f"Loop runner: Pesan untuk {current_pair_loop} terlalu panjang ({len(final_msg_loop)} chars), akan dibagi.")
                        for i in range(0, len(final_msg_loop), max_msg_len):
                            chunk = final_msg_loop[i:i+max_msg_len]
                            try:
                                bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=chunk, parse_mode=ParseMode.MARKDOWN_V2)
                            except Exception as e_chunk_loop:
                                logger.warning(f"Loop runner: GAGAL KIRIM chunk pesan untuk {current_pair_loop}: {e_chunk_loop}.")
                                break # Hentikan pengiriman chunk berikutnya jika satu gagal
                    else:
                        try:
                            bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=final_msg_loop, parse_mode=ParseMode.MARKDOWN_V2)
                        except Exception as e_final_loop:
                            logger.warning(f"Loop runner: GAGAL KIRIM pesan untuk {current_pair_loop}: {e_final_loop}.")
                    logger.info(f"Loop runner: Pesan untuk {current_pair_loop} dikirim ke chat ID {TELEGRAM_CHAT_ID}.")
                else:
                    logger.info(f"Loop runner: Tidak ada pesan yang dihasilkan untuk {current_pair_loop}.")

            except Exception as e_pair_loop:
                logger.error(f"Error saat memproses {current_pair_loop} di loop_runner: {e_pair_loop}", exc_info=True)
            
            time.sleep(5) # Jeda antar pair di loop_runner untuk menghindari rate limit API

        logger.info(f"Siklus loop_runner selesai, menunggu {interval_minutes} menit...")
        time.sleep(interval_minutes * 60)


def main():
    if not TELEGRAM_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN tidak ditemukan di file .env. Bot tidak dapat dimulai.")
        return
    
    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

def error_handler(update, context):
    logger.error(msg="Exception dalam polling Telegram:", exc_info=context.error)

dp.add_error_handler(error_handler)

dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("sinyal", sinyal, pass_args=True))

    # Membuat thread untuk updater.start_polling()
    polling_thread = threading.Thread(target=updater.start_polling, daemon=True)
    polling_thread.start()
    logger.info("Bot aktif dan polling pembaruan dari Telegram...")

    if TELEGRAM_CHAT_ID:
        logger.info(f"Loop runner akan mengirim pesan ke TELEGRAM_CHAT_ID: {TELEGRAM_CHAT_ID}")
        # Inisialisasi objek Bot di sini karena dibutuhkan oleh loop_runner
        # Pastikan ini tidak menyebabkan konflik jika Updater juga membuat instance Bot internal
        # Biasanya aman jika hanya untuk mengirim pesan.
        bot_for_loop = Bot(token=TELEGRAM_TOKEN)
        
        # Membuat thread untuk loop_runner agar tidak memblokir main thread jika ada updater.idle()
        # Namun, jika tidak ada updater.idle(), loop_runner bisa berjalan di main thread setelah polling dimulai.
        # Jika Anda ingin loop_runner dan polling berjalan paralel dan program tetap hidup sampai Ctrl+C,
        # updater.idle() diperlukan setelah memulai thread loop_runner.
        
        loop_runner_thread = threading.Thread(target=loop_runner, args=(bot_for_loop, 30), daemon=True) # Interval 30 menit
        loop_runner_thread.start()
        logger.info("Loop runner dimulai dalam thread terpisah.")
        
        # updater.idle() akan menjaga program tetap berjalan sampai dihentikan (misal dengan Ctrl+C)
        # Ini penting jika kedua thread (polling dan loop_runner) adalah daemon.
        # Jika tidak ada updater.idle(), program bisa langsung keluar jika main thread selesai.
        try:
            while True:
                time.sleep(3600) # Jaga main thread tetap hidup, atau gunakan updater.idle() jika tidak ada loop lain di main()
        except KeyboardInterrupt:
            logger.info("Bot dihentikan oleh pengguna (KeyboardInterrupt).")
            updater.stop() # Hentikan updater dengan bersih
            logger.info("Updater dihentikan.")
            # Thread daemon akan berhenti otomatis saat program utama keluar.
        except Exception as e_main:
            logger.critical(f"Error kritis di main thread: {e_main}", exc_info=True)

    else:
        logger.info("TELEGRAM_CHAT_ID tidak dikonfigurasi. Loop runner otomatis tidak akan berjalan.")
        logger.info("Bot hanya akan merespons perintah. Gunakan Ctrl+C untuk menghentikan.")
        updater.idle() # Jaga bot tetap berjalan untuk merespons perintah jika tidak ada loop runner

if __name__ == "__main__":
    main()

