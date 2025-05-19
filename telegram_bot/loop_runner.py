import time
from telegram import Bot, ParseMode
from bot_config import TELEGRAM_CHAT_ID, PAIRS, SUPPORTED_TF_MAP, logger
from market.market_data import fetch_okx_candles, analyze_indicators, check_extreme_alert
from analysis.ai_content import build_ai_analysis_prompt, get_ai_analysis
from analysis.sol_alert_rules import generate_sol_alerts
from utils.utils import escape_markdown_v2

def loop_runner(bot: Bot, interval_minutes: int = 30):
    logger.info(f"Memulai loop_runner dengan interval {interval_minutes} menit.")
    while TELEGRAM_CHAT_ID and isinstance(TELEGRAM_CHAT_ID, int):
        logger.info("Memulai siklus loop_runner untuk semua PAIRS...")

        for pair in PAIRS:
            try:
                logger.info(f"Memproses: {pair}")
                tf_main = SUPPORTED_TF_MAP.get("1h", "1H")
                df_main = fetch_okx_candles(pair, tf_main, 220)

                msg_parts = []

                if pair == "SOL-USDT":
                    sol_dfs = {}
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
                    if valid_dfs:
                        sol_alerts = generate_sol_alerts(valid_dfs, pair)
                        if sol_alerts:
                            msg_parts.append(f"🚨 *Sinyal Otomatis untuk {escape_markdown_v2(pair)}*:\n{sol_alerts}")

                if not df_main.empty:
                    if "rsi" not in df_main.columns:
                        df_main = analyze_indicators(df_main)

                    alert = check_extreme_alert(df_main, pair)
                    if alert:
                        msg_parts.append(alert)

                    prompt = build_ai_analysis_prompt(df_main, pair, "1H")
                    ai_result = get_ai_analysis(prompt)
                    escaped_ai = escape_markdown_v2(ai_result)

                    msg_parts.append(f"📡 *Analisis AI: {escape_markdown_v2(pair)} (1H)*\n{escaped_ai}")
                else:
                    logger.warning(f"Data kosong untuk {pair} (1H).")

                final_msg = "\n\n---\n\n".join(filter(None, msg_parts))

                if final_msg:
                    if len(final_msg) > 4096:
                        for i in range(0, len(final_msg), 4096):
                            try:
                                chunk = final_msg[i:i+4096]
                                bot.send_message(
                                    chat_id=TELEGRAM_CHAT_ID,
                                    text=escape_markdown_v2(chunk),
                                    parse_mode=ParseMode.MARKDOWN_V2
                                )
                            except Exception as e:
                                logger.warning(f"Gagal kirim chunk pesan untuk {pair}: {e}")
                                break
                    else:
                        try:
                            bot.send_message(
                                chat_id=TELEGRAM_CHAT_ID,
                                text=escape_markdown_v2(final_msg),
                                parse_mode=ParseMode.MARKDOWN_V2
                            )
                        except Exception as e:
                            logger.warning(f"Gagal kirim pesan untuk {pair}: {e}")

                    logger.info(f"Pesan loop_runner untuk {pair} dikirim.")
                else:
                    logger.info(f"Tidak ada pesan yang dikirim untuk {pair}.")

            except Exception as e:
                logger.error(f"Error saat proses {pair} di loop_runner: {e}", exc_info=True)

            time.sleep(5)

        logger.info(f"Siklus loop_runner selesai. Tidur {interval_minutes} menit...")
        time.sleep(interval_minutes * 60)
