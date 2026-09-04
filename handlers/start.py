from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from database import SessionLocal, Rider, Vendor
import config

REG_NAME, REG_LOCATION = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    session = SessionLocal()
    try:
        # 1. Admin
        if user.id in config.ADMIN_IDS:
            from handlers.admin import admin_panel
            await admin_panel(update, context)
            return ConversationHandler.END

        # 2. Vendor (higher priority than Rider)
        vendor = session.query(Vendor).filter_by(telegram_id=user.id, is_suspended=False).first()
        if vendor:
            from handlers.vendor import vendor_menu
            await vendor_menu(update, context)
            return ConversationHandler.END

        # 3. Rider
        rider = session.query(Rider).filter_by(telegram_id=user.id).first()
        if rider and rider.name and rider.home_lat is not None:
            if rider.is_suspended:
                await update.message.reply_text("আপনার Rider অ্যাকাউন্ট Suspended আছে। Admin-এর সাথে যোগাযোগ করুন।")
                return ConversationHandler.END

            text = (
                f"স্বাগতম {rider.name}!\n\n"
                f"স্ট্যাটাস: {'🟢 Online' if rider.is_online else '🔴 Offline'}\n"
                f"Busy: {'হ্যাঁ' if rider.is_busy else 'না'}\n"
                f"Range: {rider.range_km} km\n\n"
                "কমান্ডসমূহ:\n"
                "/go_online - Online হোন (Live Location শেয়ার করুন)\n"
                "/go_offline - Offline হোন\n"
                "/range - ডেলিভারি রেঞ্জ সেট করুন\n"
                "/change_home_address - হোম লোকেশন পরিবর্তন\n"
                "/myinfo - নিজের তথ্য দেখুন"
            )
            keyboard = [
                [
                    InlineKeyboardButton("🟢 Go Online", callback_data="rider_go_online"),
                    InlineKeyboardButton("🔴 Go Offline", callback_data="rider_go_offline"),
                ],
                [
                    InlineKeyboardButton("📏 Set Range", callback_data="rider_set_range"),
                    InlineKeyboardButton("🏠 Change Home", callback_data="rider_change_home"),
                ],
            ]
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return ConversationHandler.END

        # 4. New registration
        text = (
            "স্বাগতম Food Delivery Rider Bot-এ!\n\n"
            "Rider হিসেবে রেজিস্ট্রেশন করতে নিচের বাটনে ক্লিক করে ফোন নাম্বার শেয়ার করুন।\n"
            "অথবা /registration লিখুন।"
        )
        contact_btn = KeyboardButton("📱 আমার ফোন নাম্বার শেয়ার করুন", request_contact=True)
        markup = ReplyKeyboardMarkup([[contact_btn]], one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text(text, reply_markup=markup)
        return REG_NAME
    finally:
        session.close()

async def registration_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    session = SessionLocal()
    try:
        rider = session.query(Rider).filter_by(telegram_id=user.id).first()
        if not rider:
            session.add(Rider(telegram_id=user.id))
            session.commit()
    finally:
        session.close()

    contact_btn = KeyboardButton("📱 আমার ফোন নাম্বার শেয়ার করুন", request_contact=True)
    markup = ReplyKeyboardMarkup([[contact_btn]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("রেজিস্ট্রেশন শুরু। প্রথমে ফোন নাম্বার শেয়ার করুন:", reply_markup=markup)
    return REG_NAME

async def reg_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    user = update.effective_user
    phone = contact.phone_number if (contact and contact.user_id == user.id) else (update.message.text or "unknown")

    session = SessionLocal()
    try:
        rider = session.query(Rider).filter_by(telegram_id=user.id).first()
        if not rider:
            rider = Rider(telegram_id=user.id, phone=phone)
            session.add(rider)
        else:
            rider.phone = phone
        session.commit()
    finally:
        session.close()

    await update.message.reply_text(f"ফোন সেভ হয়েছে: {phone}\n\nএখন আপনার নাম লিখুন:", reply_markup=ReplyKeyboardRemove())
    return REG_NAME

async def reg_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = (update.message.text or "").strip()
    if len(name) < 2:
        await update.message.reply_text("সঠিক নাম লিখুন (কমপক্ষে ২ অক্ষর):")
        return REG_NAME

    user = update.effective_user
    session = SessionLocal()
    try:
        rider = session.query(Rider).filter_by(telegram_id=user.id).first()
        if rider:
            rider.name = name
            session.commit()
    finally:
        session.close()

    loc_btn = KeyboardButton("📍 আমার Current Location শেয়ার করুন", request_location=True)
    markup = ReplyKeyboardMarkup([[loc_btn]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(
        "নাম সেভ হয়েছে।\n\nএখন **Home Address** হিসেবে Current Location শেয়ার করুন।\nশুধু Location Share করুন, টাইপ করবেন না।",
        reply_markup=markup, parse_mode="Markdown"
    )
    return REG_LOCATION

async def reg_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    location = update.message.location
    if not location:
        await update.message.reply_text("লোকেশন শেয়ার করুন (বাটন ব্যবহার করে)।")
        return REG_LOCATION

    user = update.effective_user
    session = SessionLocal()
    try:
        rider = session.query(Rider).filter_by(telegram_id=user.id).first()
        if rider:
            rider.home_lat = location.latitude
            rider.home_lon = location.longitude
            rider.current_lat = location.latitude
            rider.current_lon = location.longitude
            session.commit()
    finally:
        session.close()

    await update.message.reply_text(
        "✅ রেজিস্ট্রেশন সম্পন্ন!\n\nএখন /go_online দিয়ে Live Location শেয়ার করে Online হোন।",
        reply_markup=ReplyKeyboardRemove()
    )
    keyboard = [[
        InlineKeyboardButton("🟢 Go Online", callback_data="rider_go_online"),
        InlineKeyboardButton("📏 Set Range", callback_data="rider_set_range"),
    ]]
    await update.message.reply_text("মেনু:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

async def cancel_reg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("রেজিস্ট্রেশন বাতিল।", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END
