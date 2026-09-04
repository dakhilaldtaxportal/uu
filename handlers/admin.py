from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import SessionLocal, Rider, Vendor, get_setting, set_setting
import config

ADD_VENDOR_TG, ADD_VENDOR_NAME, ADD_VENDOR_PHONE, ADD_VENDOR_ADDRESS, ADD_VENDOR_LOC = range(20, 25)
SET_RATE_WAIT = 25
SEARCH_WAIT = 26

def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("শুধুমাত্র Admin-এর জন্য।")
        return
    text = (
        "🛠 Admin Panel\n\n"
        "/add_vendor - Vendor যোগ\n"
        "/list_vendors - Vendor লিস্ট\n"
        "/list_riders - Rider লিস্ট\n"
        "/search - সার্চ\n"
        "/set_rates - রেট সেট\n"
        "/suspend <id> - Suspend\n"
        "/unsuspend <id> - Unsuspend\n"
        "/delete_rider <id> - Rider ডিলিট\n"
        "/stats"
    )
    keyboard = [
        [InlineKeyboardButton("➕ Add Vendor", callback_data="admin_add_vendor")],
        [InlineKeyboardButton("📋 List Vendors", callback_data="admin_list_vendors")],
        [InlineKeyboardButton("👥 List Riders", callback_data="admin_list_riders")],
        [InlineKeyboardButton("⚙️ Set Rates", callback_data="admin_set_rates")],
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def add_vendor_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        if not is_admin(query.from_user.id):
            return
        await query.message.reply_text("Vendor-এর Telegram ID দিন:")
    else:
        if not is_admin(update.effective_user.id):
            return
        await update.message.reply_text("Vendor-এর Telegram ID দিন:")
    return ADD_VENDOR_TG

async def add_vendor_tg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        tg_id = int(update.message.text.strip())
    except:
        await update.message.reply_text("সঠিক Telegram ID দিন।")
        return ADD_VENDOR_TG
    context.user_data["new_vendor_tg"] = tg_id
    await update.message.reply_text("Vendor-এর নাম লিখুন:")
    return ADD_VENDOR_NAME

async def add_vendor_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text("সঠিক নাম দিন।")
        return ADD_VENDOR_NAME
    context.user_data["new_vendor_name"] = name
    await update.message.reply_text("Vendor-এর ফোন নাম্বার দিন:")
    return ADD_VENDOR_PHONE

async def add_vendor_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    context.user_data["new_vendor_phone"] = phone
    await update.message.reply_text("Vendor-এর Address (টেক্সট) লিখুন:")
    return ADD_VENDOR_ADDRESS

async def add_vendor_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    address = update.message.text.strip()
    context.user_data["new_vendor_address"] = address
    await update.message.reply_text(
        "এখন Vendor-এর Current Location শেয়ার করুন\n"
        "অথবা lat,lon লিখুন (উদাহরণ: 23.8103,90.4125):"
    )
    return ADD_VENDOR_LOC

async def add_vendor_loc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lat = lon = None
    if update.message.location:
        lat = update.message.location.latitude
        lon = update.message.location.longitude
    else:
        try:
            parts = update.message.text.strip().replace(" ", "").split(",")
            lat, lon = float(parts[0]), float(parts[1])
        except:
            await update.message.reply_text("লোকেশন শেয়ার করুন অথবা lat,lon লিখুন।")
            return ADD_VENDOR_LOC

    tg_id = context.user_data.get("new_vendor_tg")
    name = context.user_data.get("new_vendor_name")
    phone = context.user_data.get("new_vendor_phone")
    address = context.user_data.get("new_vendor_address")

    session = SessionLocal()
    try:
        existing = session.query(Vendor).filter_by(telegram_id=tg_id).first()
        if existing:
            existing.name = name
            existing.phone = phone
            existing.address = address
            existing.lat = lat
            existing.lon = lon
            existing.added_by = update.effective_user.id
            msg = "Vendor আপডেট হয়েছে।"
        else:
            v = Vendor(
                telegram_id=tg_id, name=name, phone=phone, address=address,
                lat=lat, lon=lon, added_by=update.effective_user.id
            )
            session.add(v)
            msg = "Vendor সফলভাবে যোগ হয়েছে।"
        session.commit()
        await update.message.reply_text(
            f"✅ {msg}\nনাম: {name}\nPhone: {phone}\nAddress: {address}\nLoc: {lat:.5f},{lon:.5f}"
        )
    finally:
        session.close()
    context.user_data.clear()
    return ConversationHandler.END

async def list_vendors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id
    if not is_admin(user_id):
        return
    session = SessionLocal()
    try:
        vendors = session.query(Vendor).all()
        if not vendors:
            text = "কোনো Vendor নেই।"
        else:
            lines = []
            for v in vendors:
                status = "🚫" if v.is_suspended else "✅"
                lines.append(f"{status} ID:{v.id} | {v.name} | {v.phone} | {v.address or '-'} | TG:{v.telegram_id}")
            text = "📋 Vendors:\n\n" + "\n".join(lines)
    finally:
        session.close()
    if query:
        await query.answer()
        await query.message.reply_text(text)
    else:
        await update.message.reply_text(text)

async def list_riders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id
    if not is_admin(user_id):
        return
    session = SessionLocal()
    try:
        riders = session.query(Rider).all()
        if not riders:
            text = "কোনো Rider নেই।"
        else:
            lines = []
            for r in riders:
                status = "🟢" if r.is_online else "🔴"
                sus = "🚫" if r.is_suspended else ""
                busy = "Busy" if r.is_busy else ""
                lines.append(f"{status}{sus} {r.name} | {r.phone} | TG:{r.telegram_id} | R:{r.range_km} {busy}")
            text = "👥 Riders:\n\n" + "\n".join(lines)
    finally:
        session.close()
    if query:
        await query.answer()
        await query.message.reply_text(text)
    else:
        await update.message.reply_text(text)

async def set_rates_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        if not is_admin(query.from_user.id):
            return
        msg = query.message
    else:
        if not is_admin(update.effective_user.id):
            return
        msg = update.message
    base_km = get_setting("base_km", "3")
    base_price = get_setting("base_price", "50")
    extra = get_setting("extra_per_km", "20")
    bcast = get_setting("broadcast_per_km", "15")
    text = (
        f"বর্তমান রেট:\nBase: {base_km} km → {base_price} টাকা\n"
        f"Extra: {extra} টাকা/km\nBroadcast extra: {bcast} টাকা/km\n\n"
        "নতুন রেট: `base_km,base_price,extra_per_km,broadcast_per_km`\n"
        "উদাহরণ: `3,50,20,15`"
    )
    await msg.reply_text(text, parse_mode="Markdown")
    return SET_RATE_WAIT

async def set_rates_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    try:
        parts = [p.strip() for p in update.message.text.split(",")]
        set_setting("base_km", parts[0])
        set_setting("base_price", parts[1])
        set_setting("extra_per_km", parts[2])
        set_setting("broadcast_per_km", parts[3])
        await update.message.reply_text("✅ রেট আপডেট হয়েছে।")
    except:
        await update.message.reply_text("সঠিক ফরম্যাট দিন।")
        return SET_RATE_WAIT
    return ConversationHandler.END

async def search_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("ফোন বা Telegram ID দিন:")
    return SEARCH_WAIT

async def search_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    q = update.message.text.strip()
    session = SessionLocal()
    try:
        lines = []
        if q.isdigit():
            tid = int(q)
            riders = session.query(Rider).filter_by(telegram_id=tid).all()
            vendors = session.query(Vendor).filter_by(telegram_id=tid).all()
        else:
            riders = session.query(Rider).filter(Rider.phone.contains(q)).all()
            vendors = session.query(Vendor).filter(Vendor.phone.contains(q)).all()
        for r in riders:
            lines.append(f"[Rider] {r.name} | {r.phone} | TG:{r.telegram_id} | Online:{r.is_online} | Sus:{r.is_suspended}")
        for v in vendors:
            lines.append(f"[Vendor] {v.name} | {v.phone} | {v.address} | TG:{v.telegram_id} | Sus:{v.is_suspended}")
        await update.message.reply_text("\n".join(lines) if lines else "কিছু পাওয়া যায়নি।")
    finally:
        session.close()
    return ConversationHandler.END

async def suspend_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if not args:
        await update.message.reply_text("ব্যবহার: /suspend <telegram_id>")
        return
    try:
        tg_id = int(args[0])
    except:
        await update.message.reply_text("সঠিক id দিন।")
        return
    session = SessionLocal()
    try:
        rider = session.query(Rider).filter_by(telegram_id=tg_id).first()
        vendor = session.query(Vendor).filter_by(telegram_id=tg_id).first()
        if rider:
            rider.is_suspended = True
            rider.is_online = False
            session.commit()
            await update.message.reply_text(f"Rider {tg_id} suspended।")
        elif vendor:
            vendor.is_suspended = True
            session.commit()
            await update.message.reply_text(f"Vendor {tg_id} suspended।")
        else:
            await update.message.reply_text("পাওয়া যায়নি।")
    finally:
        session.close()

async def unsuspend_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if not args:
        await update.message.reply_text("ব্যবহার: /unsuspend <telegram_id>")
        return
    try:
        tg_id = int(args[0])
    except:
        await update.message.reply_text("সঠিক id দিন।")
        return
    session = SessionLocal()
    try:
        rider = session.query(Rider).filter_by(telegram_id=tg_id).first()
        vendor = session.query(Vendor).filter_by(telegram_id=tg_id).first()
        if rider:
            rider.is_suspended = False
            session.commit()
            await update.message.reply_text(f"Rider {tg_id} unsuspended।")
        elif vendor:
            vendor.is_suspended = False
            session.commit()
            await update.message.reply_text(f"Vendor {tg_id} unsuspended।")
        else:
            await update.message.reply_text("পাওয়া যায়নি।")
    finally:
        session.close()

async def delete_rider(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if not args:
        await update.message.reply_text("ব্যবহার: /delete_rider <telegram_id>")
        return
    try:
        tg_id = int(args[0])
    except:
        await update.message.reply_text("সঠিক id দিন।")
        return
    session = SessionLocal()
    try:
        rider = session.query(Rider).filter_by(telegram_id=tg_id).first()
        if rider:
            session.delete(rider)
            session.commit()
            await update.message.reply_text(f"Rider {tg_id} ডিলিট করা হয়েছে।")
        else:
            await update.message.reply_text("Rider পাওয়া যায়নি।")
    finally:
        session.close()

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    session = SessionLocal()
    try:
        from database import Order
        text = (
            f"📊 Stats\n"
            f"Riders: {session.query(Rider).count()} (Online: {session.query(Rider).filter_by(is_online=True).count()})\n"
            f"Vendors: {session.query(Vendor).count()}\n"
            f"Orders: {session.query(Order).count()}"
        )
        await update.message.reply_text(text)
    finally:
        session.close()

async def cancel_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("বাতিল।")
    return ConversationHandler.END
