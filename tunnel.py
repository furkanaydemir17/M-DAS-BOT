"""
Cloudflare Tunnel Yöneticisi
Ücretsiz, kayıt gerektirmeyen geçici tunnel oluşturur.
Dünyanın her yerinden telefonla erişim sağlar.
"""
import subprocess
import threading
import re
import logging
import os
import sys

logger = logging.getLogger("tunnel")

# Tunnel durumu
tunnel_state = {
    "url": None,
    "status": "stopped",  # stopped, starting, running, error
    "error": None,
    "process": None
}


def get_cloudflared_path() -> str:
    """cloudflared.exe'nin yolunu döndürür."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "cloudflared.exe")


def is_cloudflared_available() -> bool:
    """cloudflared.exe mevcut mu kontrol eder."""
    return os.path.exists(get_cloudflared_path())


def _read_tunnel_output(process):
    """Tunnel sürecinin çıktısını okuyup URL'yi yakalar."""
    global tunnel_state
    url_pattern = re.compile(r'https://[a-zA-Z0-9\-]+\.trycloudflare\.com')

    for line in process.stderr:
        line = line.strip()
        if line:
            logger.info(f"[tunnel] {line}")

            # URL'yi yakala
            match = url_pattern.search(line)
            if match:
                tunnel_state["url"] = match.group(0)
                tunnel_state["status"] = "running"
                logger.info(f"🌍 Tunnel aktif! Public URL: {tunnel_state['url']}")

    # Süreç sona erdiyse
    if tunnel_state["status"] == "running":
        tunnel_state["status"] = "stopped"
        tunnel_state["url"] = None
        logger.warning("Tunnel bağlantısı kesildi.")


def start_tunnel(port: int = 8000) -> dict:
    """
    Cloudflare Tunnel başlatır.
    Kayıt veya hesap gerektirmez — ücretsiz geçici URL oluşturur.
    """
    global tunnel_state

    if tunnel_state["status"] == "running" and tunnel_state["process"]:
        return {"status": "already_running", "url": tunnel_state["url"]}

    if not is_cloudflared_available():
        tunnel_state["status"] = "error"
        tunnel_state["error"] = "cloudflared.exe bulunamadı!"
        return {"status": "error", "message": tunnel_state["error"]}

    tunnel_state["status"] = "starting"
    tunnel_state["error"] = None
    tunnel_state["url"] = None

    try:
        cloudflared_path = get_cloudflared_path()
        process = subprocess.Popen(
            [cloudflared_path, "tunnel", "--url", f"http://localhost:{port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        tunnel_state["process"] = process

        # Çıktıyı arka planda oku
        reader_thread = threading.Thread(target=_read_tunnel_output, args=(process,), daemon=True)
        reader_thread.start()

        return {"status": "starting", "message": "Tunnel başlatılıyor, birkaç saniye bekleyin..."}

    except Exception as e:
        tunnel_state["status"] = "error"
        tunnel_state["error"] = str(e)
        logger.error(f"Tunnel başlatılamadı: {e}")
        return {"status": "error", "message": str(e)}


def stop_tunnel() -> dict:
    """Tunnel sürecini durdurur."""
    global tunnel_state

    if tunnel_state["process"]:
        try:
            tunnel_state["process"].terminate()
            tunnel_state["process"].wait(timeout=5)
        except Exception:
            try:
                tunnel_state["process"].kill()
            except Exception:
                pass
        tunnel_state["process"] = None

    tunnel_state["url"] = None
    tunnel_state["status"] = "stopped"
    tunnel_state["error"] = None
    return {"status": "stopped", "message": "Tunnel durduruldu."}


def get_tunnel_status() -> dict:
    """Tunnel durumunu döndürür."""
    return {
        "url": tunnel_state["url"],
        "status": tunnel_state["status"],
        "error": tunnel_state["error"],
        "available": is_cloudflared_available()
    }
