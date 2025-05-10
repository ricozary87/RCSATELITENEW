# bot_handlers.py

import time
import pandas as pd # Diperlukan untuk pd.DataFrame() kosong
import logging
from telegram import Bot, ParseMode
from telegram.ext import CommandHandler 

# Impor dari modul lain yang sudah kita buat
from bot_config import PAIRS, SUPPORTED_TF_MAP, TELEGRAM_CHAT_ID, TELEGRAM_TOKEN, logger
from utils import escape_markdown_v2
from market_data import fetch_okx_candles, analyze_indicators, check_extreme_alert
from ai_content import build_ai_analysis_prompt, get_ai_analysis
from sol_alert_rules import generate_sol_alerts


def start(update, context):
    user = update.effective_user
    update.message.reply_html(f"Halo {user.mention_html()}!\nGunakan /sinyal NAMA_KOIN [tf1] [tf2]...")

def sinyal(update, context):
    # (Salin implementasi fungsi sinyal yang sudah diperbaiki dan mendukung MTF ke sini)
    args = context.args
    if not args:
        update.message.reply_text(
            "Format perintah: `/sinyal NAMA_KOIN [tf1] [tf2] ...`\n"
            "Contoh: `/sinyal SOL 5m 1h`\n"
            "Timeframe yang didukung: 1m, 5m, 15m, 30m, 1h, 4h, 1d, dll.\n"
            "Jika timeframe tidak diberikan, default ke 1H untuk analisis AI.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    coin_name_arg = args[0].upper()
    requested_timeframes_input = args[1:] if len(args) > 1 else ["1h"] 

    target_pair = None
    for p_name in PAIRS:
        if p_name.startswith(coin_name_arg.split('-')[0]):
            target_pair = p_name
            break
    
    if not target_pair:
        update.message.reply_text(f"Nama koin '{escape_markdown_v2(coin_name_arg)}' tidak ditemukan atau tidak didukung. Contoh: SOL, BTC.")
        return

    timeframes_to_process_okx = []
    user_friendly_tfs_display = []

    for tf_input in requested_timeframes_input:
        tf_lower = tf_input.lower()
        if tf_lower in SUPPORTED_TF_MAP:
            okx_format_tf = SUPPORTED_TF_MAP[tf_lower]
            if okx_format_tf not in timeframes_to_process_okx:
                 timeframes_to_process_okx.append(okx_format_tf)
                 user_friendly_tfs_display.append(tf_input)
        else:
            update.message.reply_text(f"Timeframe '{escape_markdown_v2(tf_input)}' tidak dikenal/didukung. Coba 1m, 5m, 1h, 4h, 1d.")
            return
            
    if not timeframes_to_process_okx:
        if len(args) == 1: 
            timeframes_to_process_okx = [SUPPORTED_TF_MAP.get("1h", "1H")]
            user_friendly_tfs_display = ["1h (Default)"]
        else:
            update.message.reply_text("Tidak ada timeframe valid yang diproses.")
            return

    processing_message = None
    try:
        processing_message = update.message.reply_text(
            f"⏳ Menganalisis {escape_markdown_v2(target_pair)} untuk timeframe: {escape_markdown_v2(', '.join(user_friendly_tfs_display))}...",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except Exception as e_proc_msg:
        logger.error(f"Gagal mengirim pesan 'Menganalisis...': {e_proc_msg}")

    combined_results_parts = []
    data_frames_collection = {} 

    for i, tf_okx in enumerate(timeframes_to_process_okx):
        user_tf_str_display = user_friendly_tfs_display[i]
        logger.info(f"Mengambil data untuk {target_pair} - TF {tf_okx} (display {user_tf_str_display})")
        df = fetch_okx_candles(target_pair, tf_okx, 220) 
        if not df.empty:
            df = analyze_indicators(df)
            data_frames_collection[tf_okx] = df
        else:
            logger.warning(f"Data kosong untuk {target_pair} - TF {tf_okx}")
            data_frames_collection[tf_okx] = pd.DataFrame() 

    if target_pair == "SOL-USDT":
        valid_dfs_for_sol = {tf: df for tf, df in data_frames_collection.items() if df is not None and not df.empty}
        if valid_dfs_for_sol:
            sol_auto_alerts_text = generate_sol_alerts(valid_dfs_for_sol, target_pair)
            if sol_auto_alerts_text:
                combined_results_parts.append(f"🚨 *Sinyal Otomatis untuk {escape_markdown_v2(target_pair)}*:\n{sol_auto_alerts_text}")
        # Cek apakah SEMUA df untuk SOL kosong sebelum memberi info "tidak cukup data"
        elif not any(df is not None and not df.empty for df in data_frames_collection.values()):
             combined_results_parts.append(f"ℹ️ _Tidak ada data yang cukup untuk menghasilkan sinyal otomatis {escape_markdown_v2(target_pair)}._")

    for i, tf_okx in enumerate(timeframes_to_process_okx):
        user_tf_str_display = user_friendly_tfs_display[i]
        df = data_frames_collection.get(tf_okx)

        if df is None or df.empty:
            # Hanya tambahkan pesan ini jika belum ada pesan error spesifik untuk TF ini
            # Ini untuk menghindari duplikasi jika SOL-USDT dan generate_sol_alerts juga tidak menemukan data
            # Tapi lebih aman untuk selalu memberi tahu per TF jika datanya tidak ada untuk AI
            existing_error_msg_for_tf = f"_{escape_markdown_v2(target_pair)} ({escape_markdown_v2(user_tf_str_display)}): Data tidak tersedia"
            if not any(existing_error_msg_for_tf in part for part in combined_results_parts):
                 combined_results_parts.append(f"⚠️ {existing_error_msg_for_tf} atau gagal diproses._")
            continue
        
        logger.info(f"Membuat prompt AI untuk {target_pair} - TF {user_tf_str_display}")
        alert_tf_specific = check_extreme_alert(df, target_pair) 
        prompt_tf = build_ai_analysis_prompt(df, target_pair, user_tf_str_display)
        ai_analysis_tf_raw = get_ai_analysis(prompt_tf)
        escaped_ai_analysis_tf = escape_markdown_v2(ai_analysis_tf_raw)

        escaped_pair_tf_header = escape_markdown_v2(target_pair)
        header_tf_content = f"📡 *Analisis AI: {escaped_pair_tf_header} ({escape_markdown_v2(user_tf_str_display)})*"
        
        current_tf_analysis_text = ""
        if alert_tf_specific:
            current_tf_analysis_text += alert_tf_specific + "\n\n"
        current_tf_analysis_text += header_tf_content + "\n"
        current_tf_analysis_text += escaped_ai_analysis_tf
        
        combined_results_parts.append(current_tf_analysis_text)

    if processing_message:
        try:
            context.bot.delete_message(chat_id=update.effective_chat.id, message_id=processing_message.message_id)
        except Exception as e_del_msg:
            logger.warning(f"Gagal menghapus pesan 'Menganalisis...': {e_del_msg}")

    if combined_results_parts:
        final_message_output = "\n\n---\n\n".join(filter(None, combined_results_parts))
        
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
                    logger.error(f"GAGAL KIRIM chunk pesan MTF untuk {target_pair}: {e_chunk}. Gagal pada chunk: {chunk[:50]}...")
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


def loop_runner(bot: Bot, interval_minutes: int = 30):
    # (Salin implementasi loop_runner yang sudah diperbaiki dan diadaptasi untuk SOL ke sini)
    logger.info(f"Memulai loop_runner dengan interval {interval_minutes} menit.")
    while TELEGRAM_CHAT_ID and isinstance(TELEGRAM_CHAT_ID, int):
        logger.info(f"Memulai siklus loop_runner untuk semua PAIRS...")
        for current_pair_loop in PAIRS:
            try:
                logger.info(f"Loop runner: Memproses {current_pair_loop}...")
                default_tf_okx_loop = SUPPORTED_TF_MAP.get("1h", "1H")
                user_tf_display_loop = "1H" 

                df_loop_main_tf = fetch_okx_candles(current_pair_loop, default_tf_okx_loop, 220)
                
                msg_parts_loop = [] 

                if current_pair_loop == "SOL-USDT":
                    sol_dfs_for_alert_loop = {}
                    # Salin df_loop_main_tf jika tidak kosong dan sudah dianalisis indikatornya
                    if not df_loop_main_tf.empty:
                        # Analisis indikator di sini jika belum
                        if 'rsi' not in df_loop_main_tf.columns:
                             df_loop_main_tf = analyze_indicators(df_loop_main_tf.copy())
                        sol_dfs_for_alert_loop[default_tf_okx_loop] = df_loop_main_tf
                    
                    tf_5m_okx = SUPPORTED_TF_MAP.get("5m", "5m")
                    # Cek apakah df_sol_5m_loop perlu diambil atau sudah ada (jika Anda memodifikasi lebih lanjut)
                    df_sol_5m_loop = fetch_okx_candles(current_pair_loop, tf_5m_okx, 220)
                    if not df_sol_5m_loop.empty:
                        sol_dfs_for_alert_loop[tf_5m_okx] = analyze_indicators(df_sol_5m_loop)
                    
                    # Tambahkan fetch TF lain jika aturan Anda di generate_sol_alerts membutuhkannya
                    tf_15m_okx = SUPPORTED_TF_MAP.get("15m","15m") # Contoh untuk 15m
                    df_sol_15m_loop = fetch_okx_candles(current_pair_loop, tf_15m_okx, 220)
                    if not df_sol_15m_loop.empty:
                        sol_dfs_for_alert_loop[tf_15m_okx] = analyze_indicators(df_sol_15m_loop)


                    valid_sol_dfs_for_alert = {tf: df for tf, df in sol_dfs_for_alert_loop.items() if df is not None and not df.empty}
                    if valid_sol_dfs_for_alert:
                        sol_alerts_loop_text = generate_sol_alerts(valid_sol_dfs_for_alert, current_pair_loop)
                        if sol_alerts_loop_text:
                            msg_parts_loop.append(f"🚨 *Sinyal Otomatis untuk {escape_markdown_v2(current_pair_loop)}*:\n{sol_alerts_loop_text}")
                
                if df_loop_main_tf.empty:
                    logger.warning(f"Loop runner: Data utama (TF {user_tf_display_loop}) kosong untuk {current_pair_loop}.")
                else:
                    if 'rsi' not in df_loop_main_tf.columns:
                         df_loop_main_tf = analyze_indicators(df_loop_main_tf)

                    alert_content_loop = check_extreme_alert(df_loop_main_tf, current_pair_loop)
                    if alert_content_loop:
                         msg_parts_loop.append(alert_content_loop)

                    prompt_loop = build_ai_analysis_prompt(df_loop_main_tf, current_pair_loop, user_tf_display_loop)
                    ai_analysis_raw_loop = get_ai_analysis(prompt_loop)
                    escaped_ai_analysis_loop = escape_markdown_v2(ai_analysis_raw_loop)
                    
                    escaped_pair_header_loop = escape_markdown_v2(current_pair_loop)
                    header_loop = f"📡 *Analisis AI: {escaped_pair_header_loop} ({escape_markdown_v2(user_tf_display_loop)})*"
                    msg_parts_loop.append(f"{header_loop}\n{escaped_ai_analysis_loop}")

                final_msg_loop = "\n\n---\n\n".join(filter(None, msg_parts_loop)) 

                if final_msg_loop:
                    max_msg_len = 4096 
                    if len(final_msg_loop) > max_msg_len:
                        logger.info(f"Loop runner: Pesan untuk {current_pair_loop} terlalu panjang ({len(final_msg_loop)} chars), akan dibagi.")
                        for i in range(0, len(final_msg_loop), max_msg_len):
                            chunk = final_msg_loop[i:i+max_msg_len]
                            try:
                                bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=chunk, parse_mode=ParseMode.MARKDOWN_V2)
                            except Exception as e_chunk_loop:
                                logger.warning(f"Loop runner: GAGAL KIRIM chunk pesan untuk {current_pair_loop}: {e_chunk_loop}.")
                                break 
                    else:
                        try:
                            bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=final_msg_loop, parse_mode=ParseMode.MARKDOWN_V2)
                        except Exception as e_final_loop:
                            logger.warning(f"Loop runner: GAGAL KIRIM pesan untuk {current_pair_loop}: {e_final_loop}.")
                    logger.info(f"Loop runner: Pesan untuk {current_pair_loop} dikirim ke chat ID {TELEGRAM_CHAT_ID}.")
                else:
                    logger.info(f"Loop runner: Tidak ada pesan yang dihasilkan untuk {current_pair_loop}.")

            except Exception as e_pair_loop:
                logger.error(f"Error besar saat memproses {current_pair_loop} di loop_runner: {e_pair_loop}", exc_info=True)
            
            time.sleep(5) 

        logger.info(f"Siklus loop_runner selesai, menunggu {interval_minutes} menit...")
        time.sleep(interval_minutes * 60)
