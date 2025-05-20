import os
import logging
from dotenv import load_dotenv
from openai import OpenAI

# === Logging Setup ===
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === Load .env ===
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID_STR = os.getenv("TELEGRAM_CHAT_ID")

# === Parse TELEGRAM_CHAT_ID ===
TELEGRAM_CHAT_ID = None
if TELEGRAM_CHAT_ID_STR is None:
    logger.error("TELEGRAM_CHAT_ID tidak ditemukan di file .env.")
else:
    try:
        TELEGRAM_CHAT_ID = int(TELEGRAM_CHAT_ID_STR)
    except ValueError:
        logger.error(f"TELEGRAM_CHAT_ID '{TELEGRAM_CHAT_ID_STR}' tidak valid.")

# === Init OpenAI Client ===
CLIENT_OPENAI = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
if not CLIENT_OPENAI:
    logger.warning("OPENAI_API_KEY tidak ditemukan atau kosong. Fitur AI tidak akan berfungsi.")

# === Konstanta Pasangan Koin & Timeframe ===
PAIRS = ["SOL-USDT"]

SUPPORTED_TF_MAP = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1H", "2h": "2H", "4h": "4H", "6h": "6H", "12h": "12H",
    "1d": "1D", "1w": "1W", "1mon": "1M",
    "3mon": "3M", "6mon": "6M", "1y": "1Y"
}
