# test_openai.py
import os
from openai import OpenAI
from dotenv import load_dotenv
import logging
import traceback

# Setup logging sederhana untuk tes ini
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load .env
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# Coba dulu dengan model yang lebih ringan dan cepat untuk tes awal
OPENAI_MODEL_TEST = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo") 
# OPENAI_MODEL_TEST = "gpt-4o" # Anda bisa ganti ke gpt-4o setelah tes dengan gpt-3.5-turbo berhasil

logger.info(f"Tes OpenAI: Menggunakan API Key: {'Ada' if OPENAI_API_KEY else 'TIDAK ADA'}")
logger.info(f"Tes OpenAI: Menggunakan Model: {OPENAI_MODEL_TEST}")

if not OPENAI_API_KEY:
    logger.error("Tes OpenAI: Kunci API OpenAI tidak ditemukan di .env. Keluar.")
    exit()

client = OpenAI(api_key=OPENAI_API_KEY)

def run_openai_test():
    try:
        logger.info("Tes OpenAI: Mencoba mengirim permintaan sederhana...")
        start_time = time.time()
        response = client.chat.completions.create(
            model=OPENAI_MODEL_TEST,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello, what is the capital of France?"}
            ],
            max_tokens=50,
            timeout=60  # Timeout 60 detik untuk tes
        )
        end_time = time.time()
        logger.info(f"Tes OpenAI: Berhasil menerima respons dalam {end_time - start_time:.2f} detik.")
        
        if response.choices and response.choices[0].message and response.choices[0].message.content:
            content = response.choices[0].message.content.strip()
            logger.info(f"Tes OpenAI: Konten Respons: {content}")
        else:
            logger.error("Tes OpenAI: Respons OpenAI tidak memiliki struktur yang diharapkan.")
            logger.info(f"Tes OpenAI: Respons mentah: {response}")

    except Exception as e:
        logger.error(f"Tes OpenAI: Terjadi error saat menghubungi OpenAI: {e}")
        logger.error(traceback.format_exc()) # Cetak traceback lengkap

if __name__ == "__main__":
    import time # Pastikan time diimpor untuk start_time
    run_openai_test()
