import time
from telegram import Bot, ParseMode
from bot_config import TELEGRAM_CHAT_ID, SUPPORTED_TF_MAP, logger
from market.market_data import fetch_okx_candles, analyze_indicators, check_extreme_alert
from analysis.ai_content import generate_combined_prompt, get_ai_analysis
from analysis.sol_alert_rules import generate_sol_alerts
from analysis.smc_analyzer import get_smc_signals
from utils.utils import escape_markdown_v2

def loop_runner(bot: Bot, interval_minutes: int = 30):
    logger.info(f"⏳ Memulai loop_runner SOL/USDT setiap {interval_minutes} menit.")
    pair = "SOL-USDT"

    while TELEGRAM_CHAT_ID and isinstance(TELEGRAM_CHAT_ID, int):
        logger.info("🔁 Loop dimulai untuk SOL-USDT...")

        try:
            tf_main = SUPPORTED_TF_MAP.get("1h", "1H")
            df_main = fetch_okx_candles(pair, tf_main, 220)
            msg_parts = []

            sol_dfs = {}

            # Ambil dan proses data semua TF
            if not df_main.empty:
                if "rsi" not in df_main.columns:
                    df_main = analyze_indicators(df_main)
                sol_dfs[tf_main] = df_main

            tf_5m = SUPPORTED_TF_MAP.get("5m", "5m")
            df_5m = fetch_okx_candles(pair, tf_5m, 220)
            if not df_5m.empty:
                sol_dfs[tf_5m] = analyze_indicators(df_5m)

            tf_15m = SUPPORTED_TF_MAP.get("15m", "15m")
            df_15m = fetch_okx_candles(pair, tf_15m, 220)
            if not df_15m.empty:
                sol_dfs[tf_15m] = analyze_indicators(df_15m)

            valid_dfs = {tf: df for tf, df in sol_dfs.items() if not df.empty}

            # === Header harga terkini ===
            harga_terkini = df_main.iloc[-1]["close"]
            harga_str = f"{harga_terkini:.2f}"
            msg_parts.append(f"📍 *{escape_markdown_v2(pair)}*\n🕒 Harga Terkini: ${escape_markdown_v2(harga_str)}")

            # === Sinyal rules manual ===
            if valid_dfs:
                sol_alerts = generate_sol_alerts(valid_dfs, pair)
                if sol_alerts:
                    msg_parts.append(f"🚨 *Sinyal Otomatis {escape_markdown_v2(pair)}*:\n{sol_alerts}")

            # === Deteksi ekstrem (RSI / MACD abnormal)
            if not df_main.empty:
                alert = check_extreme_alert(df_main, pair)
                if alert:
                    msg_parts.append(alert)

            # === Deteksi SMC ===
            smc_summary = {}
            for tf, df in valid_dfs.items():
                try:
                    smc_df = get_smc_signals(df)
                    last = smc_df.iloc[-1]
                    notes = []
                    if last['bos']: notes.append("BOS")
                    if last['choch']: notes.append("CHoCH")
                    if last['liquidity_sweep']: notes.append("Sweep")
                    if notes:
                        smc_summary[tf] = notes
                except Exception as e:
                    logger.warning(f"Gagal analisis SMC ({tf}): {e}")

            # === Narasi GPT + Entry Plan ===
            prompt = generate_combined_prompt(pair, valid_dfs, smc_summary)
            ai_result = get_ai_analysis(prompt)
            escaped_ai = escape_markdown_v2(ai_result)
            msg_parts.append(f"📡 *Analisis AI:*\n{escaped_ai}")

            # === Kirim Telegram ===
            final_msg = "\n\n---\n\n".join(filter(None, msg_parts))

            if final_msg:
                if len(final_msg) > 4096:
                    for i in range(0, len(final_msg), 4096):
                        try:
                            bot.send_message(
                                chat_id=TELEGRAM_CHAT_ID,
                                text=escape_markdown_v2(final_msg[i:i+4096]),
                                parse_mode=ParseMode.MARKDOWN_V2
                            )
                        except Exception as e:
                            logger.warning(f"Gagal kirim chunk pesan: {e}")
                            break
                else:
                    try:
                        bot.send_message(
                            chat_id=TELEGRAM_CHAT_ID,
                            text=escape_markdown_v2(final_msg),
                            parse_mode=ParseMode.MARKDOWN_V2
                        )
                    except Exception as e:
                        logger.warning(f"Gagal kirim pesan: {e}")

                logger.info("✅ Pesan SOL-USDT dikirim ke Telegram.")
            else:
                logger.info("⚠️ Tidak ada sinyal untuk dikirim.")

        except Exception as e:
            logger.error(f"❌ Error di loop SOL-USDT: {e}", exc_info=True)

        logger.info(f"🛌 Menunggu {interval_minutes} menit...")
        time.sleep(interval_minutes * 60)
