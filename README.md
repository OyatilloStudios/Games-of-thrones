# 🚀 Vesteros RPG Telegram Bot: VPS va MySQL O'rnatish Qo'llanmasi

Ushbu loyiha Game of Thrones RPG Telegram botining Google Apps Script-dan Python (Flask + pyTelegramBotAPI) va MySQL bazasiga ko'chirilgan (super tezkor) talqinidir.

---

## 🏗️ 1. VPS Serverni Tayyorlash (Hetzner, DigitalOcean va h.k.)

Serveringizga (Ubuntu/Debian) kiring va kerakli muhitni o'rnating:

```bash
# Tizimni yangilash
sudo apt update && sudo apt upgrade -y

# Python 3 va pip o'rnatish (agar o'rnatilmagan bo'lsa)
sudo apt install python3 python3-pip python3-venv -y

# PM2 (Dasturni fonda turg'un saqlash va boshqarish uchun) o'rnatish
# PM2 Node.js orqali ishlaydi, shuning uchun Node.js va npm kerak bo'ladi
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs
sudo npm install pm2 -g

# MySQL Serverni o'rnatish
sudo apt install mysql-server -y
```

---

## 🛢️ 2. MySQL Ma'lumotlar Bazasi va Foydalanuvchi Sozlash

Terminal orqali MySQL-ga kiring:
```bash
sudo mysql
```

Quyidagi buyruqlarni bajarib, baza va maxsus foydalanuvchi yarating:
```sql
CREATE DATABASE vesteros_rpg CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Yangi foydalanuvchi yaratish (parolni o'zgartiring!)
CREATE USER 'vesteros_user'@'localhost' IDENTIFIED BY 'KuchliParol123!';
GRANT ALL PRIVILEGES ON vesteros_rpg.* TO 'vesteros_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

---

## 📂 3. Loyihani Serverga Yuklash va Sozlash

1. Serverda yangi papka ochib, `vps_bot` ichidagi fayllarni yuklang.
2. Virtual muhit (Virtual Environment) yarating va faollashtiring:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Kutubxonalarni o'rnating:
   ```bash
   pip install -r requirements.txt
   ```
4. `.env` faylini yarating va sozlang:
   ```bash
   nano .env
   ```
   Quyidagi o'zgaruvchilarni yozing:
   ```env
   BOT_TOKEN=Sizning_Telegram_Bot_Tokeningiz
   ADMIN_TELEGRAM_ID=Sizning_Telegram_IDingiz
   
   DB_HOST=localhost
   DB_USER=vesteros_user
   DB_PASSWORD=KuchliParol123!
   DB_NAME=vesteros_rpg
   DB_PORT=3306
   ```

---

## 🔄 4. Ma'lumotlarni Google Sheets-dan Ko'chirish (CSV orqali Migration)

1. Google Sheets bazangizdagi har bir jadvalni alohida `.csv` shaklida yuklab oling (fayllar nomi `Users.csv`, `Houses.csv`, `House_Units.csv`, `Units.csv` bo'lishi kerak).
2. Yuklab olingan barcha CSV fayllarni loyihaning asosiy papkasiga (yoki `heets` papkasiga) yuklang.
3. Migratsiya skriptini ishga tushiring (virtual muhit faol holatda):
   ```bash
   python migrate_db.py
   ```
   Skript MySQL-da jadvallarni yaratadi va barcha CSV ma'lumotlarni bir necha soniyada MySQL jadvallariga xavfsiz ko'chirib beradi.

---

## 🚀 5. Botni Ishga Tushirish (PM2)

Bot serverini fonda (doimiy) ishga tushirish uchun PM2-dan foydalanamiz:
```bash
# Virtual muhit faollashtirilgan holda PM2 bilan ishga tushirish:
pm2 start server.py --name "vesteros-bot" --interpreter ./venv/bin/python

# Server o'chib yonganda bot avtomatik yoqilishi uchun:
pm2 startup
pm2 save
```

---

## 🪝 6. Telegram Webhook-ni VPS-ga Yo'naltirish

Telegram-ga VPS serveringiz manzilini webhook qilib ulashingiz kerak. Telegram webhook faqat **HTTPS** (xavfsiz SSL) orqali ishlaydi. 

VPS-ga bepul SSL (Nginx + Certbot) ulash uchun:
```bash
sudo apt install nginx certbot python3-certbot-nginx -y
```

Nginx konfiguratsiyasini oching (`/etc/nginx/sites-available/default`) va Flask server portiga (3000) reverse-proxy o'rnating:
```nginx
location / {
    proxy_pass http://localhost:3000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection 'upgrade';
    proxy_set_header Host $host;
    proxy_cache_bypass $http_upgrade;
}
```

Nginx-ni qayta yuklang va SSL sertifikatini oling:
```bash
sudo systemctl restart nginx
sudo certbot --nginx -d domeningiz.uz
```

Sertifikat olingach, `.env` faylingizni yangilab `PUBLIC_URL` qo'shib qo'ying:
```env
PUBLIC_URL=https://domeningiz.uz
```
Va botni qayta yuklang:
```bash
pm2 restart vesteros-bot
```

Bot endi soniyaning yuzdan bir ulushida **super tezkor** ishlaydi va Sheets-dagi cheklovlardan butunlay qutuldi! 🎉
