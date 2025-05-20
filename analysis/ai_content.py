import os
import time
import pandas as pd
from openai import OpenAI
from bot_config import logger
from utils.utils import escape_markdown_v2, get_val

# === Inisialisasi OpenAI Client (Project Key Support) ===
CLIENT_OPENAI = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    project=os.getenv("OPENAI_PROJECT_ID")
)

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

def build_ai_analysis_prompt(df: pd.DataFrame, pair_name: str, timeframe_str: str) -> str:
    if df.empty:
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
        if last_candle.get(pattern_col):
            patterns.append(label)
    pattern_text = ", ".join(patterns) if patterns else "Tidak ada pola signifikan"

    close_val = last_candle.get("close", None)
    low_val = last_candle.get("low", None)
    ema_9 = last_candle.get("ema_9", None)
    ema_20 = last_candle.get("ema_20", None)
    ema_50 = last_candle.get("ema_50", None)
    ema_200 = last_candle.get("ema_200", None)
    rsi = last_candle.get("rsi", None)
    macd = last_candle.get("macd", None)

    precision = 4 if "BTC" in pair_name.upper() else 2

    close_str = f"${close_val:.{precision}f}" if close_val else "N/A"
    low_str = f"${low_val:.{precision}f}" if low_val else "N/A"
    ema_9_str = f"${ema_9:.{precision}f}" if ema_9 else "N/A"
    ema_20_str = f"${ema_20:.{precision}f}" if ema_20 else "N/A"
    ema_50_str = f"${ema_50:.{precision}f}" if ema_50 else "N/A"
    ema_200_str = f"${ema_200:.{precision}f}" if ema_200 else "N/A"
    rsi_str = f"{rsi:.1f}" if rsi is not None else "N/A"
    macd_str = f"{macd:.3f}" if macd is not None else "N/A"

    sl_val = low_val * 0.995 if low_val else None
    tp1_val = ema_50 if ema_50 else None
    tp2_val = ema_200 if ema_200 else None

    sl_str = f"${sl_val:.{precision}f}" if sl_val else "N/A"
    tp1_str = f"${tp1_val:.{precision}f}" if tp1_val else "N/A"
    tp2_str = f"${tp2_val:.{precision}f}" if tp2_val else "N/A"

    role_prompt = (
        "Kamu adalah 'RC SATELLITE GPT SUPREME', AI analis scalping dan intraday.\n"
        "Fokus ke strategi siap eksekusi. Jangan berteori. Tulis tajam, ringkas, dan langsung ke aksi."
    )

    instructions = f"""
📊 Data untuk {escape_markdown_v2(pair_name)} ({escape_markdown_v2(timeframe_str)}):
- Harga Saat Ini: {close_str}
- RSI: {rsi_str}
- MACD: {macd_str}
- EMA: {ema_9_str}, {ema_20_str}, {ema_50_str}, {ema_200_str}
- Pola Candle Terakhir: {pattern_text}

🎯 Tulis strategi ringkas, dalam format:
- Pair: {pair_name} ({timeframe_str})
- Strategi: BUY / SELL
- Zona Entry: $... - $...
- TP1: {tp1_str}
- TP2: {tp2_str}
- SL: {sl_str}
- Plan B: Jika support {low_str} jebol, cut loss atau tunggu validasi baru.

Gaya bebas, tapi langsung ke intinya. Fokus ke keputusan dan arah harga.
"""

    return f"{role_prompt}\n\n{instructions}"

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
        return "❌ Terjadi kesalahan saat menghubungi layanan AI."

def generate_combined_prompt(pair: str, data_dict: dict, smc_summary: dict) -> str:
    prompt = [
        f"Kamu adalah RC SATELLITE, AI trading profesional untuk {pair}. Tugasmu adalah menyimpulkan validitas ENTRY berdasarkan data pre-analyzed di bawah."
    ]

    tf_summary = []

    for tf, df in data_dict.items():
        if df is None or df.empty:
            continue

        last = df.iloc[-1]
        tf_label = tf.upper()
        section = [f"\n📊 Timeframe {tf_label}"]

        close = last.get("close", 0)
        rsi = last.get("rsi", 0)
        macd = last.get("macd", 0)
        macd_signal = last.get("macd_signal", 0)
        ema20 = last.get("ema_20", 0)
        ema50 = last.get("ema_50", 0)
        ema200 = last.get("ema_200", 0)
        volume = last.get("volume", 0)

        if rsi < 30:
            section.append("- RSI oversold → potensi rebound.")
        elif rsi > 70:
            section.append("- RSI overbought → waspadai koreksi.")

        if macd > macd_signal:
            section.append("- MACD cross up → momentum bullish.")
        else:
            section.append("- MACD cross down → momentum lemah.")

        if close > ema20 > ema50:
            section.append("- Harga di atas EMA → tren naik aktif.")
        elif close < ema20 < ema50:
            section.append("- Harga di bawah EMA → tren turun aktif.")

        section.append(f"- Volume: {volume:.2f}")

        smc = smc_summary.get(tf)
        if smc:
            section.append(f"- Struktur SMC terdeteksi: {', '.join(smc)}")

        tf_summary.append("\n".join(section))

    prompt.append("\n".join(tf_summary))

    prompt.append(
        """
TUGASMU:
1. Tentukan apakah saat ini layak ENTRY atau tidak.
2. Jika layak, berikan ZONA ENTRY, SL, TP1, TP2.
3. Jika tidak layak, jelaskan alasannya dan tunggu validasi apa.
4. Jika sinyal tumpang tindih antar timeframe, utamakan timeframe yang dominan.

FORMAT JAWABAN:
- Pair: ...
- Strategi: BUY / SELL / WAIT
- Entry: $... - $...
- TP1: $...
- TP2: $...
- SL: $...
- Plan B: Jika gagal, skenario cut atau switch.
- Catatan teknikal: (tulis ringkasan tajam teknikal semua TF)

Jawab dalam bahasa Indonesia yang lugas dan actionable. Jangan mengulang ulang. Fokus ke eksekusi.
"""
    )

    return "\n".join(prompt)
