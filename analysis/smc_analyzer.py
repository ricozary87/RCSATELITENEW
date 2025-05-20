import pandas as pd

def detect_bos_choch(df: pd.DataFrame, lookback=20):
    df = df.copy()
    df['bos'] = False
    df['choch'] = False

    for i in range(lookback, len(df)):
        prev_high = max(df['high'][i-lookback:i])
        prev_low = min(df['low'][i-lookback:i])

        # Break of Structure (BOS)
        if df['high'][i] > prev_high or df['low'][i] < prev_low:
            df.at[i, 'bos'] = True

        # Change of Character (CHoCH)
        if df['bos'][i-1] and (
            (df['high'][i] < prev_high) or (df['low'][i] > prev_low)
        ):
            df.at[i, 'choch'] = True

    return df[['timestamp', 'bos', 'choch']]

def identify_liquidity_sweep(df: pd.DataFrame):
    df = df.copy()
    df['liquidity_sweep'] = False

    for i in range(1, len(df) - 1):
        # Sweep low + bullish close
        if df['low'][i] < df['low'][i-1] and df['close'][i] > df['open'][i]:
            df.at[i, 'liquidity_sweep'] = True
        # Sweep high + bearish close
        if df['high'][i] > df['high'][i-1] and df['close'][i] < df['open'][i]:
            df.at[i, 'liquidity_sweep'] = True

    return df[['timestamp', 'liquidity_sweep']]

def get_smc_signals(df: pd.DataFrame):
    df = df.reset_index()

    if 'timestamp' not in df.columns:
        df['timestamp'] = df['index']

    # Pastikan 'timestamp' di format datetime
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    df1 = detect_bos_choch(df)
    df2 = identify_liquidity_sweep(df)

    merged = df.join(df1.set_index('timestamp'), on='timestamp')
    merged = merged.join(df2.set_index('timestamp'), on='timestamp')

    return merged[['timestamp', 'bos', 'choch', 'liquidity_sweep']]
