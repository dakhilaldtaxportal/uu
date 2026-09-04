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
]

async def extract_lat_lon_from_text(text: str) -> Optional[Tuple[float, float]]:
    if not text:
        return None
    text = text.strip()
    for pat in PATTERNS:
        m = pat.search(text)
        if m:
            try:
                lat, lon = float(m.group(1)), float(m.group(2))
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    return lat, lon
            except ValueError:
                continue
    if "maps.app.goo.gl" in text or "goo.gl/maps" in text:
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                resp = await client.get(text)
                final_url = str(resp.url)
                for pat in PATTERNS:
                    m = pat.search(final_url)
                    if m:
                        lat, lon = float(m.group(1)), float(m.group(2))
                        if -90 <= lat <= 90 and -180 <= lon <= 180:
                            return lat, lon
        except Exception as e:
            logger.warning(f"Short link resolve failed: {e}")
    return None
