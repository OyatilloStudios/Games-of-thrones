# 🚀 Telegram Botni Railway-ga Joylashtirish va Sozlash Qo'llanmasi

Ushbu loyiha Python va MySQL ma'lumotlar bazasida yozilgan. Uni Railway platformasida ishga tushirish uchun quyidagi bosqichlarni ketma-ket bajaring.

---

## 📂 1. Loyalash va Tayyorgarlik

Railway platformasi botingizni o'rnatganda shaxsiy sozlamalar (Bot Token, Parollar) va CSV ma'lumotlaringiz xavfsiz turishi uchun loyihaga `.gitignore` fayli qo'shildi. 
Bu fayl `.env` va `.csv` fayllaringizni GitHub-ga chiqib ketishidan (omma ko'rib qolishidan) himoya qiladi.

---

## 🛢️ 2. Railway-da Loyiha va MySQL-ni Yaratish

1. [railway.app](https://railway.app) saytiga kiring va o'z hisobingizga kiring.
2. **"New Project"** tugmasini bosing.
3. Menyudan **"Provision MySQL"** (yoki **"Database"** -> **"MySQL"**) ni tanlang.
4. Railway siz uchun MySQL ma'lumotlar bazasini yaratadi.

---

## 🔄 3. Mahalliy Kompyuterdan Ma'lumotlarni Migratsiya Qilish (CSV -> Railway)

Railway-dagi MySQL bazasi doimiy va o'chmas (persistent). Shuning uchun Google Sheets-dan eksport qilingan CSV ma'lumotlarni Railway-ga bir marta mahalliy kompyuteringiz orqali yozib yuborasiz:

1. Railway-dagi MySQL xizmatini ustiga bosing.
2. **"Variables"** yoki **"Connect"** bo'limiga o'ting.
3. Quyidagi **Tashqi ulanish (External Connection)** ma'lumotlarini nusxalab oling:
   * `MYSQLHOST` (masalan, `containers-us-west-...railway.app` kabi tashqi domen)
   * `MYSQLPORT` (masalan, `3306` yoki boshqa port)
   * `MYSQLUSER` (odatda `root`)
   * `MYSQLPASSWORD` (Railway bergan maxfiy parol)
   * `MYSQLDATABASE` (odatda `railway`)
4. Mahalliy kompyuteringizdagi `vps_bot/.env` faylini oching va ushbu ma'lumotlarni o'rnating:
   ```env
   BOT_TOKEN=Sizning_Telegram_Bot_Tokeningiz
   ADMIN_TELEGRAM_ID=Sizning_Telegram_ID
   
   # Railway-dan olingan Tashqi MySQL ulanishlar:
   DB_HOST=containers-us-west-xxx.railway.app
   DB_USER=root
   DB_PASSWORD=sizning_railway_parolingiz
   DB_NAME=railway
   DB_PORT=xxxxx
   ```
5. Google Sheets jadvallaringizni `.csv` ko'rinishida yuklab oling va ularni mahalliy `vps_bot` papkasiga (yoki `vps_bot/heets` ichiga) quyidagi nomlar bilan joylashtiring:
   * `Houses.csv`
   * `Users.csv`
   * `Units.csv`
   * `House_Units.csv`
   * `Bank_Treasury.csv`
   * `Loans.csv`
   * `Broadcasts.csv`
   * `Transactions.csv`
   * `Battles.csv`
   * `Casino_Broadcasts.csv`
6. Mahalliy kompyuteringiz terminalida `vps_bot` papkasiga kiring va quyidagi buyruqni bering:
   ```bash
   python migrate_db.py
   ```
   *Ushbu buyruq mahalliy CSV fayllaringizni o'qib, ularni Railway-da joylashgan MySQL bazasiga bir necha soniyada xavfsiz yuklaydi.*

> [!WARNING]
> **Muhim eslatma:** `python migrate_db.py` buyrug'i bazadagi eski ma'lumotlarni tozalab tashlaydi. Bot ishga tushib, foydalanuvchilar o'yinni boshlagandan so'ng bu buyruqni qayta ishga tushirmang, aks holda barcha o'yin natijalari yo'qoladi!

---

## 🚀 4. Botni Railway-ga Yuklash (GitHub orqali)

Baza tayyor bo'lgach, bot kodini Railway-ga yuklaymiz:

1. `vps_bot` papkangizni shaxsiy GitHub-ingizga yuklang (private repository qilish tavsiya etiladi).
2. Railway boshqaruv panelida (Dashboard) **"New"** -> **"GitHub Repository"** tugmasini bosing va bot yuklangan repository-ni tanlang.
3. Loyiha yuklanishi boshlanadi.

---

## ⚙️ 5. Railway-da Muhit O'zgaruvchilarini (Variables) Sozlash

Bot serveri to'g'ri ishlashi uchun Railway-dagi xizmatning **"Variables"** bo'limiga o'ting va quyidagi o'zgaruvchilarni qo'shing:

1. `BOT_TOKEN` = `Sizning_Telegram_Bot_Tokeningiz`
2. `ADMIN_TELEGRAM_ID` = `Sizning_Telegram_ID`
3. `PORT` = `3000` (yoki Railway default qoldirgan port)

> [!NOTE]
> Loyihamiz Railway MySQL o'zgaruvchilarini (MYSQLHOST, MYSQLUSER, MYSQLPASSWORD va boshqalar) avtomatik taniydigan qilingan. Baza ma'lumotlarini xizmatga qo'lda kiritib o'tirish shart emas! Ular avtomatik ulanadi.

---

## 🔗 6. Webhookni Avtomatik Sozlash

Telegram bot webhook orqali xabarlarni qabul qilishi uchun unga umumiy domen kerak bo'ladi. Buni Railway-da sozlash juda oson:

1. Railway dashboard-da bot xizmatining ustiga bosing.
2. **"Settings"** bo'limiga o'ting.
3. **"Networking"** qismida **"Generate Domain"** tugmasini bosing.
4. Railway sizga `https://loyihangiz.up.railway.app` ko'rinishidagi bepul SSL domen beradi.
5. **Bo'ldi!** Loyiha qayta ishga tushganda, tizim ushbu domenni avtomatik tarzda aniqlaydi va Telegram Webhook-ni shu zaxoti sozlab oladi. Hech qanday qo'shimcha amallar bajarishingiz shart emas.

---

## 🩺 7. Statusni Tekshirish

Botingiz ishlayotganligini tekshirish uchun brauzeringizda quyidagi manzilga kiring:
`https://loyihangiz.up.railway.app/status`

U sizga quyidagi JSON natijani qaytarishi kerak:
```json
{
  "status": "active",
  "bot_username": "botingiz_nomi"
}
```
Agar bu yozuv chiqsa, demak, botingiz Railway platformasida 100% tezkor va muvaffaqiyatli ishga tushdi!
