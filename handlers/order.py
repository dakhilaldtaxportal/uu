import logging
from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import (
    SessionLocal, Rider, Vendor, Order, OrderType, OrderStatus, get_setting
)
from utils.distance import get_road_distance_km, calculate_delivery_charge, calculate_broadcast_extra
from utils.location import extract_lat_lon_from_text
import config

logger = logging.getLogger(__name__)

# order_id -> (chat_id, message_id) of the current offer
current_offer_msg = {}

def _get_tried_ids(order: Order) -> set:
    if not order.tried_rider_ids:
        return set()
    return set(int(x) for x in order.tried_rider_ids.split(",") if x.strip().isdigit())

def _add_tried(order: Order, rider_id: int):
    tried = _get_tried_ids(order)
    tried.add(rider_id)
    order.tried_rider_ids = ",".join(str(x) for x in tried)

async def _find_eligible_riders(session, vendor, customer_lat, customer_lon, radius_km, exclude_ids: set):
    """Return list of (rider, dist_vr) sorted by distance, that pass all checks."""
    riders = session.query(Rider).filter(
        Rider.is_online == True,
        Rider.is_suspended == False,
        Rider.is_busy == False,
        Rider.home_lat.isnot(None),
        Rider.current_lat.isnot(None),
        Rider.id.notin_(exclude_ids) if exclude_ids else True
    ).all()

    eligible = []
    now = datetime.now(timezone.utc)
    for r in riders:
        # live location freshness
        if r.last_location_update:
            last = r.last_location_update
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if (now - last).total_seconds() > config.LIVE_LOCATION_TIMEOUT:
                r.is_online = False
                continue

        # 1. Rider live location within radius of vendor
        dist_vr = await get_road_distance_km(vendor.lat, vendor.lon, r.current_lat, r.current_lon)
        if dist_vr > radius_km:
            continue

        # 2. Vendor within rider's home range
        dist_home_v = await get_road_distance_km(r.home_lat, r.home_lon, vendor.lat, vendor.lon)
        if dist_home_v > r.range_km:
            continue

        # 3. Customer within rider's home range
        dist_home_c = await get_road_distance_km(r.home_lat, r.home_lon, customer_lat, customer_lon)
        if dist_home_c > r.range_km:
            continue

        eligible.append((r, dist_vr))

    eligible.sort(key=lambda x: x[1])
    return eligible

def _make_maps_link(lat, lon):
    return f"https://www.google.com/maps?q={lat},{lon}"

