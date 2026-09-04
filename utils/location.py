import re
import logging
from typing import Optional, Tuple
import httpx

logger = logging.getLogger(__name__)

def _safe_float(value):
    try:
        v = float(value)
        if -180 <= v <= 180:
            return v
    except (ValueError, TypeError):
        pass
    return None

def _is_valid_coord(lat: Optional[float], lon: Optional[float]) -> bool:
    """Latitude এবং Longitude বৈধ সীমার মধ্যে আছে কিনা তা যাচাই করে।"""
    if lat is not None and lon is not None:
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return True
    return False

async def extract_lat_lon_from_text(text: str) -> Optional[Tuple[float, float]]:
    if not text:
        return None

    text = text.strip()

    # Regex patterns for coordinates
    patterns = [
        r"@(-?\d+\.\d+),(-?\d+\.\d+)",
        r"[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)",
        r"[?&]ll=(-?\d+\.\d+),(-?\d+\.\d+)",
        r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)",
        r"center=(-?\d+\.\d+)%2C(-?\d+\.\d+)",
        r"destination=(-?\d+\.\d+)%2C(-?\d+\.\d+)",
        r"(-?\d{1,2}\.\d{3,}),\s*(-?\d{1,3}\.\d{3,})",
    ]

    # ---------- ১. সরাসরি ইনপুট টেক্সটে Coordinates খোঁজা ----------
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            lat = _safe_float(m.group(1))
            lon = _safe_float(m.group(2))
            if _is_valid_coord(lat, lon):
                return lat, lon

    # ---------- ২. টেক্সট থেকে যেকোনো URL এক্সট্র্যাক্ট করা ----------
    # নির্দিষ্ট ডোমেইনে সীমাবদ্ধ না রেখে যেকোনো লিঙ্ক বের করা হবে যাতে শর্ট লিঙ্ক মিস না হয়
    url_match = re.search(r"https?://[^\s]+", text)
    if not url_match:
        return None

    # বিশেষ কিছু ট্রেইলিং ক্যারেক্টার থাকলে তা বাদ দেওয়া (যেমন: বন্ধনী বা দাড়ি/কমা)
    url = url_match.group(0).rstrip(").,]>\"'")

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
        
        # client history ট্র্যাক করার জন্য httpx.AsyncClient ব্যবহার
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0, headers=headers) as client:
            resp = await client.get(url)
            
            # ক) Redirect History-র প্রতিটি মধ্যবর্তী URL চেক করা (Google Maps redirection হ্যান্ডলিং)
            all_urls = [str(r.url) for r in resp.history] + [str(resp.url)]
            for current_url in all_urls:
                for pat in patterns:
                    m = re.search(pat, current_url)
                    if m:
                        lat = _safe_float(m.group(1))
                        lon = _safe_float(m.group(2))
                        if _is_valid_coord(lat, lon):
                            return lat, lon

            # খ) Response Body / Page HTML Source-এ Coordinates খোঁজা
            content = resp.text[:20000]  # সার্চ স্পেস ২০০০০ ক্যারেক্টার পর্যন্ত বাড়ানো হয়েছে
            for pat in patterns:
                m = re.search(pat, content)
                if m:
                    lat = _safe_float(m.group(1))
                    lon = _safe_float(m.group(2))
                    if _is_valid_coord(lat, lon):
                        return lat, lon

            # গ) Meta tag / Canonical URL থেকে অনুসন্ধান
            meta_match = re.search(r'content="https://maps\.google\.com/maps/api/staticmap\?center=(-?\d+\.\d+)%2C(-?\d+\.\d+)', content)
            if meta_match:
                lat = _safe_float(meta_match.group(1))
                lon = _safe_float(meta_match.group(2))
                if _is_valid_coord(lat, lon):
                    return lat, lon

    except Exception as e:
        logger.warning(f"Failed to resolve map link '{url}': {e}")

    return None
