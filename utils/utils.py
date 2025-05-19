import re
import pandas as pd
from bot_config import logger

def escape_markdown_v2(text):
    """
    Escape karakter khusus agar tidak error saat dikirim ke Telegram dengan Markdown V2.
    """
    if text is None:
        return ""
    text_to_escape = str(text)
    escape_chars = r"_*[]()~`>#+-=|{}.!\\"
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text_to_escape)

def get_val(series, key, p=2, prefix="$", include_prefix=True):
    """
    Ambil dan format nilai dari series/key untuk ditampilkan dalam pesan.
    """
    val = series.get(key)
    if pd.isna(val):
        return "N/A"
    try:
        float_val = float(val)
        formatted_val = f"{float_val:.{p}f}"
    except ValueError:
        return str(val)
    return f"{prefix}{formatted_val}" if include_prefix else formatted_val