async def _send_offer_to_rider(context, order, vendor, rider, dist_vr, broadcast_extra):
    """Send order offer to one rider. Returns True if sent successfully."""
    customer_link = _make_maps_link(order.customer_lat, order.customer_lon)
    vendor_link = _make_maps_link(vendor.lat, vendor.lon)

    text = (
        f"📦 নতুন অর্ডার #{order.id}\n"
        f"Type: {'📢 Broadcast' if order.order_type == OrderType.BROADCAST else '📦 Normal'}\n\n"
        f"{order.order_text[:400]}\n\n"
        f"🏪 Vendor: {vendor.name}\n"
        f"📞 Phone: {vendor.phone}\n"
        f"📍 Address: {vendor.address or '-'}\n"
        f"📌 Vendor Location: {vendor_link}\n"
        f"📌 Customer Location: {customer_link}\n\n"
        f"📏 Vendor থেকে আপনার দূরত্ব: {dist_vr:.2f} km\n"
        f"💰 Delivery Charge: {order.delivery_charge} টাকা\n"
    )
    if order.order_type == OrderType.BROADCAST and broadcast_extra > 0:
        text += f"💸 Broadcast Extra (Vendor দিবে): {broadcast_extra} টাকা\n"

    text += f"\n⏱ {config.ACCEPT_TIMEOUT_SECONDS} সেকেন্ডের মধ্যে Accept করুন।"

    keyboard = [[
        InlineKeyboardButton("✅ Accept", callback_data=f"order_accept_{order.id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"order_reject_{order.id}"),
    ]]
    try:
        sent = await context.bot.send_message(
            chat_id=rider.telegram_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=False
        )
        current_offer_msg[order.id] = (rider.telegram_id, sent.message_id)
        return True
    except Exception as e:
        logger.warning(f"Send offer failed to {rider.telegram_id}: {e}")
        return False

async def _offer_next_rider(context, order_id: int):
    """Try to offer the order to the next eligible rider. If none, set WAITING."""
    session = SessionLocal()
    try:
        order = session.query(Order).filter_by(id=order_id).first()
        if not order or order.status not in (OrderStatus.PENDING, OrderStatus.WAITING):
            return

        vendor = session.query(Vendor).filter_by(id=order.vendor_id).first()
        if not vendor:
            return

        radius = float(get_setting("broadcast_radius" if order.order_type == OrderType.BROADCAST else "normal_radius",
                                   str(config.BROADCAST_RADIUS_KM if order.order_type == OrderType.BROADCAST else config.NORMAL_RADIUS_KM)))

        tried = _get_tried_ids(order)
        eligible = await _find_eligible_riders(session, vendor, order.customer_lat, order.customer_lon, radius, tried)

        if not eligible:
            order.status = OrderStatus.WAITING
            session.commit()
            # notify vendor once
            try:
                await context.bot.send_message(
                    chat_id=vendor.telegram_id,
                    text=f"⏳ অর্ডার #{order.id} — এখনো উপযুক্ত Rider পাওয়া যায়নি। খুঁজতে থাকব।"
                )
            except Exception:
                pass
            return

        # take the nearest
        rider, dist_vr = eligible[0]
        broadcast_extra = 0.0
        if order.order_type == OrderType.BROADCAST:
            per_km = float(get_setting("broadcast_per_km", str(config.DEFAULT_BROADCAST_PER_KM)))
            broadcast_extra = calculate_broadcast_extra(dist_vr, per_km)

        _add_tried(order, rider.id)
        order.status = OrderStatus.PENDING
        order.expires_at = datetime.now(timezone.utc) + timedelta(seconds=config.ACCEPT_TIMEOUT_SECONDS)
        session.commit()

        sent = await _send_offer_to_rider(context, order, vendor, rider, dist_vr, broadcast_extra)
        if not sent:
            # try next immediately
            await _offer_next_rider(context, order_id)
            return

        # schedule timeout
        context.job_queue.run_once(
            order_timeout_callback,
            when=config.ACCEPT_TIMEOUT_SECONDS,
            data={"order_id": order_id},
            name=f"timeout_{order_id}"
        )
    finally:
        session.close()

async def create_and_dispatch_order(context, vendor_telegram_id: int, order_text: str, order_type: str = "normal") -> str:
    session = SessionLocal()
    try:
        vendor = session.query(Vendor).filter_by(telegram_id=vendor_telegram_id, is_suspended=False).first()
        if not vendor:
            return "❌ Vendor পাওয়া যায়নি বা Suspended।"

        extracted = await extract_lat_lon_from_text(order_text)
        if not extracted:
            return "❌ Customer-এর Google Maps link বা lat,lon পাওয়া যায়নি।"

        customer_lat, customer_lon = extracted
        dist_vc = await get_road_distance_km(vendor.lat, vendor.lon, customer_lat, customer_lon)

        base_km = float(get_setting("base_km", "3"))
        base_price = float(get_setting("base_price", "50"))
        extra_per_km = float(get_setting("extra_per_km", "20"))
        delivery_charge = calculate_delivery_charge(dist_vc, base_km, base_price, extra_per_km)

        otype = OrderType.BROADCAST if order_type == "broadcast" else OrderType.NORMAL

        order = Order(
            vendor_id=vendor.id,
            order_text=order_text,
            customer_map_link=order_text,
            customer_lat=customer_lat,
            customer_lon=customer_lon,
            order_type=otype,
            status=OrderStatus.PENDING,
            delivery_charge=delivery_charge,
            distance_vendor_customer_km=dist_vc,
            tried_rider_ids=""
        )
        session.add(order)
        session.commit()
        session.refresh(order)

        # start offering
        await _offer_next_rider(context, order.id)

        return (
            f"✅ অর্ডার #{order.id} তৈরি হয়েছে।\n"
            f"Vendor→Customer: {dist_vc:.2f} km | Charge: {delivery_charge} টাকা\n"
            f"Type: {order_type}\n"
            f"উপযুক্ত Rider খোঁজা হচ্ছে..."
        )
    except Exception as e:
        logger.exception("create_and_dispatch_order error")
        return f"❌ Error: {e}"
    finally:
        session.close()

async def order_timeout_callback(context: ContextTypes.DEFAULT_TYPE):
    order_id = context.job.data["order_id"]
    # remove current offer message
    if order_id in current_offer_msg:
        chat_id, msg_id = current_offer_msg.pop(order_id)
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id,
                text=f"⏱ অর্ডার #{order_id} এর সময় শেষ।"
            )
        except Exception:
            pass
    # try next rider
    await _offer_next_rider(context, order_id)

