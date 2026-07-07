import threading
import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os

from config import load_config, save_config
from notifier import test_telegram_connection
from scanner import run_scan, scan_history, active_signals
from tunnel import start_tunnel, stop_tunnel, get_tunnel_status

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("app")


# Background scheduler thread
def scheduler_loop():
    """Arka planda periyodik olarak piyasaları tarayan zamanlayıcı döngüsü."""
    logger.info("Arka plan tarama zamanlayıcısı başlatıldı.")
    # Başlangıçta 5 saniye bekle
    time.sleep(5)
    while True:
        try:
            config = load_config()
            interval = config.get("scan_interval_minutes", 15)
            logger.info("Periyodik piyasa taraması başlatılıyor...")
            run_scan()
            logger.info(f"Tarama tamamlandı. Sonraki tarama {interval} dakika sonra.")
            # 5 saniyelik aralıklarla uyu (güncelleme veya kapatma kontrolü için)
            for _ in range(int(interval * 60 / 5)):
                time.sleep(5)
        except Exception as e:
            logger.error(f"Zamanlayıcı hatası: {e}")
            time.sleep(30)


# Modern FastAPI lifespan (deprecated on_event yerine)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    t = threading.Thread(target=scheduler_loop, daemon=True)
    t.start()
    # Tunnel'ı otomatik başlat (telefondan erişim için)
    logger.info("Cloudflare Tunnel başlatılıyor...")
    start_tunnel(port=8000)
    logger.info("Uygulama başlatıldı.")
    yield
    # Shutdown
    stop_tunnel()
    logger.info("Uygulama kapatılıyor.")


app = FastAPI(title="Midas & Crypto Signal Bot API", lifespan=lifespan)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------------------------------------------------
# Pydantic Request Models
# -------------------------------------------------------------------

class TelegramTestModel(BaseModel):
    token: str
    chat_id: str


class ConfigUpdateModel(BaseModel):
    telegram_token: str
    telegram_chat_id: str
    scan_interval_minutes: int
    total_capital: float
    bist_tickers: list[str]
    crypto_tickers: list[str]
    rsi_period: int
    rsi_oversold: int
    rsi_overbought: int
    macd_fast: int
    macd_slow: int
    macd_signal: int
    supertrend_period: int
    supertrend_multiplier: float


# -------------------------------------------------------------------
# API Endpoints
# -------------------------------------------------------------------

@app.get("/api/config")
def get_config():
    """Mevcut yapılandırmayı döndürür."""
    return load_config()


@app.post("/api/config")
def update_full_config(data: ConfigUpdateModel):
    """Tüm yapılandırmayı günceller."""
    config = {
        "telegram_token": data.telegram_token,
        "telegram_chat_id": data.telegram_chat_id,
        "scan_interval_minutes": data.scan_interval_minutes,
        "total_capital": data.total_capital,
        "bist_tickers": data.bist_tickers,
        "crypto_tickers": data.crypto_tickers,
        "indicators": {
            "rsi_period": data.rsi_period,
            "rsi_oversold": data.rsi_oversold,
            "rsi_overbought": data.rsi_overbought,
            "macd_fast": data.macd_fast,
            "macd_slow": data.macd_slow,
            "macd_signal": data.macd_signal,
            "supertrend_period": data.supertrend_period,
            "supertrend_multiplier": data.supertrend_multiplier
        }
    }
    save_config(config)
    return {"status": "success", "message": "Konfigürasyon kaydedildi."}


@app.get("/api/status")
def get_status():
    """Aktif sinyalleri, tarama geçmişini ve son tarama zamanını döndürür."""
    return {
        "active_signals": active_signals,
        "history": scan_history[:20],  # Frontend'e en fazla 20 log gönder
        "active_signals_count": len(active_signals),
        "last_scan_time": scan_history[0]["time"] if scan_history else "Henüz taranmadı"
    }


@app.post("/api/scan")
def trigger_manual_scan(background_tasks: BackgroundTasks):
    """Manuel tarama tetikler."""
    background_tasks.add_task(run_scan)
    return {"status": "success", "message": "Tarama işlemi arka planda başlatıldı."}


@app.post("/api/test_telegram")
def test_telegram(data: TelegramTestModel):
    """Telegram bağlantısını test eder."""
    success, error_msg = test_telegram_connection(data.token, data.chat_id)
    if success:
        return {"status": "success", "message": "Telegram testi başarılı! Test mesajı gönderildi."}
    else:
        raise HTTPException(status_code=400, detail=f"Telegram testi başarısız: {error_msg}")


# -------------------------------------------------------------------
# Tunnel API Endpoints
# -------------------------------------------------------------------

@app.get("/api/tunnel/status")
def api_tunnel_status():
    """Tunnel durumunu döndürür."""
    return get_tunnel_status()


@app.post("/api/tunnel/start")
def api_tunnel_start():
    """Tunnel'ı başlatır."""
    return start_tunnel(port=8000)


@app.post("/api/tunnel/stop")
def api_tunnel_stop():
    """Tunnel'ı durdurur."""
    return stop_tunnel()


# -------------------------------------------------------------------
# Frontend Static Files & Root Route
# -------------------------------------------------------------------

current_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(current_dir, "static")
templates_dir = os.path.join(current_dir, "templates")

# Klasörlerin varlığını garantile
os.makedirs(static_dir, exist_ok=True)
os.makedirs(templates_dir, exist_ok=True)


@app.get("/")
def read_root():
    """Ana sayfa — kontrol paneli."""
    index_path = os.path.join(templates_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Kontrol paneli templates/index.html bulunamadı."}


@app.get("/favicon.ico")
def favicon():
    """Favicon 204 döndür (404 loglarını önle)."""
    from fastapi.responses import Response
    return Response(status_code=204)


# Static files mount — route tanımlarından SONRA olmalı
app.mount("/static", StaticFiles(directory=static_dir), name="static")
