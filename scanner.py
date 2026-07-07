import logging
import pandas as pd
import numpy as np
import yfinance as yf
import requests
from datetime import datetime
from config import load_config

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("scanner")

# In-memory store for active signals and scan logs
scan_history = []
active_signals = {}  # Format: {symbol: {signal_type: 'LONG'/'SHORT', price: float, time: str, details: str, grade: str}}

# -------------------------------------------------------------------
# Teknik İndikatör Hesaplamaları
# -------------------------------------------------------------------

def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """RSI (Relative Strength Index) hesaplar. Sıfır bölme koruması dahil."""
    close = df['Close']
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(100.0)


def calculate_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD (Moving Average Convergence Divergence) hesaplar."""
    ema_fast = df['Close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['Close'].ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    hist = macd - signal_line
    return macd, signal_line, hist


def calculate_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0):
    """SuperTrend indikatörünü hesaplar. NaN koruması dahil."""
    high = df['High']
    low = df['Low']
    close = df['Close']

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()

    hl2 = (high + low) / 2
    upperband = hl2 + (multiplier * atr)
    lowerband = hl2 - (multiplier * atr)

    final_upperband = upperband.copy()
    final_lowerband = lowerband.copy()

    for i in range(1, len(df)):
        if pd.isna(atr.iloc[i]):
            continue
        if upperband.iloc[i] < final_upperband.iloc[i-1] or close.iloc[i-1] > final_upperband.iloc[i-1]:
            final_upperband.iloc[i] = upperband.iloc[i]
        else:
            final_upperband.iloc[i] = final_upperband.iloc[i-1]

        if lowerband.iloc[i] > final_lowerband.iloc[i-1] or close.iloc[i-1] < final_lowerband.iloc[i-1]:
            final_lowerband.iloc[i] = lowerband.iloc[i]
        else:
            final_lowerband.iloc[i] = final_lowerband.iloc[i-1]

    supertrend = pd.Series(True, index=df.index)
    for i in range(1, len(df)):
        if pd.isna(final_upperband.iloc[i-1]) or pd.isna(final_lowerband.iloc[i-1]):
            supertrend.iloc[i] = supertrend.iloc[i-1]
            continue

        if close.iloc[i] > final_upperband.iloc[i-1]:
            supertrend.iloc[i] = True
        elif close.iloc[i] < final_lowerband.iloc[i-1]:
            supertrend.iloc[i] = False
        else:
            supertrend.iloc[i] = supertrend.iloc[i-1]
            if supertrend.iloc[i] and final_lowerband.iloc[i] < final_lowerband.iloc[i-1]:
                final_lowerband.iloc[i] = final_lowerband.iloc[i-1]
            if not supertrend.iloc[i] and final_upperband.iloc[i] > final_upperband.iloc[i-1]:
                final_upperband.iloc[i] = final_upperband.iloc[i-1]

    return supertrend, final_upperband, final_lowerband


def calculate_obv(df: pd.DataFrame) -> pd.Series:
    """OBV (On Balance Volume) hesaplar."""
    close_diff = df['Close'].diff().fillna(0)
    direction = np.sign(close_diff)
    obv = (direction * df['Volume']).cumsum()
    return obv


def calculate_bollinger_bands(df: pd.DataFrame, period: int = 20, num_std: float = 2.0):
    """Bollinger Bantları ve Bant Genişliğini (Bandwidth) hesaplar."""
    sma = df['Close'].rolling(period).mean()
    std = df['Close'].rolling(period).std()
    upper_band = sma + (num_std * std)
    lower_band = sma - (num_std * std)
    bandwidth = (upper_band - lower_band) / sma
    return upper_band, lower_band, bandwidth.fillna(0)


# -------------------------------------------------------------------
# Veri Çekme Fonksiyonları (Retry Mekanizmalı)
# -------------------------------------------------------------------

def _retry(func, max_retries: int = 3, delay: float = 2.0):
    """Genel retry wrapper."""
    import time as _time
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(f"Deneme {attempt}/{max_retries} basarisiz: {e}. {delay}s sonra tekrar denenecek...")
                _time.sleep(delay)
    raise last_error


def fetch_crypto_data(symbol: str, timeframe: str = "1h") -> pd.DataFrame:
    """
    yfinance üzerinden Kripto fiyat verisi çeker.
    Bu yöntem, US IP bloklarını (Binance 451 hatasını) tamamen aşar.
    Örnek symbol: BTC/USDT -> BTC-USD
    """
    symbol_usd = symbol.replace("/", "-").replace("USDT", "USD")
    needs_resample_4h = (timeframe == "4h")
    
    interval_map = {
        "15m": "15m",
        "1h": "1h",
        "4h": "1h",
        "1d": "1d"
    }
    interval = interval_map.get(timeframe, "1h")

    # yfinance period limitleri (1h için 60 gün güvenlidir)
    period_map = {
        "15m": "60d",
        "1h": "60d",
        "1d": "2y"
    }
    period = period_map.get(interval, "60d")

    def _fetch():
        ticker = yf.Ticker(symbol_usd)
        df = ticker.history(period=period, interval=interval)
        if df.empty:
            raise Exception(f"yfinance (Kripto): {symbol_usd} icin veri alinamadi.")
        return df

    df = _retry(_fetch)

    if needs_resample_4h and not df.empty:
        df = df.resample('4h').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }).dropna()

    return df


def fetch_bist_data(symbol: str, timeframe: str = "1h") -> pd.DataFrame:
    """yfinance üzerinden BIST/ABD hisse verisi çeker."""
    needs_resample_4h = (timeframe == "4h")
    interval_map = {
        "15m": "15m",
        "1h": "1h",
        "4h": "1h",
        "1d": "1d"
    }
    interval = interval_map.get(timeframe, "1h")

    # yfinance period limitleri (1h için 60 gün güvenlidir)
    period_map = {
        "15m": "60d",
        "1h": "60d",
        "1d": "2y"
    }
    period = period_map.get(interval, "60d")

    def _fetch():
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)
        if df.empty:
            raise Exception(f"yfinance: {symbol} icin veri alinamadi.")
        return df

    df = _retry(_fetch)

    if needs_resample_4h and not df.empty:
        df = df.resample('4h').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }).dropna()

    return df


# -------------------------------------------------------------------
# Analiz Motoru (Ultra Zeki Confluence ve MTF Algoritması)
# -------------------------------------------------------------------

def analyze_market_data(df: pd.DataFrame, config_inds: dict, htf_trend: str = None, total_capital: float = 1000.0) -> tuple:
    """
    Tarihsel veriyi analiz eder, sinyal ('LONG', 'SHORT' veya None), detay metni ve sinyal derecesini döndürür.
    
    Ultra Zeki Algoritmalar:
    - Çoklu Zaman Dilimi (MTF) Trend Filtresi
    - Hacim Patlaması & OBV Gücü
    - Bollinger Bant Sıkışması (Squeeze) ve Patlaması (Breakout)
    - Puanlama Matrisi (0-100) -> A++, A, B derecelendirme
    """
    if len(df) < 30:
        return None, "Yetersiz veri (en az 30 mum gerekli).", None

    df = df.copy()

    rsi_p = config_inds.get("rsi_period", 14)
    rsi_os = config_inds.get("rsi_oversold", 30)
    rsi_ob = config_inds.get("rsi_overbought", 70)

    macd_f = config_inds.get("macd_fast", 12)
    macd_s = config_inds.get("macd_slow", 26)
    macd_sig = config_inds.get("macd_signal", 9)

    st_p = config_inds.get("supertrend_period", 10)
    st_m = config_inds.get("supertrend_multiplier", 3.0)

    # Temel göstergeler
    df['RSI'] = calculate_rsi(df, rsi_p)
    macd, signal, hist = calculate_macd(df, macd_f, macd_s, macd_sig)
    df['MACD'] = macd
    df['MACD_Signal'] = signal
    df['MACD_Hist'] = hist
    df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
    df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
    
    supertrend, _, _ = calculate_supertrend(df, st_p, st_m)
    df['SuperTrend'] = supertrend

    # Gelişmiş göstergeler (Ultra Zeki)
    df['OBV'] = calculate_obv(df)
    df['OBV_EMA'] = df['OBV'].ewm(span=20, adjust=False).mean()
    upper_bb, lower_bb, bandwidth = calculate_bollinger_bands(df)
    df['BB_Upper'] = upper_bb
    df['BB_Lower'] = lower_bb
    df['BB_Bandwidth'] = bandwidth
    df['BB_Bandwidth_SMA'] = bandwidth.rolling(30).mean()

    # Hacim ortalaması
    df['Volume_SMA'] = df['Volume'].rolling(20).mean()

    # Son veriler
    last_row = df.iloc[-1]
    prev_row = df.iloc[-2]

    close = float(last_row['Close'])
    rsi = float(last_row['RSI'])
    macd_val = float(last_row['MACD'])
    macd_sig_val = float(last_row['MACD_Signal'])
    macd_hist = float(last_row['MACD_Hist'])
    volume = float(last_row['Volume'])
    vol_sma = float(last_row['Volume_SMA'])
    obv = float(last_row['OBV'])
    obv_ema = float(last_row['OBV_EMA'])
    bw = float(last_row['BB_Bandwidth'])
    bw_sma = float(last_row['BB_Bandwidth_SMA'])
    st_val = bool(last_row['SuperTrend'])
    ema_50 = float(last_row['EMA_50'])
    ema_200 = float(last_row['EMA_200'])

    prev_rsi = float(prev_row['RSI'])
    prev_macd_val = float(prev_row['MACD'])
    prev_macd_sig_val = float(prev_row['MACD_Signal'])
    prev_st_val = bool(prev_row['SuperTrend'])
    prev_close = float(prev_row['Close'])

    # ---------------------------------------------------------------
    # Gelişmiş Filtre Koşulları
    # ---------------------------------------------------------------
    
    # Bollinger Squeeze ve Breakout durumları
    # Squeeze: Bandwidth son 30 periyodun ortalamasının altındaysa volatilite sıkışmıştır
    is_squeezed = bw < bw_sma * 0.90
    
    # Breakout: Fiyat bant dışına taşmış ve bandwidth genişlemeye başlamış
    bb_breakout_up = (close > last_row['BB_Upper']) and (bw > prev_row['BB_Bandwidth'])
    bb_breakout_down = (close < last_row['BB_Lower']) and (bw > prev_row['BB_Bandwidth'])

    # Hacim patlaması (Kırılımlarda aranır)
    is_volume_spike = volume > vol_sma * 1.5

    # MACD hacimsel güç eşiği
    macd_min_strength = close * 0.0008  # Fiyatın %0.08'i (küçük dalgaları elemek için dinamik eşik)
    macd_is_strong = abs(macd_hist) > macd_min_strength

    # ---------------------------------------------------------------
    # Puanlama & Gerekçelendirme Matrisi
    # ---------------------------------------------------------------
    long_score = 0
    long_reasons = []
    short_score = 0
    short_reasons = []

    # Tetikleyiciler
    st_buy_trigger = (st_val is True and prev_st_val is False)
    st_sell_trigger = (st_val is False and prev_st_val is True)
    macd_up_cross = (macd_val > macd_sig_val and prev_macd_val <= prev_macd_sig_val and macd_is_strong)
    macd_down_cross = (macd_val < macd_sig_val and prev_macd_val >= prev_macd_sig_val and macd_is_strong)
    rsi_buy_trigger = (rsi > rsi_os and prev_rsi <= rsi_os)
    rsi_sell_trigger = (rsi < rsi_ob and prev_rsi >= rsi_ob)

    # 1. MTF (Çoklu Zaman Dilimi) Onayı (+20 Puan / -30 Puan Cezası)
    if htf_trend == "BULLISH":
        long_score += 20
        long_reasons.append("MTF: Ust Zaman Dilimi Trendi Boga (+20)")
    elif htf_trend == "BEARISH":
        # LONG sinyaline ceza ver, trende karşı işlem açma!
        long_score -= 30
        short_score += 20
        short_reasons.append("MTF: Ust Zaman Dilimi Trendi Ayi (+20)")
    
    if htf_trend == "BEARISH" and (st_sell_trigger or macd_down_cross or rsi_sell_trigger):
        # Üst zaman dilimi bearish ise SHORT sinyaline ek destek
        short_score += 10
        short_reasons.append("MTF: Buyuk Trend Yonunde SHORT (+10)")
    elif htf_trend == "BULLISH" and (st_buy_trigger or macd_up_cross or rsi_buy_trigger):
        long_score += 10
        long_reasons.append("MTF: Buyuk Trend Yonunde LONG (+10)")

    # 2. Temel Kesişim Tetikleyicileri (+25 Puan)
    if st_buy_trigger:
        long_score += 25
        long_reasons.append("SuperTrend: Yukari Yonlu Kırılım (+25)")
    if macd_up_cross:
        long_score += 25
        long_reasons.append("MACD: Yukari Yönlü Kesisim (+25)")
    if rsi_buy_trigger:
        long_score += 20
        long_reasons.append("RSI: Asiri Satimdan Donus (+20)")

    if st_sell_trigger:
        short_score += 25
        short_reasons.append("SuperTrend: Asagi Yonlu Kırılım (+25)")
    if macd_down_cross:
        short_score += 25
        short_reasons.append("MACD: Asagi Yönlü Kesisim (+25)")
    if rsi_sell_trigger:
        short_score += 20
        short_reasons.append("RSI: Asiri Alimdan Donus (+20)")

    # 3. EMA Trend Onayları (+15 Puan)
    is_above_ema200 = close > ema_200
    is_above_ema50 = close > ema_50
    ema_50_above_200 = ema_50 > ema_200

    if is_above_ema200 and is_above_ema50:
        long_score += 15
        long_reasons.append("EMA: EMA50 ve EMA200 uzerinde (+15)")
    elif not is_above_ema200 and not is_above_ema50:
        short_score += 15
        short_reasons.append("EMA: EMA50 ve EMA200 altinda (+15)")

    if ema_50_above_200:
        long_score += 10
        long_reasons.append("EMA: Golden Cross Aktif (+10)")
    else:
        short_score += 10
        short_reasons.append("EMA: Death Cross Aktif (+10)")

    # 4. Hacim ve OBV Momentum Onayları (+15 Puan)
    if is_volume_spike:
        if close > prev_close:
            long_score += 15
            long_reasons.append("Volume: Yuksek Hacimli Alis Patlamasi (+15)")
        else:
            short_score += 15
            short_reasons.append("Volume: Yuksek Hacimli Satis Patlamasi (+15)")
            
    if obv > obv_ema:
        long_score += 10
        long_reasons.append("OBV: Hacim Akisi Alislari Destekliyor (+10)")
    else:
        short_score += 10
        short_reasons.append("OBV: Hacim Akisi Satislari Destekliyor (+10)")

    # 5. Bollinger Bant Breakout Onayı (+15 Puan)
    if bb_breakout_up:
        long_score += 15
        long_reasons.append("Bollinger: Ust Banttan Disari Patlama (+15)")
    elif bb_breakout_down:
        short_score += 15
        short_reasons.append("Bollinger: Alt Banttan Disari Patlama (+15)")

    if is_squeezed:
        long_reasons.append("Bollinger: Sıkışma Var (Volatilite Yakin)")
        short_reasons.append("Bollinger: Sıkışma Var (Volatilite Yakin)")

    # ---------------------------------------------------------------
    # Nihai Karar ve Derecelendirme (A++, A, B)
    # ---------------------------------------------------------------
    signal_type = None
    final_score = 0
    grade = None
    reasons_list = []

    has_long_trigger = st_buy_trigger or macd_up_cross or rsi_buy_trigger or bb_breakout_up
    has_short_trigger = st_sell_trigger or macd_down_cross or rsi_sell_trigger or bb_breakout_down

    if has_long_trigger and long_score >= 45 and long_score > short_score:
        signal_type = "LONG"
        final_score = long_score
        reasons_list = long_reasons
    elif has_short_trigger and short_score >= 45 and short_score > long_score:
        signal_type = "SHORT"
        final_score = short_score
        reasons_list = short_reasons

    if signal_type:
        if final_score >= 80:
            grade = "A++"
        elif final_score >= 60:
            grade = "A"
        else:
            grade = "B"

    # ---------------------------------------------------------------
    # ATR (Average True Range) Tabanlı TP ve SL Hesaplama
    # ---------------------------------------------------------------
    tr1 = df['High'] - df['Low']
    tr2 = (df['High'] - df['Close'].shift()).abs()
    tr3 = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    if pd.isna(atr) or atr <= 0:
        atr = close * 0.01

    if signal_type == "LONG":
        tp_price = round(close + (atr * 2.0), 6)
        sl_price = round(close - (atr * 1.0), 6)
    elif signal_type == "SHORT":
        tp_price = round(close - (atr * 2.0), 6)
        sl_price = round(close + (atr * 1.0), 6)
    else:
        tp_price = None
        sl_price = None

    # Confluence (İndikatör Uyumu) Skoru
    confluence_pct = min(final_score, 100) if final_score else 0

    # Risk/Ödül oranı
    if tp_price and sl_price and signal_type:
        potential_gain = abs(tp_price - close)
        potential_loss = abs(sl_price - close)
        rr_ratio = round(potential_gain / potential_loss, 1) if potential_loss > 0 else 0
        tp_pct = round((potential_gain / close) * 100, 2)
        sl_pct = round((potential_loss / close) * 100, 2)
    else:
        rr_ratio = 0
        tp_pct = 0
        sl_pct = 0

    # ---------------------------------------------------------------
    # Önerilen Kasa Yönetimi (Dinamik Bakiye ve 10x Kaldıraç için)
    # ---------------------------------------------------------------
    if tp_price and sl_price and signal_type:
        sl_fraction = potential_loss / close
        leverage_val = 10.0
        
        # Risk seviyelerine göre kaybedilecek maksimum tutarlar (Bakiye yüzdeleri)
        # Düşük Risk: Kasanın %3'ü kayıp
        # Orta Risk: Kasanın %5'i kayıp
        # Yüksek Risk: Kasanın %10'u kayıp
        loss_low = total_capital * 0.03
        loss_medium = total_capital * 0.05
        loss_high = total_capital * 0.10
        
        margin_low = min(loss_low / (leverage_val * sl_fraction), total_capital)
        margin_medium = min(loss_medium / (leverage_val * sl_fraction), total_capital)
        margin_high = min(loss_high / (leverage_val * sl_fraction), total_capital)
        
        risk_management_text = (
            f"💰 ÖNERİLEN GİRİŞ MİKTARLARI ({total_capital:,.0f} TL Kasa için - 10x):\n"
            f"  🟢 Düşük Risk (Kaybın en fazla {loss_low:.1f} TL olur): {margin_low:.0f} TL Teminat\n"
            f"  🟡 Orta Risk (Kaybın en fazla {loss_medium:.0f} TL olur): {margin_medium:.0f} TL Teminat\n"
            f"  🔴 Yüksek Risk (Kaybın en fazla {loss_high:.0f} TL olur): {margin_high:.0f} TL Teminat\n"
            f"  (Not: Kasan değiştikçe panelden bakiyeni güncelleyebilirsin)"
        )
    else:
        risk_management_text = ""

    # ---------------------------------------------------------------
    # Detay Raporu (Telegram ve Dashboard için)
    # ---------------------------------------------------------------
    trend_text = "Boğa/Yükseliş" if is_above_ema200 else "Ayı/Düşüş"
    rsi_text = "Aşırı Satım" if rsi < rsi_os else ("Aşırı Alım" if rsi > rsi_ob else "Nötr")
    st_text = "YUKARI (LONG)" if st_val else "ASAGI (SHORT)"
    sq_text = "Sıkışma Var ⚡" if is_squeezed else "Normal"

    price_fmt = f"{close:,.4f}" if close < 10 else f"{close:,.2f}"
    tp_fmt = f"{tp_price:,.4f}" if tp_price and tp_price < 10 else f"{tp_price:,.2f}" if tp_price else "—"
    sl_fmt = f"{sl_price:,.4f}" if sl_price and sl_price < 10 else f"{sl_price:,.2f}" if sl_price else "—"

    details_parts = [
        f"💵 Anlık Fiyat: {price_fmt}",
        f"🎯 Hedef Fiyat (TP): {tp_fmt} (+%{tp_pct})",
        f"🛑 Zarar Durdur (SL): {sl_fmt} (-%{sl_pct})",
        f"⚖️ Risk/Ödül Oranı: 1:{rr_ratio}",
        f"📊 İndikatör Uyumu: %{confluence_pct}/100",
        f"---"
    ]
    if risk_management_text:
        details_parts.append(risk_management_text)
        details_parts.append("---")
        
    details_parts.extend([
        f"📈 EMA Trendi: {trend_text}",
        f"🔵 RSI: {rsi:.1f} ({rsi_text})",
        f"⚡ SuperTrend: {st_text}",
        f"📉 MACD Gücü: {'Güçlü' if macd_is_strong else 'Zayıf'}",
        f"💧 Volume: {'Patlama 🔥' if is_volume_spike else 'Normal'}",
        f"🔀 OBV: {'Pozitif Akış ▲' if obv > obv_ema else 'Negatif Akış ▼'}",
        f"📏 Bollinger: {sq_text}",
        f"🌐 MTF Trend: {htf_trend if htf_trend else 'Bilinmiyor'}",
        f"---",
        f"✅ Onay Gerekçeleri:\n" + "\n".join(f"• {r.split(' (+')[0]}" for r in reasons_list)
    ])

    details = "\n".join(details_parts)

    return signal_type, details, grade, tp_price, sl_price, confluence_pct


# -------------------------------------------------------------------
# Tarama Çalıştırıcı (MTF Destekli)
# -------------------------------------------------------------------

def run_scan(timeframe: str = "1h") -> dict:
    """Tüm yapılandırılmış tickerları MTF analiz onaylı şekilde tarar."""
    config = load_config()
    bist_tickers = config.get("bist_tickers", [])
    crypto_tickers = config.get("crypto_tickers", [])
    indicators = config.get("indicators", {})
    total_capital = float(config.get("total_capital", 1000.0))

    global active_signals
    new_signals_found = 0
    errors = []
    scanned_items = []

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Üst Zaman Dilimini (HTF) belirle
    # 15m -> 1h, 1h -> 4h (Kripto) veya 1d (BIST), 4h -> 1d
    htf_map_crypto = {"15m": "1h", "1h": "4h", "4h": "1d", "1d": None}
    htf_map_bist = {"15m": "1h", "1h": "1d", "4h": "1d", "1d": None}

    # BIST tara
    for symbol in bist_tickers:
        try:
            # 1. Alt zaman dilimi verisi (LTF)
            df_ltf = fetch_bist_data(symbol, timeframe)
            
            # 2. Üst zaman dilimi trendini kontrol et (HTF)
            htf = htf_map_bist.get(timeframe)
            htf_trend = None
            if htf:
                try:
                    df_htf = fetch_bist_data(symbol, htf)
                    if len(df_htf) >= 200:
                        df_htf['EMA_200'] = df_htf['Close'].ewm(span=200, adjust=False).mean()
                        last_close_htf = float(df_htf.iloc[-1]['Close'])
                        last_ema200_htf = float(df_htf.iloc[-1]['EMA_200'])
                        htf_trend = "BULLISH" if last_close_htf > last_ema200_htf else "BEARISH"
                except Exception as htf_err:
                    logger.warning(f"HTF ({htf}) trendi alinamadi: {htf_err}. Yalnizca LTF taranacak.")

            # 3. Analiz yap
            signal, details, grade, tp_price, sl_price, confluence_pct = analyze_market_data(df_ltf, indicators, htf_trend, total_capital)
            current_price = float(df_ltf.iloc[-1]['Close'])
            scanned_items.append({
                "symbol": symbol,
                "type": "BIST",
                "price": current_price,
                "signal": signal,
                "grade": grade
            })

            if signal:
                existing_sig = active_signals.get(symbol)
                should_notify = False

                if not existing_sig or existing_sig["signal_type"] != signal or existing_sig.get("grade") != grade:
                    should_notify = True
                elif existing_sig:
                    old_price = existing_sig.get("price", 0)
                    if old_price > 0:
                        pct_change = abs(current_price - old_price) / old_price * 100
                        if pct_change >= 2.0:
                            should_notify = True

                if should_notify:
                    from notifier import send_signal_alert
                    send_signal_alert(symbol, "BIST", signal, current_price, timeframe, details, grade, tp_price, sl_price, confluence_pct)
                    active_signals[symbol] = {
                        "signal_type": signal,
                        "price": current_price,
                        "tp_price": tp_price,
                        "sl_price": sl_price,
                        "confluence_pct": confluence_pct,
                        "time": timestamp,
                        "details": details,
                        "grade": grade
                    }
                    new_signals_found += 1
            else:
                if symbol in active_signals:
                    del active_signals[symbol]
        except Exception as e:
            err_msg = f"BIST {symbol}: {e}"
            logger.error(err_msg)
            errors.append(err_msg)

    # Kripto tara
    for symbol in crypto_tickers:
        try:
            # 1. Alt zaman dilimi verisi (LTF)
            df_ltf = fetch_crypto_data(symbol, timeframe)
            
            # 2. Üst zaman dilimi trendini kontrol et (HTF)
            htf = htf_map_crypto.get(timeframe)
            htf_trend = None
            if htf:
                try:
                    df_htf = fetch_crypto_data(symbol, htf)
                    if len(df_htf) >= 200:
                        df_htf['EMA_200'] = df_htf['Close'].ewm(span=200, adjust=False).mean()
                        last_close_htf = float(df_htf.iloc[-1]['Close'])
                        last_ema200_htf = float(df_htf.iloc[-1]['EMA_200'])
                        htf_trend = "BULLISH" if last_close_htf > last_ema200_htf else "BEARISH"
                except Exception as htf_err:
                    logger.warning(f"HTF ({htf}) trendi alinamadi: {htf_err}. Yalnizca LTF taranacak.")

            # 3. Analiz yap
            signal, details, grade, tp_price, sl_price, confluence_pct = analyze_market_data(df_ltf, indicators, htf_trend, total_capital)
            current_price = float(df_ltf.iloc[-1]['Close'])
            scanned_items.append({
                "symbol": symbol,
                "type": "Crypto",
                "price": current_price,
                "signal": signal,
                "grade": grade
            })

            if signal:
                existing_sig = active_signals.get(symbol)
                should_notify = False

                if not existing_sig or existing_sig["signal_type"] != signal or existing_sig.get("grade") != grade:
                    should_notify = True
                elif existing_sig:
                    old_price = existing_sig.get("price", 0)
                    if old_price > 0:
                        pct_change = abs(current_price - old_price) / old_price * 100
                        if pct_change >= 2.0:
                            should_notify = True

                if should_notify:
                    from notifier import send_signal_alert
                    send_signal_alert(symbol, "Crypto", signal, current_price, timeframe, details, grade, tp_price, sl_price, confluence_pct)
                    active_signals[symbol] = {
                        "signal_type": signal,
                        "price": current_price,
                        "tp_price": tp_price,
                        "sl_price": sl_price,
                        "confluence_pct": confluence_pct,
                        "time": timestamp,
                        "details": details,
                        "grade": grade
                    }
                    new_signals_found += 1
            else:
                if symbol in active_signals:
                    del active_signals[symbol]
        except Exception as e:
            err_msg = f"Crypto {symbol}: {e}"
            logger.error(err_msg)
            errors.append(err_msg)

    # Tarama günlüğünü kaydet
    log_entry = {
        "time": timestamp,
        "scanned_count": len(bist_tickers) + len(crypto_tickers),
        "new_signals": new_signals_found,
        "items": scanned_items,
        "errors": errors
    }
    scan_history.insert(0, log_entry)
    if len(scan_history) > 50:
        scan_history.pop()

    return log_entry
