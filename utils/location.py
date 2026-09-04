import re
import logging
from typing import Optional, Tuple
import httpx

logger = logging.getLogger(__name__)

PATTERNS = [
    re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+)"),
    re.compile(r"[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)"),
    re.compile(r"[?&]ll=(-?\d+\.\d+),(-?\d+\.\d+)"),
    re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)"),
    re.compile(r"geo:(-?\d+\.\d+),(-?\d+\.\d+)"),
    re.compile(r"(-?\d{1,3}\.\d{4,}),\s*(-?\d{1,3}\.\d{4,})"),
    re.compile(r"center=(-?\d+\.\d+)%2C(-?\d+\.\d+)"),
    re.compile(r"destination=(-?\d+\.\d+)%2C(-?\d+\.\d+)"),
]

async def extract_lat_lon_from_text(text: str) -> Optional[Tuple[float, float]]:
    if not text:
        return None

    text = text.strip()

    # 1. সরাসরি প্যাটার্ন ম্যাচ
    for pat in PATTERNS:
        m = pat.search(text)
        if m:
            try:
                lat, lon = float(m.group(1)), float(m.group(2))
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    return lat, lon
            except ValueError:
                continue

    # 2. Short link (maps.app.goo.gl / goo.gl/maps) resolve করা
    if "maps.app.goo.gl" in text or "goo.gl/maps" in text or "maps.google.com" in text:
        # লিংকটা আলাদা করে বের করা
        url_match = re.search(r"https?://[^\s]+", text)
        if not url_match:
            return None
        url = url_match.group(0)

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            async with httpx.AsyncClient(follow_redirects=True, timeout=15.0, headers=headers) as client:
                resp = await client.get(url)
                final_url = str(resp.url)
                content = resp.text[:5000]  # কিছু অংশও সার্চ করা

                # Final URL থেকে খোঁজা
                for pat in PATTERNS:
                    m = pat.search(final_url)
                    if m:
                        lat, lon = float(m.group(1)), float(m.group(2))
                        if -90 <= lat <= 90 and -180 <= lon <= 180:
                            return lat, lon

                # Page content থেকেও খোঁজা
                for pat in PATTERNS:
                    m = pat.search(content)
                    if m:
                        lat, lon = float(m.group(1)), float(m.group(2))
                        if -90 <= lat <= 90 and -180 <= lon <= 180:
                            return lat, lon

        except Exception as e:
            logger.warning(f"Map link resolve failed: {e}")

    return None
