# Food Delivery Rider Bot (Corrected Logic)

## মূল লজিক (সঠিক)

### Rider Range
- Rider তার **Home Location** থেকে কত কিমি পর্যন্ত কাজ করবে সেট করে (`/range`)
- অর্ডার পাওয়ার আগে চেক হয়:
  - Vendor লোকেশন কি Rider-এর Home Range-এর ভিতরে?
  - Customer লোকেশন কি Rider-এর Home Range-এর ভিতরে?
- দুটোই হ্যাঁ হলে তবেই অর্ডার যেতে পারে।

### Normal Order (১ কিমি)
- শুধু Vendor থেকে **১ কিমি** এর মধ্যে Live Location থাকা Riderদের খোঁজা হয়
- তাদের মধ্যে একজন একজন করে (nearest first) অর্ডার পাঠানো হয়
- Reject বা Timeout হলে পরের Rider-এর কাছে যায়
- কেউ না থাকলে অর্ডার **WAITING** থাকে → পরে কোনো Rider ১ কিমি-এর মধ্যে এলে অটো অফার যায়

### Broadcast (৫ কিমি)
- একই লজিক, শুধু রেডিয়াস ৫ কিমি + Vendor Rider-কে extra টাকা দেয়

### Live Location
- Rider ম্যানুয়ালি Live Location শেয়ার করে
- Complete-এর পর আবার Go Online করতে হয় না (যতক্ষণ Live Location অন থাকে)

### Vendor Add
- Telegram ID + নাম + ফোন + **Address (টেক্সট)** + Location

### Rider-এর কাছে অর্ডার এলে দেখায়
- Vendor নাম, ফোন, Address
- Vendor Location (Google Maps লিংক)
- Customer Location (Google Maps লিংক)
- Delivery Charge
- (Broadcast হলে) Extra টাকা

### Admin Commands
- `/delete_rider <telegram_id>` → Rider রেকর্ড ডিলিট

---

## Deploy (Render)

1. Environment Variables:
   - `BOT_TOKEN`
   - `ADMIN_IDS` (তোমার Telegram ID)
   - `DATABASE_URL` (Render Postgres link করলে অটো আসে)

2. `runtime.txt` → python-3.12.7
3. Start Command → `python main.py`
4. UptimeRobot দিয়ে `/ping` পিং করো
