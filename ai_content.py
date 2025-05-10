import pandas as pd
import time 
from bot_config import logger, CLIENT_OPENAI, OPENAI_MODEL
from utils import escape_markdown_v2, get_val

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

Berikan rencana trading yang ringkas, actionable, dan siap pakai dalam BAHASA INDONESIA yang santai dan lugas (gaya trader profesional, bukan bahasa textbook atau laporan formal).

Tugas Utama Kamu (berdasarkan data di atas):
1.  Identifikasi STRATEGI UTAMA (BUY atau SELL) yang paling potensial saat ini.
2.  Sebutkan ZONA ENTRY yang jelas (bisa berupa rentang harga atau level kunci terdekat).
3.  Tentukan level TARGET PROFIT (TP1, dan TP2 jika relevan dan logis).
4.  Tentukan level STOP LOSS (SL) yang ketat namun masuk akal.
5.  Berikan SKENARIO ALTERNATIF (PLAN B) singkat: Apa yang harus dilakukan jika harga bergerak berlawanan dengan skenario utama.

Gunakan Format Wajib Seperti Ini:
- Pair: {pair_name} ({escape_markdown_v2(timeframe_str)})
- Strategi: [BUY/SELL]
- Zona Entry: $[angka] - $[angka] (atau sekitar $[angka])
- TP1: $[angka]
- TP2: $[angka] (jika ada)
- SL: $[angka]
- Plan B: Jika tembus support {low_candle_str}, pertimbangkan cut atau switch SELL target ke ${target_sell_example_str}. SL di atas {low_candle_str}.

Contoh gaya penulisan:
"Untuk {pair_name} di TF {escape_markdown_v2(timeframe_str)}, harga sekarang {harga_sekarang_str}. RSI {rsi_value_str}-an.
Kalau dari chart keliatan {pattern_text.lower() if patterns else 'lagi ranging aja nih'} dekat {ema_20_str}, dan ada sinyal konfirmasi (misal candle berikutnya menguat atau volume mendukung), gue sih condong ke spekulasi BUY.
Entry BUY coba di area {harga_sekarang_str} sampai {low_candle_str}. SL ketat aja, di bawah ${sl_example_str}. TP1 incar ke {ema_50_example_str}, lanjut TP2 ke {ema_200_example_str}."

LANGSUNG ke intinya, berikan output sesuai "Format Wajib".
"""
    final_prompt = f"{role_prompt}\n\n{instructions}"
    return final_prompt

def get_ai_analysis(prompt: str) -> str:
    if not CLIENT_OPENAI:
        logger.warning("Klien OpenAI tidak aktif (API Key mungkin kosong). Mengembalikan pesan default.")
        return "Layanan AI tidak aktif saat ini."
    try:
        logger.info(f"Mengirim prompt ke OpenAI (model: {OPENAI_MODEL}, panjang: {len(prompt)} karakter)...")
        logger.debug(f"Sampel awal prompt: {prompt[:250]}...")
        start_time_openai = time.time()
        response = CLIENT_OPENAI.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=600,
            timeout=90
        )
        end_time_openai = time.time()
        logger.info(f"Berhasil menerima respons dari OpenAI dalam {end_time_openai - start_time_openai:.2f} detik.")

        if response.choices and response.choices[0].message and response.choices[0].message.content:
            analysis_content = response.choices[0].message.content.strip()
            logger.debug(f"Konten AI diterima (awal): {analysis_content[:250]}...")
            return analysis_content
        else:
            logger.error("Respons OpenAI tidak berisi pilihan atau konten pesan yang diharapkan.")
            return "Gagal mendapatkan konten analisis dari AI (respons tidak valid)."

    except Exception as e:
        logger.error(f"Error saat menghubungi OpenAI API atau memproses respons: {e}", exc_info=True)
        error_message_detail = "Detail error API tidak tersedia."
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_data = e.response.json()
                error_message_detail = error_data.get("error", {}).get("message", str(error_data))
            except:
                error_message_detail = str(e.response.content) if hasattr(e.response, 'content') else str(e.response)
        elif hasattr(e, 'message'):
            error_message_detail = e.message

        logger.error(f"Detail spesifik error API (jika ada): {error_message_detail}")
        return f"Terjadi kesalahan saat menghubungi layanan AI: {escape_markdown_v2(error_message_detail)}. Coba beberapa saat lagi."
