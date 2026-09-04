import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "123456789").split(",") if x.strip().isdigit()]

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///rider_bot.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Business rules
NORMAL_RADIUS_KM = float(os.getenv("NORMAL_RADIUS_KM", "1.0"))
BROADCAST_RADIUS_KM = float(os.getenv("BROADCAST_RADIUS_KM", "5.0"))
ACCEPT_TIMEOUT_SECONDS = int(os.getenv("ACCEPT_TIMEOUT_SECONDS", "60"))

DEFAULT_BASE_KM = float(os.getenv("DEFAULT_BASE_KM", "3.0"))
DEFAULT_BASE_PRICE = float(os.getenv("DEFAULT_BASE_PRICE", "50.0"))
DEFAULT_EXTRA_PER_KM = float(os.getenv("DEFAULT_EXTRA_PER_KM", "20.0"))
DEFAULT_BROADCAST_PER_KM = float(os.getenv("DEFAULT_BROADCAST_PER_KM", "15.0"))
DEFAULT_RIDER_RANGE_KM = float(os.getenv("DEFAULT_RIDER_RANGE_KM", "10.0"))

LIVE_LOCATION_TIMEOUT = int(os.getenv("LIVE_LOCATION_TIMEOUT", "180"))

PORT = int(os.getenv("PORT", "10000"))
KEEP_ALIVE = os.getenv("KEEP_ALIVE", "true").lower() == "true"

OSRM_SERVER = os.getenv("OSRM_SERVER", "https://router.project-osrm.org")