async def order_accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        order_id = int(query.data.split("_")[-1])
    except:
        return

    user_id = query.from_user.id
    session = SessionLocal()
    try:
        order = session.query(Order).filter_by(id=order_id).first()
        if not order or order.status != OrderStatus.PENDING:
            await query.edit_message_text("এই অর্ডার আর Available নেই।")
            return

        rider = session.query(Rider).filter_by(telegram_id=user_id).first()
        if not rider or rider.is_busy or not rider.is_online:
            await query.edit_message_text("আপনি এখন অর্ডার নিতে পারবেন না।")
            return

        vendor = session.query(Vendor).filter_by(id=order.vendor_id).first()

        order.rider_id = rider.id
        order.status = OrderStatus.ACCEPTED
        order.accepted_at = datetime.now(timezone.utc)
        rider.is_busy = True

        if order.order_type == OrderType.BROADCAST and rider.current_lat:
            dist_vr = await get_road_distance_km(vendor.lat, vendor.lon, rider.current_lat, rider.current_lon)
            per_km = float(get_setting("broadcast_per_km", "15"))
            order.broadcast_extra = calculate_broadcast_extra(dist_vr, per_km)
            order.distance_vendor_rider_km = dist_vr

        session.commit()

        # cancel timeout
        for j in context.job_queue.get_jobs_by_name(f"timeout_{order_id}"):
            j.schedule_removal()
        current_offer_msg.pop(order_id, None)

        vendor_link = _make_maps_link(vendor.lat, vendor.lon)
        customer_link = _make_maps_link(order.customer_lat, order.customer_lon)

        keyboard = [
            [InlineKeyboardButton("✅ Delivery Complete", callback_data=f"order_complete_{order_id}")],
            [InlineKeyboardButton("⚠️ Cancel / Problem", callback_data=f"order_cancel_{order_id}")],
        ]
        text = (
            f"✅ আপনি অর্ডার #{order_id} Accept করেছেন!\n\n"
            f"{order.order_text[:350]}\n\n"
            f"🏪 Vendor: {vendor.name}\n"
            f"📞 Phone: {vendor.phone}\n"
            f"📍 Address: {vendor.address or '-'}\n"
            f"📌 Vendor: {vendor_link}\n"
            f"📌 Customer: {customer_link}\n"
            f"💰 Charge: {order.delivery_charge} টাকা\n"
        )
        if order.broadcast_extra > 0:
            text += f"💸 Extra: {order.broadcast_extra} টাকা\n"
        text += "\nডেলিভারি শেষে Complete চাপুন।"

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

        try:
            await context.bot.send_message(
                chat_id=vendor.telegram_id,
                text=(
                    f"✅ অর্ডার #{order_id} Accept হয়েছে!\n"
                    f"Rider: {rider.name}\n"
                    f"📞 Rider Phone: {rider.phone}\n"
                    f"এখন কল করতে পারেন।"
                )
            )
        except Exception:
            pass
    finally:
        session.close()

async def order_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Reject করা হয়েছে")
    try:
        order_id = int(query.data.split("_")[-1])
    except:
        return
    await query.edit_message_text(f"আপনি অর্ডার #{order_id} Reject করেছেন।")
    current_offer_msg.pop(order_id, None)
    # cancel timeout and go to next
    for j in context.job_queue.get_jobs_by_name(f"timeout_{order_id}"):
        j.schedule_removal()
    await _offer_next_rider(context, order_id)

async def order_complete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        order_id = int(query.data.split("_")[-1])
    except:
        return
    user_id = query.from_user.id
    session = SessionLocal()
    try:
        order = session.query(Order).filter_by(id=order_id).first()
        if not order or order.status != OrderStatus.ACCEPTED:
            await query.edit_message_text("Complete করা যাবে না।")
            return
        rider = session.query(Rider).filter_by(telegram_id=user_id).first()
        if not rider or order.rider_id != rider.id:
            await query.edit_message_text("এই অর্ডার আপনার নয়।")
            return

        order.status = OrderStatus.COMPLETED
        order.completed_at = datetime.now(timezone.utc)
        rider.is_busy = False
        session.commit()

        await query.edit_message_text(
            f"✅ অর্ডার #{order_id} Complete হয়েছে।\n"
            f"Live Location চালু থাকলে আপনি আবার নতুন অর্ডার পেতে পারবেন।"
        )

        vendor = session.query(Vendor).filter_by(id=order.vendor_id).first()
        if vendor and vendor.telegram_id:
            try:
                await context.bot.send_message(chat_id=vendor.telegram_id, text=f"✅ অর্ডার #{order_id} Complete হয়েছে।")
            except Exception:
                pass
    finally:
        session.close()

async def order_cancel_reassign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        order_id = int(query.data.split("_")[-1])
    except:
        return
    user_id = query.from_user.id
    session = SessionLocal()
    try:
        order = session.query(Order).filter_by(id=order_id).first()
        if not order or order.status != OrderStatus.ACCEPTED:
            await query.edit_message_text("Cancel করা যাবে না।")
            return
        rider = session.query(Rider).filter_by(telegram_id=user_id).first()
        if not rider or order.rider_id != rider.id:
            await query.edit_message_text("এই অর্ডার আপনার নয়।")
            return

        rider.is_busy = False
        order.rider_id = None
        order.status = OrderStatus.PENDING
        order.accepted_at = None
        # keep tried list so same rider not immediately re-offered
        session.commit()

        await query.edit_message_text(f"⚠️ অর্ডার #{order_id} Cancel করা হয়েছে। অন্য Rider খোঁজা হচ্ছে...")

        vendor = session.query(Vendor).filter_by(id=order.vendor_id).first()
        try:
            await context.bot.send_message(chat_id=vendor.telegram_id, text=f"অর্ডার #{order_id} Rider cancel করেছে। নতুন Rider খোঁজা হচ্ছে।")
        except Exception:
            pass

        await _offer_next_rider(context, order_id)
    finally:
        session.close()

async def waiting_orders_scanner(context: ContextTypes.DEFAULT_TYPE):
    """Background job: re-check WAITING orders every 45s."""
    session = SessionLocal()
    try:
        waiting = session.query(Order).filter_by(status=OrderStatus.WAITING).all()
        for order in waiting:
            await _offer_next_rider(context, order.id)
    finally:
        session.close()
