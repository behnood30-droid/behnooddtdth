# 🎵 ربات موزیک تلگرام

ربات تلگرامی که آهنگ رو فقط به کاربران عضو کانال‌های اجباری می‌فرسته.

---

## ساختار پروژه

```
music_bot/
├── bot.py          ← منطق اصلی و هندلرهای کاربر
├── admin.py        ← هندلرهای ادمین + آپلود آهنگ
├── database.py     ← تمام عملیات SQLite
├── config.py       ← توکن و تنظیمات
├── requirements.txt
├── songs/          ← فایل‌های صوتی آپلود شده
└── bot.log         ← لاگ‌ها (ساخته می‌شه هنگام اجرا)
```

---

## نصب و راه‌اندازی

### ۱. پیش‌نیازها

- Python 3.10 یا بالاتر
- pip
- سرور Ubuntu 24.04

### ۲. کلون کردن پروژه

```bash
git clone <your-repo-url>
cd music_bot
```

### ۳. ساختن virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### ۴. نصب کتابخونه‌ها

```bash
pip install -r requirements.txt
```

### ۵. اجرای ربات (مستقیم)

```bash
python bot.py
```

---

## راه‌اندازی سرویس systemd (همیشه روشن)

برای اینکه ربات بعد از ریستارت سرور هم به طور خودکار شروع به کار کنه:

### ۱. ساختن فایل سرویس

```bash
sudo nano /etc/systemd/system/music-bot.service
```

محتوای فایل (مسیرها رو با مسیر واقعی خودت عوض کن):

```ini
[Unit]
Description=Telegram Music Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/music_bot
ExecStart=/home/ubuntu/music_bot/venv/bin/python bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### ۲. فعال‌سازی و اجرا

```bash
sudo systemctl daemon-reload
sudo systemctl enable music-bot
sudo systemctl start music-bot
```

### ۳. بررسی وضعیت

```bash
sudo systemctl status music-bot
```

### مشاهده لاگ‌ها

```bash
# لاگ systemd (real-time)
sudo journalctl -u music-bot -f

# فایل لاگ ربات
tail -f /home/ubuntu/music_bot/bot.log
```

### دستورات سرویس

```bash
sudo systemctl stop music-bot      # متوقف کردن
sudo systemctl restart music-bot   # ریستارت
sudo systemctl disable music-bot   # غیرفعال کردن autostart
```

---

## دستورات ادمین

| دستور | توضیح |
|-------|--------|
| `/upload` | آپلود آهنگ جدید (مکالمه چند مرحله‌ای) |
| `/songs` | لیست همه آهنگ‌ها با لینک هر کدوم |
| `/deletesong 3` | حذف آهنگ با شناسه ۳ |
| `/channels` | نمایش کانال‌های اجباری فعلی |
| `/addchannel @user \| عنوان \| لینک` | اضافه کردن کانال اجباری |
| `/removechannel @user` | حذف کانال از لیست اجباری |

### مثال `/addchannel`

```
/addchannel @peechgooshtii | پیچ گوشتی | https://t.me/peechgooshtii
```

---

## جریان کاربر

```
کاربر روی لینک کلیک می‌کنه
         ↓
  t.me/BOT?start=SONG_ID
         ↓
  بررسی عضویت کانال‌ها
    ↙             ↘
عضو نیست        عضو هست
    ↓                ↓
نمایش دکمه‌های    ارسال آهنگ 🎵
جوین + دکمه
«عضو شدم ✅»
    ↓
کاربر عضو شد و دکمه رو زد
    ↓
بررسی مجدد عضویت
    ↓
ارسال آهنگ 🎵
```

---

## نکات مهم

- ربات باید در کانال‌های اجباری **ادمین** باشه تا بتونه عضویت کاربر رو چک کنه.
- حداکثر حجم فایل قابل دانلود از تلگرام: **20MB**. فایل‌های بزرگتر فقط با file_id ذخیره می‌شن.
- دیتابیس SQLite به صورت خودکار هنگام اولین اجرا ساخته می‌شه.
