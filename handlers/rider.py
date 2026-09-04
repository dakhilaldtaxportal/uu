from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from database import SessionLocal, Rider
import config

RANGE_WAIT = 10
CHANGE_HOME_WAIT = 11

async def go_online(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        user_id = query.from_user.id
        target = query.message
    else:
        user_id = update.effective_user.id
        target = update.message

    session = SessionLocal()
    try:
        rider = session.query(Rider).filter_by(telegram_id=user_id).first()
        if not rider or not rider.name or rider.home_lat is None:
            text = "আগে রেজিস্ট্রেশন সম্পন্ন করুন। /registration"
            if query:
                await query.edit_message_text(text)
            else:
                await target.reply_text(text)
            return
        if rider.is_suspended:
            text = "আপনার অ্যাকাউন্ট Suspended।"
            if query:
                await query.edit_message_text(text)
            else:
                await target.reply_text(text)
            return

        loc_btn = KeyboardButton("📡 Live Location শেয়ার করুন", request_location=True)
        markup = ReplyKeyboardMarkup([[loc_btn]], one_time_keyboard=True, resize_keyboard=True)
        text = (
            "🟢 Online হতে **Live Location** শেয়ার করুন।\n\n"
            "Telegram-এ Location শেয়ার করার সময় **Live Location** সিলেক্ট করুন "
            "এবং সময়সীমা সেট করুন।\n\n"
            "Live Location চালু থাকলে Complete-এর পর আবার শেয়ার করার দরকার নেই।"
        )
        await target.reply_text(text, reply_markup=markup, parse_mode="Markdown")
    finally:
        session.close()

async def receive_live_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    location = update.message.location
    if not location:
        return

    user = update.effective_user
    session = SessionLocal()
    try:
        rider = session.query(Rider).filter_by(telegram_id=user.id).first()
        if not rider:
            return
        rider.current_lat = location.latitude
        rider.current_lon = location.longitude
        rider.last_location_update = datetime.now(timezone.utc)
        rider.is_online = True
        session.commit()
        await update.message.reply_text(
            f"✅ আপনি এখন 🟢 Online!\nLocation আপডেট হয়েছে।\nRange: {rider.range_km} km\n\n"
            "Live Location চালু রাখুন। যতক্ষণ অন থাকবে ততক্ষণ অর্ডার পেতে পারবেন।",
            reply_markup=ReplyKeyboardRemove()
        )
    finally:
        session.close()

async def go_offline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        user_id = query.from_user.id
        edit = True
    else:
        user_id = update.effective_user.id
        edit = False

    session = SessionLocal()
    try:
        rider = session.query(Rider).filter_by(telegram_id=user_id).first()
        if rider:
            rider.is_online = False
            session.commit()
            text = "🔴 আপনি Offline হয়ে গেছেন।"
        else:
            text = "রেজিস্ট্রেশন নেই।"
    finally:
        session.close()

    if edit and query:
        await query.edit_message_text(text)
    else:
        await update.effective_message.reply_text(text)

async def myinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    session = SessionLocal()
    try:
        rider = session.query(Rider).filter_by(telegram_id=user.id).first()
        if not rider:
            await update.message.reply_text("রেজিস্ট্রেশন নেই। /registration")
            return
        text = (
            f"👤 নাম: {rider.name}\n"
            f"📱 ফোন: {rider.phone}\n"
            f"🏠 Home: {rider.home_lat:.5f}, {rider.home_lon:.5f}\n"
            f"📏 Range: {rider.range_km} km\n"
            f"Status: {'🟢 Online' if rider.is_online else '🔴 Offline'}\n"
            f"Busy: {'হ্যাঁ' if rider.is_busy else 'না'}\n"
            f"Suspended: {'হ্যাঁ' if rider.is_suspended else 'না'}"
        )
        await update.message.reply_text(text)
    finally:
        session.close()

async def set_range_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.message.reply_text("Home থেকে কত কিমি পর্যন্ত ডেলিভারি নিতে চান? শুধু সংখ্যা লিখুন (উদাহরণ: 8):")
    else:
        await update.message.reply_text("Home থেকে কত কিমি পর্যন্ত ডেলিভারি নিতে চান? শুধু সংখ্যা লিখুন (উদাহরণ: 8):")
    return RANGE_WAIT

async def set_range_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        value = float(update.message.text.strip())
        if value < 1 or value > 50:
            await update.message.reply_text("১ থেকে ৫০ কিমির মধ্যে দিন।")
            return RANGE_WAIT
    except (ValueError, AttributeError):
        await update.message.reply_text("সঠিক সংখ্যা লিখুন।")
        return RANGE_WAIT

    user = update.effective_user
    session = SessionLocal()
    try:
        rider = session.query(Rider).filter_by(telegram_id=user.id).first()
        if rider:
            rider.range_km = value
            session.commit()
            await update.message.reply_text(f"✅ Range সেট হয়েছে: {value} km")
        else:
            await update.message.reply_text("রেজিস্ট্রেশন নেই।")
    finally:
        session.close()
    return ConversationHandler.END

async def change_home_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    target = query.message if query else update.message
    if query:
        await query.answer()
    loc_btn = KeyboardButton("📍 নতুন Home Location শেয়ার করুন", request_location=True)
    markup = ReplyKeyboardMarkup([[loc_btn]], one_time_keyboard=True, resize_keyboard=True)
    await target.reply_text("নতুন Home Location শেয়ার করুন (শুধু Location):", reply_markup=markup)
    return CHANGE_HOME_WAIT

async def change_home_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    location = update.message.location
    if not location:
        await update.message.reply_text("লোকেশন শেয়ার করুন।")
        return CHANGE_HOME_WAIT

    user = update.effective_user
    session = SessionLocal()
    try:
        rider = session.query(Rider).filter_by(telegram_id=user.id).first()
        if rider:
            rider.home_lat = location.latitude
            rider.home_lon = location.longitude
            session.commit()
            await update.message.reply_text(
                f"✅ Home Location আপডেট হয়েছে।\n{location.latitude:.5f}, {location.longitude:.5f}",
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            await update.message.reply_text("রেজিস্ট্রেশন নেই।", reply_markup=ReplyKeyboardRemove())
    finally:
        session.close()
    return ConversationHandler.END

async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("বাতিল।", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END
