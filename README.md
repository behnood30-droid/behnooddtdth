# ربات فروش کانفیگ (PasarGuard + Tetrapay)

ربات تلگرام برای فروش خودکار کانفیگ از پنل **PasarGuard** با پرداخت **تتراپی (USDT)**.

## جریان کار

1. کاربر `/start` می‌زند → لیست پلن‌ها را می‌بیند.
2. روی پلن می‌زند → ربات فاکتور تتراپی می‌سازد و لینک پرداخت می‌فرستد.
3. کاربر پرداخت می‌کند → تتراپی به `/tetrapay/callback` می‌زند.
4. ربات کاربر را در پنل PasarGuard می‌سازد و لینک ساب (subscription URL) را برای کاربر می‌فرستد.

## نصب

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# .env را با مقادیر واقعی پر کن
```

## تنظیمات مهم

### `.env`
- `TELEGRAM_BOT_TOKEN`: توکن ربات از @BotFather
- `PASARGUARD_*`: آدرس پنل + یوزر/پس ادمین
- `PASARGUARD_DEFAULT_GROUP_IDS`: گروه‌(های) پیش‌فرضی که کاربر جدید به آن‌ها اضافه می‌شود (از پنل شناسه گروه را پیدا کن)
- `TETRAPAY_API_KEY`: کلید API تتراپی
- `TETRAPAY_WEBHOOK_SECRET`: اگر تتراپی امضای webhook می‌فرستد، اینجا بگذار
- `PUBLIC_BASE_URL`: آدرس عمومی سرور تو (مثلاً `https://bot.example.com`) — این آدرس باید از اینترنت قابل دسترسی باشد تا callback تتراپی برسد

### `config.yaml`
پلن‌ها اینجا تعریف می‌شوند. هر تغییر در پلن‌ها فقط با ریستارت ربات اعمال می‌شود.

## اجرا

```bash
python bot.py
```

ربات هم polling تلگرام را اجرا می‌کند هم وب‌سرور webhook را روی `WEBHOOK_PORT` (پیش‌فرض 8080).

پشت یک reverse proxy (Caddy/Nginx) با HTTPS بگذار و آدرس عمومی را در `PUBLIC_BASE_URL` قرار بده.

## نکات مهم

### پنل PasarGuard
کد بر اساس مسیرهای استاندارد PasarGuard نوشته شده:
- `POST /api/admin/token` برای لاگین
- `POST /api/user` برای ساخت کاربر

اگر پاسخ ساخت کاربر فیلد `subscription_url` نداشت، کد اتوماتیک `GET /api/user/{username}` می‌زند تا لینک ساب را بگیرد.

### تتراپی
چون مستندات دقیق تتراپی عمومی نبود، کد با ساختار متداول REST نوشته شده. اگر مسیر یا نام فیلد فرق دارد، فقط `src/tetrapay.py` را تطبیق بده:
- اگر مسیر ساخت فاکتور `/invoice/create` نیست → تغییر بده
- اگر فیلد `payment_url` نام دیگری دارد → کد به `pay_url` و `url` هم نگاه می‌کند، فیلد جدید را اضافه کن
- اگر امضای webhook به جای HMAC-SHA256 الگوریتم دیگری دارد → `verify_webhook` را اصلاح کن

### تست بدون پرداخت واقعی
به‌عنوان ادمین می‌توانی سفارش را دستی تحویل بدهی:
```
/deliver 5
```
(آی‌دی ادمین باید در `TELEGRAM_ADMIN_IDS` باشد)

## ساختار

```
.
├── bot.py                # نقطه ورود
├── config.yaml           # پلن‌ها و پیام‌ها
├── requirements.txt
├── .env.example
└── src/
    ├── config.py         # بارگذاری تنظیمات
    ├── db.py             # SQLite (سفارش‌ها)
    ├── pasarguard.py     # کلاینت پنل
    ├── tetrapay.py       # کلاینت درگاه
    ├── delivery.py       # منطق تحویل سفارش
    ├── handlers.py       # هندلرهای تلگرام
    └── webhook.py        # callback تتراپی (aiohttp)
```
