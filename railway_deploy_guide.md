# 🚀 Vesteros RPG Telegram Bot: Railway-ga Yuklash va Boshqarish Qo'llanmasi

Ushbu hujjat Vesteros RPG Telegram botini (Python + MySQL) **Railway** bulutli platformasida Google Sheets-siz, super tezkor va xavfsiz holatda ishga tushirish hamda ma'lumotlar bazasini boshqarish bo'yicha to'liq qo'llanmadir.

---

## 📋 1. GitHub-ga Yuklash Ketma-ketligi

Loyiha papkasida (`vps_bot`) maxfiy parollar (`.env`) va foydalanuvchilar ma'lumotlari (`.csv` fayllar) GitHub-ga chiqib ketmasligi uchun `.gitignore` fayli tayyorlangan. Shuning uchun loyihani GitHub-ga xavfsiz yuklashingiz mumkin.

### 💻 Git orqali yuklash qadamlari:
1. GitHub hisobingizga kiring va yangi repozitoriy yarating. Uni **Private** (shaxsiy, yopiq) qilish tavsiya etiladi.
2. Mahalliy kompyuter terminalida (PowerShell yoki Git Bash) `vps_bot` papkasiga kiring.
3. Quyidagi buyruqlarni ketma-ket bajaring:
   ```bash
   # Gitni ishga tushirish
   git init
   
   # Barcha o'zgarishlarni qo'shish (.gitignore tufayli .env va CSV'lar qo'shilmaydi)
   git add .
   
   # Commit yaratish
   git commit -m "feat: railway integration and auto webhook"
   
   # Branch nomini main qilish
   git branch -M main
   
   # GitHub repozitoriyingizga bog'lash (o'z havolangizni qo'ying)
   git remote add origin https://github.com/foydalanuvchi_nomingiz/repozitoriy_nomi.git
   
   # GitHub-ga yuklash
   git push -u origin main
   ```

---

## 🛢️ 2. Railway-da MySQL va Loyihani Yaratish

