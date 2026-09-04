import re
import logging
from typing import Optional, Tuple
import httpx

logger = logging.getLogger(__name__)

def _safe_float(value):
    try:
        v = float(value)
        if -90 <= v <= 90 or -180 <= v <= 180:
            return v
    except (ValueError, TypeError):
        pass
    return None

async def extract_lat_lon_from_text(text: str) -> Optional[Tuple[float, float]]:
    if not text:
        return None

    text = text.strip()

    # ---------- 1. সরাসরি lat,lon খোঁজা ----------
    patterns = [
        r"@(-?\d+\.\d+),(-?\d+\.\d+)",
        r"[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)",
        r"[?&]ll=(-?\d+\.\d+),(-?\d+\.\d+)",
        r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)",
        r"center=(-?\d+\.\d+)%2C(-?\d+\.\d+)",
        r"destination=(-?\d+\.\d+)%2C(-?\d+\.\d+)",
        r"(-?\d{1,2}\.\d{5,}),\s*(-?\d{1,3}\.\d{5,})",
    ]

    for pat in patterns:
        m = re.search(pat, text)
        if m:
            lat = _safe_float(m.group(1))
            lon = _safe_float(m.group(2))
            if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon

    # ---------- 2. Short link resolve ----------
    url_match = re.search(r"https?://(?:maps\.app\.goo\.gl|goo\.gl/maps|maps\.google\.com)[^\s]*", text)
    if not url_match:
        return None

    url = url_match.group(0)

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36"
        }
        async with httpx.AsyncClient(follow_redirects=True, timeout=12.0, headers=headers) as client:
            resp = await client.get(url)
            final_url = str(resp.url)

            for pat in patterns:
                m = re.search(pat, final_url)
                if m:
                    lat = _safe_float(m.group(1))
                    lon = _safe_float(m.group(2))
                    if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
                        return lat, lon

            # page source-এও খোঁজা
            content = resp.text[:8000]
            for pat in patterns:
                m = re.search(pat, content)
                if m:
                    lat = _safe_float(m.group(1))
                    lon = _safe_float(m.group(2))
                    if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
                        return lat, lon

    except Exception as e:
        logger.warning(f"Failed to resolve map link: {e}")

    return None
