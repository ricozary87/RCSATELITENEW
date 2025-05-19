import pandas as pd
import time 
from bot_config import logger, CLIENT_OPENAI, OPENAI_MODEL
from utils.utils import escape_markdown_v2, get_val

def build_ai_analysis_prompt(df: pd.DataFrame, pair_name: str, timeframe_str: str) -> str:
    if df.empty or len(df) < 1:
        return f"Tidak dapat membuat analisa untuk {pair_name} ({timeframe_str}), data tidak cukup."

    last_candle = df.iloc[-1]
    patterns = []
    for pattern_col, label in [
        ('doji', "Doji"),
        ('bullish_engulfing', "Bullish Engulfing"),
        ('bearish_engulfing', "Bearish Engulfing"),
        ('hammer', "Hammer"),
        ('shooting_star', "Shooting Star")
    ]:
        if last_candle.get(pattern_col, False):
            patterns.append(label)
    pattern_text = ", ".join(patterns) if patterns else "Tidak ada pola candlestick signifikan terdeteksi pada candle terakhir."

    harga_sekarang_val = float(last_candle.get('close', 0))
    low_candle_val = float(last_candle.get('low', harga_sekarang_val * 0.99))
    ema_9_val = float(last_candle.get('ema_9', 0))
    ema_20_val = float(last_candle.get('ema_20', 0))
    ema_50_val = float(last_candle.get('ema_50', 0))
    ema_200_val = float(last_candle.get('ema_200', 0))

    harga_sekarang_str = get_val(last_candle, 'close')
    rsi_value_str = get_val(last_candle, 'rsi', include_prefix=False)
    macd_value_str = get_val(last_candle, 'macd', include_prefix=False)
    ema_9_str = get_val(last_candle, 'ema_9')
    ema_20_str = get_val(last_candle, 'ema_20')
    ema_50_str = get_val(last_candle, 'ema_50')
    ema_200_str = get_val(last_candle, 'ema_200')
    low_candle_str = get_val(last_candle, 'low')

    role_prompt = (
        "Kamu adalah 'RC SATELLITE GPT SUPREME', seorang analis trading scalping dan intraday yang sangat berpengalaman. "
        "Kamu memberikan rekomendasi yang tajam, 'to the point', lugas, dan siap pakai. Fokus pada aksi dan strategi praktis, "
        "hindari bahasa teoritis atau kalimat-kalimat pengantar/penutup yang tidak perlu. Anggap audiensmu adalah trader aktif yang butuh keputusan cepat."
    )

    precision = 4 if "BTC" in pair_name else 2
    sl_example_val = low_candle_val * 0.995 if not pd.isna(low_candle_val) else harga_sekarang_val * 0.99
    target_sell_example_val = ema_200_val * 0.98 if not pd.isna(ema_200_val) and ema_200_val != 0 else harga_sekarang_val * 0.95
    sl_example_str = f"{sl_example_val:.{precision}f}"
    target_sell_example_str = f"{target_sell_example_val:.{precision}f}"

    if not pd.isna(ema_50_val) and ema_50_val != 0:
        ema_50_example_str = get_val(last_candle, 'ema_50', p=precision)
    else:
        ema_50_example_str = f"${harga_sekarang_val * 1.02:.{precision}f} (target alternatif)"

    if not pd.isna(ema_200_val) and ema_200_val != 0:
        ema_200_example_str = get_val(last_candle, 'ema_200', p=precision)
    else:
        ema_200_example_str = f"${harga_sekarang_val * 1.05:.{precision}f} (target alternatif)"

    instructions = f"""
Berdasarkan data teknikal terkini untuk {pair_name} (Timeframe {escape_markdown_v2(timeframe_str)}):
- Harga Saat Ini: {harga_sekarang_str}
- RSI(14): {rsi_value_str}
- MACD: {macd_value_str}
- EMA (9/20/50/200): {ema_9_str} / {ema_20_str} / {ema_50_str} / {ema_200_str}
- Pola Candlestick Terdeteksi pada candle terakhir: {pattern_text}

Berikan rencana trading yang ringkas, actionable, dan siap pakai dalam BAHASA INDONESIA yang santai dan lugas.

Tugas Utama Kamu:
1. STRATEGI UTAMA (BUY atau SELL)
2. Zona Entry
3. Target Profit (TP1, TP2)
4. Stop Loss (SL)
5. Plan B

Format:
- Pair: {pair_name} ({escape_markdown_v2(timeframe_str)})
- Strategi: [BUY/SELL]
- Zona Entry: $[angka] - $[angka]
- TP1: $[angka]
- TP2: $[angka]
- SL: $[angka]
- Plan B: Jika tembus support {low_candle_str}, pertimbangkan cut atau switch SELL target ke ${target_sell_example_str}. SL di atas {low_candle_str}.

Contoh gaya:
Untuk {pair_name} di TF {escape_markdown_v2(timeframe_str)}, harga sekarang {harga_sekarang_str}. RSI {rsi_value_str}-an.
Kalau dari chart keliatan {pattern_text.lower()} dekat {ema_20_str}, dan ada konfirmasi, bisa coba BUY.
Entry sekitar {harga_sekarang_str} - {low_candle_str}. SL di bawah ${sl_example_str}. TP1 ke {ema_50_example_str}, TP2 ke {ema_200_example_str}.
"""

    final_prompt = f"{role_prompt}\n\n{instructions}"
    return final_prompt

def get_ai_analysis(prompt: str) -> str:
    if not CLIENT_OPENAI:
        logger.warning("Klien OpenAI tidak aktif.")
        return "Layanan AI tidak aktif."

    try:
        logger.info(f"Mengirim prompt ke OpenAI (model: {OPENAI_MODEL}, panjang: {len(prompt)} karakter)...")
        start_time = time.time()
        response = CLIENT_OPENAI.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=600,
            timeout=90
        )
        elapsed = time.time() - start_time
        logger.info(f"Berhasil menerima respons dari OpenAI dalam {elapsed:.2f} detik.")

        if response.choices and response.choices[0].message and response.choices[0].message.content:
            return response.choices[0].message.content.strip()
        else:
            return "Gagal mendapatkan respon AI."

    except Exception as e:
        logger.error(f"Error saat menghubungi OpenAI API: {e}", exc_info=True)
        return f"Terjadi kesalahan saat menghubungi layanan AI. Coba beberapa saat lagi."
