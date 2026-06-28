import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from .config import Settings, find_plan
from .db import DB
from .delivery import deliver_order
from .pasarguard import PasarGuardClient
from .tetrapay import TetrapayClient
from .youtube_handler import build_youtube_conv_handler

log = logging.getLogger(__name__)


def _plans_keyboard(settings: Settings) -> InlineKeyboardMarkup:
    rows = []
    for p in settings.plans:
        label = f"{p.title} — {p.price_toman:,} تومان"
        rows.append([InlineKeyboardButton(label, callback_data=f"buy:{p.id}")])
    rows.append([InlineKeyboardButton("📦 سفارش‌های من", callback_data="my_orders")])
    return InlineKeyboardMarkup(rows)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    await update.message.reply_text(
        settings.messages["welcome"],
        reply_markup=_plans_keyboard(settings),
    )


async def cmd_my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.application.bot_data["db"]
    orders = db.list_user_orders(update.effective_user.id)
    if not orders:
        await update.message.reply_text("هیچ سفارشی نداری.")
        return
    lines = []
    for o in orders:
        line = f"#{o.id} — {o.plan_id} — {o.status}"
        if o.sub_url:
            line += f"\n  ساب: `{o.sub_url}`"
        elif o.pay_url and o.status == "pending":
            line += f"\n  لینک پرداخت: {o.pay_url}"
        lines.append(line)
    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    settings: Settings = context.application.bot_data["settings"]
    db: DB = context.application.bot_data["db"]

    if data == "my_orders":
        orders = db.list_user_orders(query.from_user.id)
        if not orders:
            await query.message.reply_text("هیچ سفارشی نداری.")
            return
        lines = []
        for o in orders:
            line = f"#{o.id} — {o.plan_id} — {o.status}"
            if o.sub_url:
                line += f"\n  ساب: `{o.sub_url}`"
            lines.append(line)
        await query.message.reply_text("\n\n".join(lines), parse_mode="Markdown")
        return

    if data.startswith("buy:"):
        plan_id = data.split(":", 1)[1]
        await _start_order(query, context, plan_id)
        return


async def _start_order(query, context: ContextTypes.DEFAULT_TYPE, plan_id: str) -> None:
    settings: Settings = context.application.bot_data["settings"]
    db: DB = context.application.bot_data["db"]
    tetrapay: TetrapayClient = context.application.bot_data["tetrapay"]

    plan = find_plan(settings, plan_id)
    if plan is None:
        await query.message.reply_text("پلن نامعتبر.")
        return

    order_id = db.create_order(
        tg_user_id=query.from_user.id,
        plan_id=plan.id,
        price_usdt=plan.price_usdt,
    )

    callback_url = f"{settings.public_base_url}/tetrapay/callback"
    try:
        invoice = await tetrapay.create_invoice(
            amount_usdt=plan.price_usdt,
            order_id=order_id,
            callback_url=callback_url,
            description=f"plan {plan.title}",
        )
    except Exception as e:
        log.exception("create_invoice failed: %s", e)
        db.mark_failed(order_id)
        await query.message.reply_text(
            "خطا در ساخت فاکتور پرداخت. لطفاً بعداً تلاش کن."
        )
        return

    db.set_invoice(order_id, invoice["invoice_id"], invoice["pay_url"])
    text = settings.messages["payment_pending"].format(
        order_id=order_id, pay_url=invoice["pay_url"]
    )
    await query.message.reply_text(text)


# ادمین: تحویل دستی یک سفارش (مثلاً وقتی webhook نرسیده ولی پرداخت شده)
async def cmd_deliver(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    if update.effective_user.id not in settings.admin_ids:
        return
    if not context.args:
        await update.message.reply_text("استفاده: /deliver <order_id>")
        return
    order_id = int(context.args[0])
    db: DB = context.application.bot_data["db"]
    panel: PasarGuardClient = context.application.bot_data["panel"]
    # علامت‌گذاری به‌عنوان پرداخت‌شده در صورت نیاز
    order = db.get_order(order_id)
    if order is None:
        await update.message.reply_text("سفارش یافت نشد.")
        return
    if order.status == "pending":
        db.mark_paid(order_id)
    await deliver_order(order_id, context.bot, db, panel, settings)
    await update.message.reply_text(f"سفارش {order_id} پردازش شد.")


def register_handlers(app: Application) -> None:
    app.add_handler(build_youtube_conv_handler())
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("my_orders", cmd_my_orders))
    app.add_handler(CommandHandler("deliver", cmd_deliver))
    app.add_handler(CallbackQueryHandler(on_callback))
