# ☁️ 24/7 Kesintisiz Sunucu (Bulut/VPS) Kurulum Rehberi

Botun bilgisayarınız kapandığında da çalışmaya devam etmesi için kodların uzak bir sunucuda (Virtual Private Server - VPS) barındırılması gerekir. Bu rehberde en kolay ve ucuz/ücretsiz yöntemler listelenmiştir.

---

## Yöntem 1: Ücretsiz Bulut Platformları (Eko-Sistemler)

Bu servisler, kodunuzu ücretsiz veya çok düşük maliyetlerle 24 saat çalıştırabileceğiniz platformlardır.

### A. Render.com (Ücretsiz / Kolay)
Render, Python web uygulamalarını ücretsiz barındırabilir.
1. [github.com](https://github.com) üzerinde ücretsiz bir hesap açın ve bu proje klasöründeki dosyaları yeni bir depoya (repository) yükleyin.
2. [render.com](https://render.com) adresine gidin, Github hesabınızla giriş yapın.
3. **New +** butonuna basıp **Web Service** seçin. Github deponuzu bağlayın.
4. Ayarları şu şekilde yapın:
   - **Runtime:** `Python`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python -m uvicorn app:app --host 0.0.0.0 --port $PORT`
5. **Advanced** kısmından **Add Environment Variable** diyerek `PYTHONIOENCODING=utf-8` ekleyin.
6. *Not:* Render ücretsiz planında web uygulamaları 15 dakika istek almazsa uyku moduna geçer. Bunu önlemek için [cron-job.org](https://cron-job.org) sitesinden ücretsiz bir üyelik açıp, Render'ın size verdiği `.onrender.com` adresine her 10 dakikada bir istek (GET request) atacak bir zamanlayıcı tanımlayabilirsiniz. Böylece botunuz 24 saat kesintisiz çalışır.

---

## Yöntem 2: Kendi Sanal Sunucunuz (VPS - En Güvenli & Profesyonel)

Aylık yaklaşık 3$ - 5$ (yaklaşık 100-150 TL) bütçeyle DigitalOcean, Hetzner veya OVH gibi servislerden bir Linux VPS kiralayabilirsiniz. Bu yöntem finansal botlar için en kararlı yöntemdir.

### Adım Adım VPS Kurulumu:
1. **Sunucu Kiralama:**
   - [Hetzner.com](https://www.hetzner.com) veya [DigitalOcean.com](https://www.digitalocean.com) üzerinden en ucuz planlı bir **Ubuntu LTS** sunucu oluşturun.
2. **Sunucuya Bağlantı:**
   - Bilgisayarınızdan terminali (veya Windows'ta PowerShell'i) açıp sunucunuza bağlanın:
     ```bash
     ssh root@SUNUCU_IP_ADRESINIZ
     ```
3. **Gerekli Araçların Kurulumu:**
   - Sunucuyu güncelleyin ve Python kurun:
     ```bash
     sudo apt update && sudo apt upgrade -y
     sudo apt install python3-pip python3-venv git screen -y
     ```
4. **Kodların Yüklenmesi:**
   - GitHub üzerinden veya doğrudan dosyaları sunucuya kopyalayın:
     ```bash
     git clone <github_repo_linkiniz> /opt/midas-bot
     cd /opt/midas-bot
     ```
5. **Bağımlılıkların Kurulumu:**
   - Sanal ortam oluşturup kütüphaneleri yükleyin:
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     pip install -r requirements.txt
     ```
6. **Arka Planda 24 Saat Çalıştırma (Screen ile):**
   - Sunucu bağlantısını kapatsanız bile botun çalışmaya devam etmesi için `screen` oturumu açın:
     ```bash
     screen -S midasbot
     source venv/bin/activate
     python -m uvicorn app:app --host 0.0.0.0 --port 8000
     ```
   - Oturumu arka plana almak için klavyeden `CTRL + A` ve ardından `D` tuşlarına basın.
   - Artık sunucu bağlantısını güvenle kapatabilirsiniz. Bot arka planda 24 saat çalışmaya devam edecektir.
   - Tekrar duruma bakmak isterseniz sunucuya bağlanıp `screen -r midasbot` yazabilirsiniz.
