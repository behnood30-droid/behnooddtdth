"""هندلرهای ربات تلگرام."""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from config import Settings
from db import DB
from delivery import deliver_order
from plans import PLANS, get_plan
from tetra import TetraClient, TetraError

log = logging.getLogger(__name__)

MSG_WELCOME = (
    "سلام 👋 به ربات خرید کانفیگ V2Ray خوش اومدی!\n\n"
    "سرویس‌های زیر همه ۳۰ روزه هستن.\n"
    "یکی از پلن‌ها رو انتخاب کن:"
)

MSG_ORDER_CREATED = (
    "✅ سفارش شما ثبت شد!\n\n"
    "🔹 پلن: {label}\n"
    "🔹 مبلغ: {price_toman} تومان\n"
    "🔹 شماره سفارش: <code>{order_id}</code>\n\n"
    "برای پرداخت یکی از روش‌های زیر رو انتخاب کن.\n"
    "بعد از پرداخت، کانفیگ خودکار برات ارسال می‌شه 🚀"
)

MSG_CREATE_ERROR = (
    "خطا در ساخت لینک پرداخت 😕\n"
    "لطفاً دوباره تلاش کن یا با پشتیبانی تماس بگیر."
)

STATUS_FA = {
    "pending": "در انتظار پرداخت ⏳",
    "paid": "پرداخت شده ✅",
    "delivered": "تحویل داده شده 🎉",
    "failed": "ناموفق ❌",
}


def _fa(n: int | str) -> str:
    return str(n).translate(str.maketrans("0123456789,", "۰۱۲۳۴۵۶۷۸۹٬"))


def _plans_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(p.label, callback_data=f"buy:{p.id}")] for p in PLANS]
    rows.append([InlineKeyboardButton("📋 سفارش‌های من", callback_data="my_orders")])
    return InlineKeyboardMarkup(rows)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(MSG_WELCOME, reply_markup=_plans_keyboard())


async def cmd_my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    orders = db.list_user_orders(update.effective_user.id)
    if not orders:
        await update.message.reply_text("هیچ سفارشی ثبت نشده.")
        return
    lines = []
    for o in orders:
        st = STATUS_FA.get(o.status, o.status)
        line = f"🔹 <code>{o.order_id}</code> — {_fa(o.plan_gb)} گیگ — {st}"
        if o.sub_link:
            line += f"\n   ساب: <code>{o.sub_link}</code>"
        lines.append(line)
    await update.message.reply_text("\n\n".join(lines), parse_mode="HTML")


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    if data == "my_orders":
        db: DB = context.bot_data["db"]
        orders = db.list_user_orders(query.from_user.id)
        if not orders:
            await query.message.reply_text("هیچ سفارشی ثبت نشده.")
            return
        lines = []
        for o in orders:
            st = STATUS_FA.get(o.status, o.status)
            line = f"🔹 <code>{o.order_id}</code> — {_fa(o.plan_gb)} گیگ — {st}"
            if o.sub_link:
                line += f"\n   ساب: <code>{o.sub_link}</code>"
            lines.append(line)
        await query.message.reply_text("\n\n".join(lines), parse_mode="HTML")
        return

    if data.startswith("buy:"):
        try:
            plan_id = int(data.split(":")[1])
        except (ValueError, IndexError):
            return
        await _start_order(query, context, plan_id)


async def _start_order(query, context: ContextTypes.DEFAULT_TYPE, plan_id: int) -> None:
    settings: Settings = context.bot_data["settings"]
    db: DB = context.bot_data["db"]
    tetra: TetraClient = context.bot_data["tetra"]

    plan = get_plan(plan_id)
    if not plan:
        await query.message.reply_text("پلن نامعتبر.")
        return

    order_id = db.create_order(
        telegram_user_id=query.from_user.id,
        telegram_username=query.from_user.username,
        plan_gb=plan.gb,
        price_toman=plan.price_toman,
        price_rial=plan.price_rial,
        days=plan.days,
    )

    callback_url = f"{settings.webhook_domain}/webhook/payment"
    try:
        result = await tetra.create_order(
            order_id=order_id,
            amount_rial=plan.price_rial,
            callback_url=callback_url,
        )
    except TetraError as e:
        log.exception("tetra create_order failed for order %s: %s", order_id, e)
        db.mark_failed(order_id)
        await query.message.reply_text(MSG_CREATE_ERROR)
        try:
            await context.bot.send_message(
                settings.admin_telegram_id,
                f"⚠️ خطا در ساخت سفارش tetra98\n"
                f"سفارش: <code>{order_id}</code>\nخطا: {e}",
                parse_mode="HTML",
            )
        except Exception:
            pass
        return

    db.set_authority(order_id, result["authority"], result.get("tracking_id"))

    price_fa = _fa(f"{plan.price_toman:,}")
    text = MSG_ORDER_CREATED.format(
        label=plan.label,
        price_toman=price_fa,
        order_id=order_id,
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 پرداخت از طریق تلگرام", url=result["payment_url_bot"])],
        [InlineKeyboardButton("🌐 پرداخت از طریق وب", url=result["payment_url_web"])],
    ])
    await query.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)


async def cmd_deliver(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """دستور ادمین: تحویل دستی سفارش (برای تست یا موارد اضطراری)."""
    settings: Settings = context.bot_data["settings"]
    if update.effective_user.id != settings.admin_telegram_id:
        return
    if not context.args:
        await update.message.reply_text("استفاده: /deliver <order_id>")
        return

    order_id = context.args[0].upper()
    db: DB = context.bot_data["db"]
    order = db.get_order(order_id)
    if not order:
        await update.message.reply_text("سفارش یافت نشد.")
        return

    if order.status == "pending":
        db.mark_paid(order_id)
        order = db.get_order(order_id)

    await deliver_order(order, context.bot, db, context.bot_data["panel"], settings)
    await update.message.reply_text(f"سفارش {order_id} پردازش شد.")


def register_handlers(app: Application) -> None:
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("my_orders", cmd_my_orders))
    app.add_handler(CommandHandler("deliver", cmd_deliver))
    app.add_handler(CallbackQueryHandler(on_callback))
