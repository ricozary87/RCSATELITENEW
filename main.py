from telegram.ext import Updater, CommandHandler
from telegram import Bot, ParseMode
from bot_config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, logger
from telegram_bot.bot_handlers import start, sinyal
from telegram_bot.loop_runner import loop_runner
import threading
import time

def main():
    if not TELEGRAM_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN tidak ditemukan. Cek file .env.")
        return

    try:
        updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
        dp = updater.dispatcher

        # Handler command
        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(CommandHandler("sinyal", sinyal, pass_args=True))

        # Mulai polling bot Telegram
        polling_thread = threading.Thread(target=updater.start_polling, daemon=True)
        polling_thread.start()
        logger.info("Polling Telegram dimulai...")

        # Mulai loop_runner jika TELEGRAM_CHAT_ID valid
        if TELEGRAM_CHAT_ID:
            bot = Bot(token=TELEGRAM_TOKEN)
            loop_thread = threading.Thread(target=loop_runner, args=(bot, 30), daemon=True)
            loop_thread.start()
            logger.info("Loop runner dimulai...")

            while True:
                time.sleep(3600)
        else:
            logger.warning("TELEGRAM_CHAT_ID tidak dikonfigurasi. Hanya polling aktif.")
            updater.idle()

    except Exception as e:
        logger.exception(f"Error di main(): {e}")

if __name__ == "__main__":
    main()
