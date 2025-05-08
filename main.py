#from pathlib import Path
from textwrap import dedent

code = """# ✅ RCSATELLITENEW - BOT VERSI STABIL PYTHON-TELEGRAM-BOT v13.15
# Pastikan Anda menjalankan ini di sel pertama notebook Colab jika belum terinstal
# !pip install python-telegram-bot==13.15 ta python-dotenv openai --quiet

import requests
import pandas as pd
import ta
import time
import os
import logging
import threading
from decimal import Decimal, InvalidOperation
from openai import OpenAI
from dotenv import load_dotenv
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters  # Filters ditambahkan jika diperlukan di masa depan
from telegram import Bot  # Ditambahkan untuk loop_runner jika ingin menggunakan instance Bot

# === KONFIGURASI LOGGING ===
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === INIT ===
load_dotenv()  # Muat variabel dari file .env

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")  # Default model jika tidak diset
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID_STR = os.getenv("TELEGRAM_CHAT_ID")

# Validasi TELEGRAM_CHAT_ID
if TELEGRAM_CHAT_ID_STR is None:
    logger.error("TELEGRAM_CHAT_ID tidak ditemukan di file .env. Harap set variabel ini.")
    TELEGRAM_CHAT_ID = None  # Atau set ke None dan tangani di loop_runner
else:
    try:
        TELEGRAM_CHAT_ID = int(TELEGRAM_CHAT_ID_STR)
    except ValueError:
        logger.error(f"TELEGRAM_CHAT_ID '{TELEGRAM_CHAT_ID_STR}' tidak valid. Harus berupa angka integer.")
        TELEGRAM_CHAT_ID = None

# Inisialisasi OpenAI Client
if not OPENAI_API_KEY:
    logger.warning("OPENAI_API_KEY tidak ditemukan. Fungsi AI tidak akan bekerja.")
    client = None
else:
    client = OpenAI(api_key=OPENAI_API_KEY)

PAIRS = ["SOL-USDT", "BTC-USDT", "ETH-USDT", "XRP-USDT"]  # Daftar pair yang akan dianalisa

# === FUNGSI AMBIL DATA OKX ===
def fetch_okx_candles(pair="SOL-USDT", interval="1H", limit=100):
    """Mengambil data candlestick dari OKX API."""
    url = f"https://www.okx.com/api/v5/market/candles?instId={pair}&bar={interval}&limit={limit}"
    try:
        res = requests.get(url, timeout=10)  # Tambahkan timeout
        res.raise_for_status()  # Akan raise HTTPError jika status code 4xx/5xx
        
        response_data = res.json()
        
        if response_data.get("code") != "0":  # OKX API biasanya mengembalikan 'code': '0' untuk sukses
            logger.error(f"OKX API Error untuk {pair}: {response_data.get('msg', 'Pesan error tidak diketahui')}")
            return pd.DataFrame()

        data = response_data.get('data')
        if not data:
            logger.warning(f"Tidak ada data candlestick yang diterima dari OKX untuk {pair}.")
            return pd.DataFrame()

        data.reverse()  # Data dari OKX biasanya terbaru di awal, dibalik agar tertua di awal
        df = pd.DataFrame(data, columns=[
            'ts', 'open', 'high', 'low', 'close', 'volume', 'volCcy', 'volCcyQuote', 'confirm'
        ])
        
        # Konversi tipe data
        df['ts'] = pd.to_datetime(pd.to_numeric(df['ts']), unit='ms')
        numeric_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')  # errors='coerce' akan mengubah non-numerik menjadi NaN
        
        df.dropna(subset=numeric_cols, inplace=True)  # Hapus baris dengan NaN di kolom numerik penting

        return df[['ts', 'open', 'high', 'low', 'close', 'volume']]
    
    except requests.exceptions.Timeout:
        logger.error(f"Timeout saat mengambil data OKX untuk {pair} dari {url}")
        return pd.DataFrame()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error koneksi saat mengambil data OKX untuk {pair}: {e}")
        return pd.DataFrame()
    except ValueError as e:  # Error parsing JSON
        logger.error(f"Error parsing JSON dari OKX untuk {pair}: {e}")
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"Error tidak terduga di fetch_okx_candles untuk {pair}: {e}")
        return pd.DataFrame()

# === FUNGSI UTAMA UNTUK MENJALANKAN BOT ===
def main():
    """Fungsi utama untuk menginisialisasi dan menjalankan bot."""
    if not TELEGRAM_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN tidak ditemukan! Bot tidak dapat dimulai.")
        return

    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    
    polling_thread = threading.Thread(target=updater.start_polling, name="TelegramPollingThread")
    polling_thread.daemon = True 
    polling_thread.start()
    logger.info("✅ Bot Telegram polling telah dimulai di thread terpisah.")

    if TELEGRAM_CHAT_ID is not None:
        bot_instance = Bot(token=TELEGRAM_TOKEN)
        try:
            loop_runner(bot_instance, 60) 
        except KeyboardInterrupt:
            logger.info("Loop runner dihentikan oleh pengguna.")
        except Exception as e:
            logger.critical(f"Loop runner berhenti karena error: {e}", exc_info=True)
            
    else:
        logger.warning("Loop runner otomatis tidak dimulai karena TELEGRAM_CHAT_ID tidak valid.")
        logger.info("Bot hanya akan merespons perintah. Tidak ada update otomatis.")
        try:
            updater.idle() 
        except KeyboardInterrupt:
            logger.info("Bot dihentikan oleh pengguna (dari idle).")
        except Exception as e:
            logger.critical(f"Bot berhenti karena error saat idle: {e}")

    if updater.running:
        logger.info("Menghentikan polling bot...")
        updater.stop()
    logger.info("Bot telah berhenti.")


if __name__ == '__main__':
    main()
"""

Path("/content/RCSATELITENEW/main.py").write_text(dedent(code)) kode bot kamu dari canvas akan disalin ke sini
