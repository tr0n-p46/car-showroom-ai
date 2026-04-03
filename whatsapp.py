import json
import os
import re
from twilio.rest import Client

_client = None


def _get_client() -> Client | None:
    global _client
    if _client is not None:
        return _client
    sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    if not sid or not token:
        return None
    _client = Client(sid, token)
    return _client


def _from_number() -> str:
    return os.getenv("TWILIO_WHATSAPP_FROM", "").strip()


_DIGITS_RE = re.compile(r"\d+")


def normalize_phone(raw: str) -> str | None:
    """
    Normalize a phone number to WhatsApp E.164 format.
    Handles Indian numbers (default), US/international numbers with + prefix.

    Examples:
      '9876543210'        → 'whatsapp:+919876543210'   (Indian, 10-digit)
      '+919876543210'     → 'whatsapp:+919876543210'   (explicit E.164)
      '+14155238886'      → 'whatsapp:+14155238886'    (US with +)
      '09876543210'       → 'whatsapp:+919876543210'   (Indian, 0-prefix)
      '91 98765 43210'    → 'whatsapp:+919876543210'   (Indian, spaced)
    """
    if not raw:
        return None
    raw_str = str(raw).strip()
    digits = "".join(_DIGITS_RE.findall(raw_str))
    if not digits or len(digits) < 7:
        return None

    # If the caller passed an explicit + prefix, trust the full E.164 number.
    if raw_str.startswith("+"):
        return f"whatsapp:+{digits}"

    # Indian heuristics for bare numbers without country code.
    if len(digits) == 10:
        digits = "91" + digits
    elif len(digits) == 11 and digits.startswith("0"):
        digits = "91" + digits[1:]
    elif len(digits) == 12 and digits.startswith("91"):
        pass
    # 11-digit US (1XXXXXXXXXX without +)
    elif len(digits) == 11 and digits.startswith("1"):
        pass

    return f"whatsapp:+{digits}"


def _format_price_inr(price) -> str:
    try:
        p = int(price)
    except (TypeError, ValueError):
        return str(price)
    if p >= 10_000_000:
        return f"\u20b9{p / 10_000_000:.2f} Cr"
    if p >= 100_000:
        return f"\u20b9{p / 100_000:.1f} Lakh"
    return f"\u20b9{p:,}"


def _format_car_card(car: dict) -> str:
    make = car.get("make", "")
    model = car.get("model", "")
    year = car.get("year", "")
    title = f"{year} {make} {model}".strip()

    lines = [f"*{title}*"]
    parts = []
    if car.get("kms_driven") is not None:
        parts.append(f"KMs: {int(car['kms_driven']):,}")
    if car.get("fuel_type"):
        parts.append(car["fuel_type"])
    if car.get("transmission"):
        parts.append(car["transmission"])
    if parts:
        lines.append(" | ".join(parts))
    if car.get("price") is not None:
        price_str = _format_price_inr(car["price"])
        owners = car.get("owners")
        if owners is not None:
            lines.append(f"Price: {price_str} | Owners: {owners}")
        else:
            lines.append(f"Price: {price_str}")
    if car.get("car_number"):
        lines.append(f"Reg: {car['car_number']}")
    return "\n".join(lines)


def send_text(to_phone: str, body: str) -> dict:
    """Send a plain text WhatsApp message. Returns status dict."""
    client = _get_client()
    if not client:
        return {"ok": False, "error": "Twilio not configured (missing TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN)"}
    from_num = _from_number()
    if not from_num:
        return {"ok": False, "error": "TWILIO_WHATSAPP_FROM not set"}
    to = normalize_phone(to_phone)
    if not to:
        return {"ok": False, "error": f"Could not parse phone number: {to_phone}"}
    try:
        msg = client.messages.create(from_=from_num, to=to, body=body)
        return {"ok": True, "sid": msg.sid, "status": msg.status}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def send_media(to_phone: str, body: str, media_urls: list[str]) -> dict:
    """Send a WhatsApp message with media (images)."""
    client = _get_client()
    if not client:
        return {"ok": False, "error": "Twilio not configured"}
    from_num = _from_number()
    if not from_num:
        return {"ok": False, "error": "TWILIO_WHATSAPP_FROM not set"}
    to = normalize_phone(to_phone)
    if not to:
        return {"ok": False, "error": f"Could not parse phone number: {to_phone}"}
    urls = [u for u in media_urls if u and str(u).startswith("http")]
    try:
        msg = client.messages.create(
            from_=from_num, to=to, body=body,
            media_url=urls if urls else None,
        )
        return {"ok": True, "sid": msg.sid, "status": msg.status}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _extract_urls(raw) -> list[str]:
    """Parse image URLs from various formats: JSON array string, plain URL, or list."""
    if not raw:
        return []
    if isinstance(raw, list):
        return [u for u in raw if isinstance(u, str) and u.startswith("http")]
    if isinstance(raw, str):
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [u for u in parsed if isinstance(u, str) and u.startswith("http")]
            except (json.JSONDecodeError, TypeError):
                pass
        if raw.startswith("http"):
            return [raw]
    return []


def send_car_details(to_phone: str, cars: list[dict], dealer_name: str = "") -> dict:
    """
    Format a list of inventory dicts into a WhatsApp message and send.
    If any car has a photo URL, sends as media message.
    """
    if not cars:
        return {"ok": False, "error": "No cars to send"}

    header = f"Here are the cars from {dealer_name}:" if dealer_name else "Here are the cars we discussed:"
    cards = [_format_car_card(c) for c in cars[:5]]
    body = header + "\n\n" + "\n\n".join(cards)
    if dealer_name:
        body += f"\n\nVisit us at {dealer_name}!"

    photo_urls = []
    for c in cars[:5]:
        raw = c.get("image_url") or c.get("photo_url") or c.get("photos")
        urls = _extract_urls(raw)
        photo_urls.extend(urls)

    if photo_urls:
        return send_media(to_phone, body, photo_urls[:10])
    return send_text(to_phone, body)


def send_test_drive_confirmation(
    to_phone: str,
    car: dict,
    date: str,
    time: str,
    customer_name: str = "",
    dealer_name: str = "",
    address: str = "",
) -> dict:
    """Send a test drive booking confirmation via WhatsApp."""
    make = car.get("make", "")
    model = car.get("model", "")
    year = car.get("year", "")
    car_title = f"{year} {make} {model}".strip() or "your selected car"

    greeting = f"Hi {customer_name}! " if customer_name else ""
    lines = [
        f"{greeting}Your test drive is confirmed!",
        "",
        f"Car: *{car_title}*",
        f"Date: {date}",
        f"Time: {time}",
    ]
    if dealer_name:
        lines.append(f"At: {dealer_name}")
    if address:
        lines.append(f"Address: {address}")
    lines.append("")
    lines.append("Looking forward to seeing you!")

    return send_text(to_phone, "\n".join(lines))
