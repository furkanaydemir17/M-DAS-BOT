@echo off
echo ============================================
echo   Midas ^& Kripto Sinyal Botu Baslatiliyor
echo ============================================
echo.

:: Gerekli paketlerin kurulumu (ilk calistirmada)
pip install -r requirements.txt --quiet 2>nul

echo Sunucu baslatiliyor...
echo Bilgisayardan: http://localhost:8000
echo Telefondan: http://[BILGISAYAR-IP]:8000
echo (Ayni WiFi aginda olmaniz gerekir)
echo Durdurmak icin CTRL+C tuslayiniz.
echo.

python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
pause