1. [railway.app](https://railway.app) saytiga kiring va kirish tugmasini bosing.
2. **"New Project"** tugmasini bosing.
3. Ro'yxatdan **"Provision MySQL"** ni tanlang. Railway bir necha soniyada bo'sh MySQL bazasini yaratadi.
4. Baza yaratilgach, bo'sh joyga sichqonchani bosib, **"New"** -> **"GitHub Repository"** ni bosing va GitHub-ga yuklagan loyihangizni tanlang.

---

## 🔄 3. Mahalliy Kompyuterdan Baza Migratsiyasini Bajarish

Railway MySQL bazasi **persistent (doimiy)** hisoblanadi. Undagi ma'lumotlar server o'chib yonganda o'chib ketmaydi. Google Sheets-dan eksport qilingan `.csv` ma'lumotlarni bazaga yozish uchun mahalliy kompyuterdan quyidagi bosqichlarni bajaring:

### ⚙️ Migratsiya qilish qadamlari:
1. Railway panelida **MySQL** xizmati ustiga bosing.
2. **"Variables"** yoki **"Connect"** bo'limidan **Tashqi ulanish (External Connection)** ma'lumotlarini nusxalab oling.
3. Mahalliy kompyuteringizdagi `vps_bot/.env` faylini oching va quyidagi o'zgaruvchilarni Railway-dan olingan ma'lumotlarga moslab yozing:
   ```env
   # Railway MySQL tashqi ulanish ma'lumotlari:
   DB_HOST=containers-us-west-xxx.railway.app
   DB_USER=root
   DB_PASSWORD=sizning_railway_parolingiz
   DB_NAME=railway
   DB_PORT=xxxxx
   ```
4. Google Sheets-dagi barcha jadvallarni `.csv` formatda yuklab oling va ularni mahalliy `vps_bot` papkasi ichiga (yoki `vps_bot/heets` ichiga) quyidagi nomlar bilan saqlang:
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
5. Mahalliy terminalda `vps_bot` ichida turib quyidagi buyruqni bering:
   ```bash
   python migrate_db.py
   ```
   *Ushbu buyruq mahalliy kompyuterdagi CSV ma'lumotlarni Railway-dagi MySQL bazasiga bir necha soniyada xavfsiz ko'chiradi. Bu ishni faqat bir marta boshida bajarasiz!*

> [!WARNING]
> **Muhim eslatma:** `python migrate_db.py` buyrug'i bazadagi mavjud ma'lumotlarni tozalab (delete qilib), CSV fayldagi boshlang'ich ma'lumotlarni qaytadan yozadi. Bot ishga tushib, foydalanuvchilar o'yinni o'ynashni boshlagandan so'ng bu buyruqni qayta ishga tushirmang, aks holda barcha o'yin natijalari o'chib ketadi!

---

## ⚙️ 4. Railway-da Muhit O'zgaruvchilarini Sozlash

Loyiha to'g'ri ishlashi uchun uning sozlamalariga kirib **"Variables"** bo'limida quyidagi o'zgaruvchilarni qo'shing:

* `BOT_TOKEN` = `Sizning_Telegram_Bot_Tokeningiz`
* `ADMIN_TELEGRAM_ID` = `Sizning_Telegram_IDingiz`
* `PORT` = `3000` (yoki Railway bergan port)

> [!NOTE]
> Loyihamiz Railway MySQL o'zgaruvchilarini avtomatik taniydigan qilingan. Baza ma'lumotlarini xizmatga qo'lda kiritib o'tirish shart emas! Ular avtomatik ulanadi.

---

## 🔗 5. Webhook-ni Avtomatik Sozlash va Ishga Tushirish

Botingiz Telegram-dan xabarlarni qabul qilishi uchun unga domen kerak. Railway buni avtomatik qiladi:

1. Railway-da bot xizmati ustiga bosing.
2. **"Settings"** bo'limiga o'ting.
3. **"Networking"** qismida **"Generate Domain"** tugmasini bosing.
4. Railway sizga `https://loyihangiz.up.railway.app` ko'rinishidagi bepul SSL domen beradi.
5. **Tayyor!** Loyiha qayta ishga tushganda, tizim ushbu domenni avtomatik tarzda aniqlaydi va Telegram Webhook-ni o'rnatadi (`server.py` tomonidan bajariladi). Hech qanday qo'shimcha amallar bajarishingiz shart emas.

---

## 🗄️ 6. Kelajakda Bazani Tahrirlash va O'zgartirish

O'yin davomida foydalanuvchilar o'ynaganda barcha natijalar (balans, xonadon devorlari, askarlar va urushlar) MySQL bazasiga yozilib boradi va o'zgaradi. Siz ham kelajakda bazani qo'lda tahrirlashingiz mumkin:

### 💻 1-Usul: Railway veb-interfeysi orqali:
1. Railway panelida MySQL xizmati ustiga bosing.
2. Yuqoridagi **"Data"** yorlig'iga o'ting.
3. U yerdan barcha jadvallaringizni (users, houses va h.k.) tanlab, ma'lumotlarni to'g'ridan-to'g'ri veb-brauzerda tahrirlashingiz, o'chirishingiz yoki yangi qatorlar qo'shishingiz mumkin.

### 🔌 2-Usul: Tashqi SQL dasturlari orqali:
1. Kompyuteringizga bepul SQL client o'rnating: [DBeaver](https://dbeaver.io/) yoki [Navicat](https://www.navicat.com/).
2. Railway MySQL panelidan olingan **External Connection** (Tashqi ulanish) havolasi yoki uning alohida qismlari (Host, Port, User, Password, Database) orqali ushbu dasturda yangi ulanish yarating.
3. Ulanish muvaffaqiyatli amalga oshgach, o'yin bazasini xuddi o'z kompyuteringizdagidek to'liq boshqara olasiz.

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
