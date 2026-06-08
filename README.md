# ربات فروش کانفیگ V2Ray

ربات تلگرام با کیف پول داخلی، شارژ USDT (BEP20/TRC20)، و تحویل خودکار کانفیگ از PasarGuard.

## جریان کار

```
کاربر → شارژ کیف پول با USDT → تأیید خودکار تراکنش → انتخاب پلن
→ کسر از موجودی → ساخت کانفیگ در PasarGuard → ارسال لینک ساب
```

## ساختار فایل‌ها

```
├── main.py          # نقطه ورود — polling + scheduler
├── bot.py           # هندلرهای تلگرام
├── scheduler.py     # چک تراکنش‌ها هر ۳۰ ثانیه
├── wallet.py        # قیمت USDT + بررسی BSCScan/Tronscan
├── delivery.py      # ساخت کانفیگ با retry و refund
├── pasarguard.py    # کلاینت پنل PasarGuard
├── db.py            # SQLite (users, orders, wallet_charges)
├── plans.py         # پلن‌ها
├── config.py        # خواندن ENV
└── peech-bot.service # systemd service
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
| `ADMIN_TELEGRAM_ID` | آی‌دی عددی ادمین (از @userinfobot) |
| `PASARGUARD_URL` | آدرس پنل مثل `https://panel.com:8000` |
| `PASARGUARD_USERNAME` | ادمین پنل |
| `PASARGUARD_PASSWORD` | پسورد ادمین |
| `PASARGUARD_GROUP_ID` | شناسه گروه VLESS از بخش Groups پنل |
| `USDT_BEP20_ADDRESS` | آدرس کیف پول BEP20 شما |
| `USDT_TRC20_ADDRESS` | آدرس کیف پول TRC20 شما |
| `BSCSCAN_API_KEY` | از bscscan.com/myapikey |
| `SUPPORT_USERNAME` | یوزرنیم تلگرام پشتیبانی (بدون @) |

### ۴. systemd service

```bash
# در peech-bot.service، User=ubuntu را با کاربر واقعی جایگزین کن
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

## دستورات ادمین

| دستور | توضیح |
|-------|-------|
| `/addbalance <id> <amount>` | افزودن موجودی دستی |
| `/cancel` | لغو عملیات جاری |

## پلن‌ها

| پلن | حجم | مدت | قیمت |
|-----|-----|-----|------|
| ۱ | ۱۰ گیگ | ۳۰ روز | ۱۲۰٬۰۰۰ تومان |
| ۲ | ۳۰ گیگ | ۳۰ روز | ۳۰۰٬۰۰۰ تومان |
| ۳ | ۵۰ گیگ | ۳۰ روز | ۴۵۰٬۰۰۰ تومان |
| ۴ | ۱۰۰ گیگ | ۳۰ روز | ۷۰۰٬۰۰۰ تومان |
| ۵ | ۲۰۰ گیگ | ۳۰ روز | ۱٬۶۰۰٬۰۰۰ تومان |

## نحوه شارژ کیف پول

۱. کاربر «💰 افزایش موجودی» می‌زند
۲. شبکه BEP20 یا TRC20 انتخاب می‌کند
۳. مبلغ USDT را وارد می‌کند
۴. ربات قیمت لحظه‌ای از Nobitex می‌گیرد
۵. یک مبلغ یکتا (مثل ۱۰.۰۰۳) ساخته می‌شود
۶. ربات هر ۳۰ ثانیه BSCScan/Tronscan را چک می‌کند
۷. پس از تأیید، موجودی به تومان اضافه می‌شود (timeout: 30 دقیقه)

## نکات مهم

- **Retry**: در صورت شکست ساخت کانفیگ، ۳ بار با backoff تلاش می‌شود
- **Refund**: اگر بعد از ۳ تلاش کانفیگ ساخته نشد، موجودی برگردانده می‌شود
- **Admin alert**: تمام خطاها به ادمین اطلاع داده می‌شود
