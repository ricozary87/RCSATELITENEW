# main_refactored.py

import threading
import time
import signal # Untuk penanganan Ctrl+C yang lebih baik
import logging # Diimpor lagi untuk setup logger di level ini jika perlu

# Impor konfigurasi dan logger utama
from bot_config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, logger # Ambil logger dari bot_config
# Impor handler
from bot_handlers import start as start_handler, sinyal as sinyal_handler, loop_runner as loop_runner_func
# Impor Telegram specific
from telegram.ext import Updater, CommandHandler
from telegram import Bot


def main():
    if not TELEGRAM_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN tidak ditemukan di file .env. Bot tidak dapat dimulai.")
        return
    
    # Cek apakah OpenAI API Key ada, karena beberapa fungsi mungkin membutuhkannya
    from bot_config import OPENAI_API_KEY # Impor di sini untuk cek
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY tidak ada. Analisis AI tidak akan berfungsi.")

    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start_handler))
    dp.add_handler(CommandHandler("sinyal", sinyal_handler, pass_args=True))

    polling_thread = threading.Thread(target=updater.start_polling, daemon=True)
    polling_thread.start()
    logger.info("Bot aktif dan polling pembaruan dari Telegram...")

    main_loop_active = True # Variabel untuk mengontrol loop utama dan thread

    # Fungsi untuk menangani sinyal interupsi (Ctrl+C)
    def signal_interrupt_handler(signum, frame):
        nonlocal main_loop_active
        logger.info("Sinyal interupsi diterima (misal, Ctrl+C). Menghentikan bot...")
        main_loop_active = False # Set flag untuk menghentikan loop_runner_thread secara tidak langsung
        updater.stop() # Menghentikan polling Telegram
        logger.info("Updater Telegram telah dihentikan.")
        # Thread daemon (polling_thread, loop_runner_thread) akan berhenti saat program utama keluar

    signal.signal(signal.SIGINT, signal_interrupt_handler)
    signal.signal(signal.SIGTERM, signal_interrupt_handler)

    loop_runner_thread = None
    if TELEGRAM_CHAT_ID and isinstance(TELEGRAM_CHAT_ID, int) :
        logger.info(f"Loop runner akan mengirim pesan ke TELEGRAM_CHAT_ID: {TELEGRAM_CHAT_ID}")
        bot_for_loop = Bot(token=TELEGRAM_TOKEN)
        
        loop_runner_thread = threading.Thread(target=loop_runner_func, args=(bot_for_loop, 30), daemon=True)
        loop_runner_thread.start()
        logger.info("Loop runner dimulai dalam thread terpisah.")
        
        # Jaga main thread tetap hidup selama thread lain berjalan atau sampai sinyal interupsi
        while main_loop_active:
            if not polling_thread.is_alive():
                logger.error("Thread polling Telegram mati secara tidak terduga!")
                main_loop_active = False
                break
            if loop_runner_thread and not loop_runner_thread.is_alive():
                # Ini bisa normal jika loop_runner selesai karena suatu kondisi,
                # atau error. Cek log loop_runner untuk detail.
                logger.warning("Thread loop_runner mati.")
                # Anda bisa memutuskan apakah ini kondisi kritis atau tidak.
                # Untuk sekarang, kita biarkan main loop berjalan selama polling aktif.
                # Atau, jika loop_runner penting, set main_loop_active = False
                pass # Biarkan main_loop_active dikontrol oleh signal_interrupt_handler atau error polling
            try:
                time.sleep(1) 
            except InterruptedError: # Bisa terjadi jika ada interupsi saat sleep
                 logger.info("Main thread sleep terinterupsi.")
                 main_loop_active = False # Keluar dari loop
                 break


    else: # Jika tidak ada TELEGRAM_CHAT_ID untuk loop_runner
        logger.info("TELEGRAM_CHAT_ID tidak dikonfigurasi atau tidak valid. Loop runner otomatis tidak akan berjalan.")
        logger.info("Bot hanya akan merespons perintah. Gunakan Ctrl+C untuk menghentikan.")
        # updater.idle() akan memblokir di sini sampai updater dihentikan.
        # Jika kita menggunakan signal_handler, updater.idle() mungkin tidak diperlukan
        # karena loop while main_loop_active di atas sudah menjaga program tetap hidup.
        # Namun, updater.idle() adalah cara standar jika tidak ada loop_runner.
        # Mari kita gunakan cara yang lebih eksplisit dengan loop `while main_loop_active` seperti di atas
        # atau jika ingin lebih sederhana untuk kasus ini:
        try:
            updater.idle()
        except KeyboardInterrupt: # Ditangani oleh signal_handler, tapi ini fallback
            logger.info("updater.idle() diinterupsi. Menghentikan bot...")
            # signal_interrupt_handler seharusnya sudah dipanggil.
            main_loop_active = False # Pastikan loop utama tahu untuk berhenti jika ada di atas
        
    if not updater.running: # Jika updater dihentikan oleh signal_handler
        logger.info("Menunggu thread untuk bergabung (jika perlu)...")
        # polling_thread.join(timeout=5) # Jika tidak daemon
        # if loop_runner_thread and loop_runner_thread.is_alive():
        #     loop_runner_thread.join(timeout=5) # Jika tidak daemon

    logger.info("Program bot RC SATELLITE GPT telah berakhir.")

if __name__ == "__main__":
    main()
