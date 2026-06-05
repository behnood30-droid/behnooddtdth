# ربات فروش کانفیگ V2Ray

ربات تلگرام برای فروش خودکار کانفیگ V2Ray با درگاه پرداخت **tetra98** و پنل **PasarGuard**.

## جریان کار

```
کاربر → /start → انتخاب پلن → لینک پرداخت tetra98
→ پرداخت → callback به /webhook/payment → تأیید با tetra98
→ ساخت کاربر در PasarGuard → ارسال لینک ساب به کاربر
```

## پیش‌نیازها

- Python 3.11+
- Ubuntu 24.04 (یا هر distro دیگه‌ای)
- دامنه با SSL (برای دریافت callback از tetra98)
- Nginx + Certbot

## ساختار فایل‌ها

```
peech-bot/
├── main.py          # نقطه ورود — telegram polling + FastAPI
├── bot.py           # هندلرهای تلگرام
├── webhook.py       # FastAPI: دریافت callback پرداخت
├── tetra.py         # کلاینت tetra98
├── pasarguard.py    # کلاینت پنل PasarGuard
├── delivery.py      # منطق ساخت کاربر و ارسال کانفیگ
├── db.py            # دیتابیس SQLite
├── plans.py         # تعریف پلن‌ها
├── config.py        # خواندن ENV
├── .env.example     # نمونه متغیرهای محیطی
├── peech-bot.service # systemd service
└── nginx.conf       # Nginx reverse proxy
```

## نصب روی VPS

### ۱. دریافت کد

```bash
sudo mkdir -p /opt/peech-bot
sudo chown ubuntu:ubuntu /opt/peech-bot
cd /opt/peech-bot
git clone https://github.com/behnood30-droid/behnooddtdth.git .
```

### ۲. محیط مجازی Python

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### ۳. تنظیم متغیرهای محیطی

```bash
cp .env.example .env
nano .env          # مقادیر واقعی رو وارد کن
```

مقادیر مورد نیاز:

| متغیر | توضیح |
|-------|-------|
| `TELEGRAM_BOT_TOKEN` | توکن ربات از @BotFather |
| `ADMIN_TELEGRAM_ID` | آی‌دی عددی تلگرام ادمین (از @userinfobot) |
| `TETRA_API_KEY` | کلید API از داشبورد tetra98.com |
| `PASARGUARD_URL` | آدرس پنل مثلاً `https://my-panel.com:8000` |
| `PASARGUARD_USERNAME` | یوزر ادمین پنل |
| `PASARGUARD_PASSWORD` | پسورد ادمین پنل |
| `PASARGUARD_GROUP_ID` | شناسه گروه VLESS در پنل |
| `WEBHOOK_DOMAIN` | دامنه عمومی سرور مثلاً `https://bot.example.com` |
| `WEBHOOK_PORT` | پورت داخلی FastAPI (پیش‌فرض: `8080`) |

### ۴. Nginx + SSL

```bash
sudo apt install nginx certbot python3-certbot-nginx -y

# nginx config را کپی کن و your-domain.com را با دامنه واقعی جایگزین کن
sudo cp nginx.conf /etc/nginx/sites-available/peech-bot
sudo nano /etc/nginx/sites-available/peech-bot   # دامنه رو تغییر بده

sudo ln -s /etc/nginx/sites-available/peech-bot /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# SSL بگیر
sudo certbot --nginx -d your-domain.com
```

### ۵. systemd service

```bash
# User=ubuntu را با نام کاربر واقعی جایگزین کن
sudo cp peech-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable peech-bot
sudo systemctl start peech-bot
```

بررسی وضعیت:

```bash
sudo systemctl status peech-bot
sudo journalctl -u peech-bot -f   # لاگ زنده
```

## تست بدون پرداخت واقعی

به‌عنوان ادمین می‌توانید سفارش را دستی تحویل بدهید:

```
/deliver <order_id>
```

مثال: `/deliver A3F2C891B704E1D5`

## دستورات ربات

| دستور | توضیح |
|-------|-------|
| `/start` | شروع و نمایش پلن‌ها |
| `/my_orders` | لیست سفارش‌های کاربر |
| `/deliver <id>` | تحویل دستی (فقط ادمین) |

## پلن‌ها

| پلن | حجم | مدت | قیمت (تومان) |
|-----|-----|-----|--------------|
| ۱ | ۱۰ گیگ | ۳۰ روز | ۱۲۰٬۰۰۰ |
| ۲ | ۳۰ گیگ | ۳۰ روز | ۳۰۰٬۰۰۰ |
| ۳ | ۵۰ گیگ | ۳۰ روز | ۴۵۰٬۰۰۰ |
| ۴ | ۱۰۰ گیگ | ۳۰ روز | ۷۰۰٬۰۰۰ |
| ۵ | ۲۰۰ گیگ | ۳۰ روز | ۱٬۶۰۰٬۰۰۰ |

برای تغییر پلن‌ها، فایل `plans.py` را ویرایش کن و سرویس را ریستارت بده.

## نکات مهم

### PasarGuard
- API این پنل مشابه Marzban است.
- اگر `subscription_url` در پاسخ نبود، کد خودکار با GET دوباره می‌گیرد.
- پنل روی پورت ۸۰۰۰ با self-signed cert کار می‌کند — SSL verify غیرفعال است.

### tetra98
- ربات callback را دریافت می‌کند، سپس با `/api/verify` تأیید مجدد می‌گیرد.
- در صورت شکست verify، پرداخت نادیده گرفته می‌شود.

### Retry
- در صورت شکست ساخت کاربر در پنل، تا ۳ بار با backoff تلاش مجدد می‌شه.
- بعد از ۳ شکست، به کاربر و ادمین اطلاع داده می‌شه.
