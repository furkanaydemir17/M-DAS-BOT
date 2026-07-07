import requests
import logging
from config import load_config

logger = logging.getLogger("notifier")


def _escape_html(text: str) -> str:
    """Telegram HTML parse modu için özel karakterleri escape eder."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def send_telegram_message(message: str) -> bool:
    """
    Yapılandırılmış Telegram sohbetine mesaj gönderir.
    HTML format destekler.
    """
    config = load_config()
    token = config.get("telegram_token")
    chat_id = config.get("telegram_chat_id")

    if not token or not chat_id:
        logger.warning("Telegram token veya chat ID yapılandırmada eksik.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code == 200:
            logger.info("Telegram bildirimi başarıyla gönderildi.")
            return True
        else:
            logger.error(f"Telegram mesaj gönderilemedi: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Telegram bildirimi gönderilirken hata: {e}")
        return False


def send_signal_alert(symbol: str, market_type: str, signal_type: str, price: float, timeframe: str, details: str, grade: str = None, tp_price: float = None, sl_price: float = None, confluence_pct: int = 0) -> bool:
    """
    Biçimlendirilmiş işlem uyarısı gönderir (TP, SL, Confluence Skoru dahil).
    market_type: 'BIST' veya 'Crypto'
    signal_type: 'LONG' (AL) veya 'SHORT' (SAT)
    grade: 'A++', 'A', 'B' (Derece)
    """
    is_long = signal_type.upper() == "LONG"
    direction_emoji = "🟢" if is_long else "🔴"
    direction_text = "📈 LONG (AL)" if is_long else "📉 SHORT (SAT)"
    market_emoji = "🇹🇷" if market_type.upper() == "BIST" else "🪙"

    # Derece başlığı
    if grade == "A++":
        grade_header = "🔥🔥 <b>ULTRA GÜÇLÜ SİNYAL — A++</b> 🔥🔥"
    elif grade == "A":
        grade_header = "⭐⭐ <b>GÜÇLÜ SİNYAL — A</b> ⭐⭐"
    else:
        grade_header = "⚡ <b>ORTA SİNYAL — B</b>"

    # Confluence (İndikatör Uyumu) çubuğu
    filled = int(confluence_pct / 10)
    bar = "🟩" * filled + "⬜" * (10 - filled)
    confluence_text = f"{bar} <b>%{confluence_pct}</b>"

    # Fiyat formatı
    def fmt(v):
        if v is None: return "—"
        return f"{v:,.4f}" if v < 10 else f"{v:,.2f}"

    price_str = fmt(price)
    tp_str = fmt(tp_price)
    sl_str = fmt(sl_price)
    currency = "TL" if market_type.upper() == "BIST" else "USDT"

    # TP/SL yüzdeleri
    if tp_price and sl_price:
        tp_pct = round(abs(tp_price - price) / price * 100, 2)
        sl_pct = round(abs(sl_price - price) / price * 100, 2)
        tp_line = f"🎯 <b>Hedef Fiyat (TP):</b> <code>{tp_str} {currency}</code>  <i>(+%{tp_pct})</i>"
        sl_line = f"🛑 <b>Zarar Durdur (SL):</b> <code>{sl_str} {currency}</code>  <i>(-%{sl_pct})</i>"
        rr = round(tp_pct / sl_pct, 1) if sl_pct > 0 else 0
        rr_line = f"⚖️ <b>Risk / Kâr Oranı:</b>  1 : {rr}"
    else:
        tp_line = f"🎯 <b>Hedef Fiyat (TP):</b> —"
        sl_line = f"🛑 <b>Zarar Durdur (SL):</b> —"
        rr_line = f"⚖️ <b>Risk / Kâr Oranı:</b> —"

    message = (
        f"🚨 <b>YENİ İŞLEM SİNYALİ</b> 🚨\n"
        f"{grade_header}\n\n"
        f"{market_emoji} <b>{_escape_html(symbol)}</b>  |  ⏱️ {_escape_html(timeframe)}\n"
        f"{direction_emoji} <b>Yön:</b>  {direction_text}\n\n"
        f"💵 <b>Anlık Fiyat:</b>  <code>{price_str} {currency}</code>\n"
        f"{tp_line}\n"
        f"{sl_line}\n"
        f"{rr_line}\n\n"
        f"📊 <b>İndikatör Uyumu:</b>\n{confluence_text}\n\n"
        f"<b>📋 Detaylı Analiz:</b>\n<pre>{_escape_html(details)}</pre>\n\n"
        f"⚠️ <i>Bu bir yatırım tavsiyesi değildir. Kendi analizinizle teyit edin. Risk yönetimi yapın!</i>"
    )

    return send_telegram_message(message)


def test_telegram_connection(token: str, chat_id: str) -> tuple:
    """
    Telegram token ve Chat ID'yi doğrular, test mesajı gönderir.
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": "🔌 <b>Midas &amp; Kripto Takip Botu Bağlantı Testi</b>\n\nBağlantı başarıyla kuruldu! Sinyaller bu kanal üzerinden iletilecektir.",
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code == 200:
            return True, "Success"
        else:
            return False, response.json().get("description", "Unknown error")
    except Exception as e:
        return False, str(e)
