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


def send_signal_alert(symbol: str, market_type: str, signal_type: str, price: float, timeframe: str, details: str, grade: str = None) -> bool:
    """
    Biçimlendirilmiş işlem uyarısı gönderir (Derece detaylı).
    market_type: 'BIST' veya 'Crypto'
    signal_type: 'LONG' (AL) veya 'SHORT' (SAT)
    grade: 'A++', 'A', 'B' (Derece)
    """
    emoji = "🟢 LONG" if signal_type.upper() == "LONG" else "🔴 SHORT"
    market_emoji = "🇹🇷" if market_type.upper() == "BIST" else "🪙"

    # Derece başlığı
    grade_decor = ""
    if grade:
        if grade == "A++":
            grade_decor = "🔥 <b>ULTRA GÜÇLÜ SINYAL (A++)</b> 🔥\n"
        elif grade == "A":
            grade_decor = "⭐ <b>GÜÇLÜ SINYAL (A)</b>\n"
        elif grade == "B":
            grade_decor = "⚡ <b>ORTA ŞİDDETTE SINYAL (B)</b>\n"

    # Fiyat formatı
    if market_type.upper() == "BIST":
        price_str = f"{price:,.2f} TL"
    else:
        price_str = f"${price:,.4f}"

    safe_details = _escape_html(details)

    message = (
        f"🚨 <b>YENİ İŞLEM SİNYALİ</b> 🚨\n"
        f"{grade_decor}\n"
        f"<b>{market_emoji} Varlık:</b> <code>{_escape_html(symbol)}</code> ({_escape_html(market_type)})\n"
        f"<b>⚡ Yön:</b> {emoji}\n"
        f"<b>💵 Fiyat:</b> <code>{price_str}</code>\n"
        f"<b>⏱️ Grafik:</b> <code>{_escape_html(timeframe)}</code>\n\n"
        f"<b>📊 Kantitatif Analiz Raporu:</b>\n<pre>{safe_details}</pre>\n\n"
        f"⚠️ <i>Yatırım tavsiyesi değildir. Lütfen kendi analizinizle teyit edin.</i>"
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
