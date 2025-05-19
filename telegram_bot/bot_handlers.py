from telegram import Update, ParseMode
from telegram.ext import CommandHandler, CallbackContext
from bot_config import PAIRS, SUPPORTED_TF_MAP, logger
from utils.utils import escape_markdown_v2
from market.market_data import fetch_okx_candles, analyze_indicators, check_extreme_alert
from analysis.ai_content import build_ai_analysis_prompt, get_ai_analysis
from analysis.sol_alert_rules import generate_sol_alerts
import pandas as pd

def start(update: Update, context: CallbackContext):
    user = update.effective_user
    update.message.reply_html(
        f"Halo {user.mention_html()}!\nGunakan perintah /sinyal NAMA_KOIN [tf1] [tf2]...\n"
        f"Contoh: /sinyal SOL 5m 1h"
    )

def sinyal(update: Update, context: CallbackContext):
    args = context.args
    if not args:
        update.message.reply_text(
            "Format perintah:\n`/sinyal NAMA_KOIN [tf1] [tf2] ...`\nContoh: `/sinyal SOL 5m 1h`\n"
            "Jika tidak diberi timeframe, default ke 1H.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    coin = args[0].upper()
    tfs_input = args[1:] if len(args) > 1 else ["1h"]

    pair = next((p for p in PAIRS if p.startswith(coin.split("-")[0])), None)
    if not pair:
        update.message.reply_text(f"Nama koin '{escape_markdown_v2(coin)}' tidak dikenali.", parse_mode=ParseMode.MARKDOWN_V2)
        return

    okx_tfs, tf_labels = [], []
    for tf in tfs_input:
        tf_lower = tf.lower()
        if tf_lower in SUPPORTED_TF_MAP:
            okx_format = SUPPORTED_TF_MAP[tf_lower]
            if okx_format not in okx_tfs:
                okx_tfs.append(okx_format)
                tf_labels.append(tf)
        else:
            update.message.reply_text(f"Timeframe '{escape_markdown_v2(tf)}' tidak didukung.", parse_mode=ParseMode.MARKDOWN_V2)
            return

    if not okx_tfs:
        okx_tfs = [SUPPORTED_TF_MAP.get("1h", "1H")]
        tf_labels = ["1h (Default)"]

    msg_loading = update.message.reply_text(
        f"⏳ Menganalisis {escape_markdown_v2(pair)} untuk TF: {escape_markdown_v2(', '.join(tf_labels))}...",
        parse_mode=ParseMode.MARKDOWN_V2
    )

    results = []
    df_by_tf = {}

    for i, tf in enumerate(okx_tfs):
        label = tf_labels[i]
        logger.info(f"Ambil data {pair} - TF {tf} ({label})")
        df = fetch_okx_candles(pair, tf, 220)
        if not df.empty:
            df = analyze_indicators(df)
            df_by_tf[tf] = df
        else:
            df_by_tf[tf] = pd.DataFrame()

    if pair == "SOL-USDT":
        valid_df = {tf: df for tf, df in df_by_tf.items() if not df.empty}
        if valid_df:
            sol_alerts = generate_sol_alerts(valid_df, pair)
            if sol_alerts:
                results.append(f"🚨 *Sinyal Otomatis untuk {escape_markdown_v2(pair)}*:\n{sol_alerts}")

    for i, tf in enumerate(okx_tfs):
        label = tf_labels[i]
        df = df_by_tf.get(tf)
        if df is None or df.empty:
            results.append(f"⚠️ _{escape_markdown_v2(pair)} ({escape_markdown_v2(label)}): Data tidak tersedia._")
            continue

        logger.info(f"Analisa AI {pair} - TF {label}")
        alert = check_extreme_alert(df, pair)
        prompt = build_ai_analysis_prompt(df, pair, label)
        ai_result = get_ai_analysis(prompt)
        escaped_ai_result = escape_markdown_v2(ai_result)
        results.append(f"{alert}\n📡 *Analisis AI: {escape_markdown_v2(pair)} ({escape_markdown_v2(label)})*\n{escaped_ai_result}")

    if msg_loading:
        try:
            context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_loading.message_id)
        except Exception as e:
            logger.warning(f"Gagal hapus pesan loading: {e}")

    final_msg = "\n\n---\n\n".join(results)
    if len(final_msg) > 4096:
        for i in range(0, len(final_msg), 4096):
            chunk = final_msg[i:i+4096]
            try:
                update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN_V2)
            except Exception as e:
                logger.error(f"Gagal kirim chunk: {e}")
    else:
        update.message.reply_text(escape_markdown_v2("Format perintah: ..."), parse_mode=ParseMode.MARKDOWN_V2)

