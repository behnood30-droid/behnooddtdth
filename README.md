# ربات فروش کانفیگ V2Ray — Peech Bot

ربات تلگرام با پرداخت مستقیم (ریالی + کریپتو) و تحویل خودکار کانفیگ از PasarGuard.

## جریان کار

```
کاربر → انتخاب پلن → انتخاب روش پرداخت
  ├── پیروزچنج (کارت بانکی) → webhook/polling
  └── USDT BEP20/TRC20     → polling BSCScan/Tronscan
→ تأیید پرداخت → ساخت کانفیگ در PasarGuard → تحویل سرویس
```

## ساختار فایل‌ها

```
├── main.py        # نقطه ورود — PTB polling + FastAPI webhook + scheduler
├── bot.py         # هندلرهای اصلی تلگرام
├── admin.py       # پنل ادمین (/admin)
├── payment.py     # فلوی پرداخت (pirooz + USDT)
├── pirooz.py      # کلاینت API پیروزچنج
├── usdt.py        # بررسی BSCScan / Tronscan
├── webhook.py     # FastAPI — دریافت webhook پیروز
├── delivery.py    # ساخت کانفیگ با retry و notification
├── scheduler.py   # چک تراکنش‌ها هر ۳۰ ثانیه
├── pasarguard.py  # کلاینت پنل PasarGuard
├── db.py          # SQLite (users, payments, settings)
├── plans.py       # پلن‌ها
├── config.py      # خواندن ENV
├── utils.py       # تاریخ شمسی، اعداد فارسی، progress bar
└── peech-bot.service
```

## نصب روی Ubuntu 24.04

### ۱. دریافت کد

```bash
sudo mkdir -p /opt/peech-bot
sudo chown $USER:$USER /opt/peech-bot
cd /opt/peech-bot
git clone https://github.com/behnood30-droid/behnooddtdth.git .
git checkout claude/v2ray-telegram-bot-2moSn
```

### ۲. محیط مجازی

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### ۳. متغیرهای محیطی

```bash
cp .env.example .env
nano .env
```

| متغیر | توضیح |
|-------|-------|
| `TELEGRAM_BOT_TOKEN` | از @BotFather |
| `ADMIN_TELEGRAM_ID` | آی‌دی عددی ادمین |
| `PASARGUARD_URL` | آدرس پنل مثل `https://panel.com:8000` |
| `PASARGUARD_USERNAME` | ادمین پنل |
| `PASARGUARD_PASSWORD` | پسورد ادمین |
| `PASARGUARD_GROUP_ID` | شناسه گروه VLESS از بخش Groups |
| `WEBHOOK_DOMAIN` | دامنه سرور برای webhook پیروز، مثل `https://bot.example.com` |
| `WEBHOOK_PORT` | پورت FastAPI (پیش‌فرض: 8080) |
| `USDT_BEP20_ADDRESS` | آدرس کیف پول BEP20 |
| `USDT_TRC20_ADDRESS` | آدرس کیف پول TRC20 |
| `BSCSCAN_API_KEY` | از bscscan.com/myapikey |
| `PIROOZ_API_KEY` | کلید API پیروزچنج |
| `PIROOZ_PROVIDER_KEY` | کلید provider پیروزچنج |
| `PIROOZ_BASE_URL` | آدرس API پیروز (پیش‌فرض ست شده) |
| `SUPPORT_USERNAME` | یوزرنیم تلگرام پشتیبانی |

### ۴. Nginx reverse proxy (برای webhook)

```nginx
server {
    listen 443 ssl;
    server_name bot.example.com;

    ssl_certificate     /etc/letsencrypt/live/bot.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/bot.example.com/privkey.pem;

    location /webhook/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### ۵. systemd service

```bash
sudo cp peech-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable peech-bot
sudo systemctl start peech-bot
sudo systemctl status peech-bot
```

مشاهده لاگ:
```bash
sudo journalctl -u peech-bot -f
```

## پلن‌ها

| پلن | حجم | مدت | قیمت |
|-----|-----|-----|------|
| 🟢 | ۱۰ گیگ | ۳۰ روز | ۱۲۰,۰۰۰ تومان |
| 🔵 | ۳۰ گیگ | ۳۰ روز | ۳۰۰,۰۰۰ تومان 🔥 پرفروش |
| 🟣 | ۵۰ گیگ | ۳۰ روز | ۴۵۰,۰۰۰ تومان |
| 🟡 | ۱۰۰ گیگ | ۳۰ روز | ۷۰۰,۰۰۰ تومان 💎 ویژه |
| 🔴 | ۲۰۰ گیگ | ۳۰ روز | ۱,۶۰۰,۰۰۰ تومان 🎁 اقتصادی |

## روش‌های پرداخت

### پیروزچنج (ریالی)
- کارت‌به‌کارت از طریق ربات @PiroozPayBot
- webhook فوری + polling هر ۳۰ ثانیه

### USDT کریپتو
- BEP20 (Binance Smart Chain)
- TRC20 (Tron)
- مبلغ یکتا برای شناسایی تراکنش
- polling BSCScan / Tronscan هر ۳۰ ثانیه

## دستورات ادمین

`/admin` — پنل مدیریت با گزینه‌های:
- 💵 تنظیم نرخ USDT (تومان)
- 📊 آمار ربات
- 👥 لیست کاربران (صفحه‌بندی)
- 🔍 جستجوی کاربر
- ⏳ مدیریت پرداخت‌های در انتظار (تأیید/لغو دستی)
- 🔧 تلاش مجدد برای پرداخت‌های ناموفق
- 📢 پیام همگانی (متن یا عکس)

## نکات مهم

- **Retry**: ۳ بار با backoff در صورت شکست ساخت کانفیگ
- **مهلت پرداخت**: ۳۰ دقیقه برای USDT و پیروز
- **امنیت webhook**: اعتبارسنجی X-Signature از پیروزچنج
- **امنیت callback**: بررسی ownership قبل از هر عملیات
