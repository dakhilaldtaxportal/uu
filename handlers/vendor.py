from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import SessionLocal, Vendor

ORDER_TEXT_WAIT = 30
BROADCAST_TEXT_WAIT = 31

def is_vendor(user_id: int) -> bool:
    session = SessionLocal()
    try:
        return session.query(Vendor).filter_by(telegram_id=user_id, is_suspended=False).first() is not None
    finally:
        session.close()

async def vendor_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_vendor(user.id):
        await update.message.reply_text("আপনি Vendor হিসেবে রেজিস্টার্ড নন।")
        return
    text = (
        "🏪 Vendor Menu\n\n"
        "• **Order** → Vendor থেকে ১ কিমি এর মধ্যে Rider খুঁজবে\n"
        "• **Broadcast** → ৫ কিমি পর্যন্ত + extra pay"
    )
    keyboard = [
        [
            InlineKeyboardButton("📦 Order (1km)", callback_data="vendor_order_normal"),
            InlineKeyboardButton("📢 Broadcast (5km)", callback_data="vendor_order_broadcast"),
        ],
        [InlineKeyboardButton("ℹ️ My Info", callback_data="vendor_myinfo")],
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def vendor_myinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = SessionLocal()
    try:
        v = session.query(Vendor).filter_by(telegram_id=query.from_user.id).first()
        if not v:
            await query.edit_message_text("Vendor পাওয়া যায়নি।")
            return
        text = (
            f"🏪 {v.name}\n"
            f"📱 {v.phone}\n"
            f"📍 Address: {v.address or '-'}\n"
            f"📌 Location: {v.lat:.5f}, {v.lon:.5f}\n"
            f"Status: {'🚫 Suspended' if v.is_suspended else '✅ Active'}"
        )
        await query.edit_message_text(text)
    finally:
        session.close()

async def start_normal_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Callback বা Command দুটো থেকেই আসতে পারে
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        target = query.message
    else:
        user_id = update.effective_user.id
        target = update.message

    if not is_vendor(user_id):
        await target.reply_text("আপনি Vendor হিসেবে রেজিস্টার্ড নন।")
        return ConversationHandler.END

    context.user_data["order_type"] = "normal"
    await target.reply_text(
        "📦 Normal Order\n\n"
        "অর্ডারের বিবরণ + Customer-এর Google Maps Link একসাথে পাঠান।\n\n"
        "উদাহরণ:\n২ পিস বার্গার\nhttps://maps.app.goo.gl/xxxxx"
    )
    return ORDER_TEXT_WAIT


async def start_broadcast_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        target = query.message
    else:
        user_id = update.effective_user.id
        target = update.message

    if not is_vendor(user_id):
        await target.reply_text("আপনি Vendor হিসেবে রেজিস্টার্ড নন।")
        return ConversationHandler.END

    context.user_data["order_type"] = "broadcast"
    await target.reply_text(
        "📢 Broadcast Order (৫ কিমি)\n\n"
        "অর্ডারের বিবরণ + Customer-এর Google Maps Link পাঠান।\n"
        "Broadcast-এ Rider-কে extra টাকা দিতে হবে।"
    )
    return BROADCAST_TEXT_WAIT
async def receive_order_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from handlers.order import create_and_dispatch_order
    text = update.message.text or ""
    order_type = context.user_data.get("order_type", "normal")
    user_id = update.effective_user.id
    await update.message.reply_text("অর্ডার প্রসেস হচ্ছে...")
    result = await create_and_dispatch_order(context, user_id, text, order_type)
    await update.message.reply_text(result)
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_vendor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("বাতিল।")
    context.user_data.clear()
    return ConversationHandler.END
