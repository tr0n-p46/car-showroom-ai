from database import supabase

def _parse_budget_to_inr(value):
    """
    Accepts numbers or strings like:
    - "15L", "15 lakh", "15 lakhs", "15,00,000"
    - "1.2cr", "1.2 crore"
    Returns an int INR amount, or None if not parseable.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str):
        return None

    s = value.strip().lower().replace(",", "").replace("₹", "").replace("rs.", "").replace("rs", "")
    if not s:
        return None

    mult = 1
    if "crore" in s or s.endswith("cr") or s.endswith("crores"):
        mult = 10_000_000
        s = s.replace("crores", "").replace("crore", "").replace("cr", "")
    elif "lakh" in s or "lac" in s or s.endswith("l"):
        mult = 100_000
        s = s.replace("lakhs", "").replace("lakh", "").replace("lacs", "").replace("lac", "")
        if s.endswith("l"):
            s = s[:-1]

    s = s.strip()
    try:
        return int(float(s) * mult)
    except ValueError:
        return None

def _parse_int(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        s = value.strip().replace(",", "")
        if not s:
            return None
        try:
            return int(float(s))
        except ValueError:
            return None
    return None


def _norm_transmission(value: str | None):
    if not value:
        return None
    v = str(value).strip().lower()
    if v in {"at", "automatic", "auto"}:
        return "AT"
    if v in {"mt", "manual"}:
        return "Manual"
    return None


def _norm_fuel(value: str | None):
    if not value:
        return None
    v = str(value).strip().lower()
    if v in {"ev", "electric"}:
        return "Electric"
    if v in {"petrol", "gasoline"}:
        return "Petrol"
    if v in {"diesel"}:
        return "Diesel"
    if v in {"cng"}:
        return "CNG"
    return str(value).strip().title()


def search_cars(
    *,
    # Back-compat
    budget=None,
    model: str | None = None,
    fuel_type: str | None = None,
    # New filters
    make: str | None = None,
    brand: str | None = None,
    q: str | None = None,  # generic search term
    price_min=None,
    price_max=None,
    kms_min=None,
    kms_max=None,
    transmission: str | None = None,
    owners=None,
    owners_min=None,
    owners_max=None,
    reg_prefix: str | None = None,
    status: str | None = "available",
    limit: int | None = 10,
):
    _VOICE_COLUMNS = "id,make,model,year,price,kms_driven,fuel_type,transmission,owners,status"
    query = supabase.table("inventory").select(_VOICE_COLUMNS)

    if status:
        query = query.eq("status", str(status).strip().lower())
    
    # Budget is treated as price_max (<=)
    if budget is not None and price_max is None:
        price_max = budget

    price_min_inr = _parse_budget_to_inr(price_min)
    price_max_inr = _parse_budget_to_inr(price_max)
    if price_min_inr is not None:
        query = query.gte("price", price_min_inr)
    if price_max_inr is not None:
        query = query.lte("price", price_max_inr)

    kms_min_i = _parse_int(kms_min)
    kms_max_i = _parse_int(kms_max)
    if kms_min_i is not None:
        query = query.gte("kms_driven", kms_min_i)
    if kms_max_i is not None:
        query = query.lte("kms_driven", kms_max_i)

    owners_i = _parse_int(owners)
    owners_min_i = _parse_int(owners_min)
    owners_max_i = _parse_int(owners_max)
    if owners_i is not None:
        query = query.eq("owners", owners_i)
    else:
        if owners_min_i is not None:
            query = query.gte("owners", owners_min_i)
        if owners_max_i is not None:
            query = query.lte("owners", owners_max_i)

    fuel = _norm_fuel(fuel_type)
    if fuel:
        query = query.eq("fuel_type", fuel)

    trans = _norm_transmission(transmission)
    if trans:
        query = query.eq("transmission", trans)

    make_term = (brand or make or "").strip()
    model_term = (model or "").strip()
    q_term = (q or "").strip()

    # Free-text search across make/model; if you need more columns, add here.
    terms = [t for t in {make_term, model_term, q_term} if t]
    if terms:
        ors = []
        for t in terms:
            ors.append(f"make.ilike.%{t}%")
            ors.append(f"model.ilike.%{t}%")
        query = query.or_(",".join(ors))

    # Registration prefix (requires a column; configurable to avoid guessing wrong schema)
    if reg_prefix:
        prefix = str(reg_prefix).strip()
        if prefix:
            # Use env-configured columns if present
            import os as _os
            cols = [c.strip() for c in _os.getenv("INVENTORY_REG_COLUMNS", "car_number").split(",") if c.strip()]
            if cols:
                ors = ",".join([f"{c}.ilike.{prefix}%" for c in cols])
                query = query.or_(ors)

    if limit:
        query = query.limit(int(limit))
        
    res = query.execute()
    return res.data if res.data else "No cars found matching those criteria."

def create_lead(phone, intent, summary):
    data = {
        "phone_number": phone,
        "intent": intent,
        "requirement_summary": summary
    }
    res = supabase.table("leads").insert(data).execute()
    return "Lead recorded successfully. Tell the user a representative will contact them soon."


def send_car_details_whatsapp(
    *,
    phone: str,
    budget=None,
    model: str | None = None,
    fuel_type: str | None = None,
    make: str | None = None,
    brand: str | None = None,
    q: str | None = None,
    price_min=None,
    price_max=None,
    transmission: str | None = None,
    limit: int | None = 5,
):
    """
    Search inventory with the given filters and send matching cars
    to the customer's WhatsApp number.
    """
    import whatsapp

    if not phone:
        return "Cannot send WhatsApp: no phone number provided. Ask the customer for their WhatsApp number."

    cars = search_cars(
        budget=budget,
        model=model,
        fuel_type=fuel_type,
        make=make,
        brand=brand,
        q=q,
        price_min=price_min,
        price_max=price_max,
        transmission=transmission,
        limit=limit,
    )

    if isinstance(cars, str):
        return f"No matching cars found to send. {cars}"

    # Re-fetch matched car IDs with image_url for WhatsApp media
    car_ids = [c["id"] for c in cars if c.get("id")]
    if car_ids:
        img_rows = supabase.table("inventory").select("id,image_url").in_("id", car_ids).execute().data or []
        img_map = {r["id"]: r.get("image_url") for r in img_rows}
        for c in cars:
            c["image_url"] = img_map.get(c.get("id"))

    import os
    dealer_name = os.getenv("DEALER_NAME", "")
    result = whatsapp.send_car_details(phone, cars, dealer_name=dealer_name)

    if result.get("ok"):
        count = min(len(cars), 5)
        return f"Sent {count} car option(s) to WhatsApp number {phone}. Tell the customer to check their WhatsApp."
    return f"Could not send WhatsApp message: {result.get('error', 'unknown error')}. Apologize and offer to share details verbally instead."


def book_test_drive(
    *,
    phone: str,
    customer_name: str = "",
    car_make: str = "",
    car_model: str = "",
    date: str = "",
    time: str = "",
):
    """
    Book a test drive: store in DB and send WhatsApp confirmation.
    """
    import whatsapp, os

    if not phone:
        return "Cannot book test drive: no phone number. Ask the customer for their number."
    if not date:
        return "Cannot book test drive: no date provided. Ask the customer when they'd like to come."

    car_search = search_cars(make=car_make, model=car_model, limit=1)
    car = {}
    if isinstance(car_search, list) and car_search:
        car = car_search[0]
    else:
        car = {"make": car_make, "model": car_model}

    booking = {
        "phone_number": phone,
        "customer_name": customer_name or "",
        "car_make": car.get("make", car_make),
        "car_model": car.get("model", car_model),
        "preferred_date": date,
        "preferred_time": time or "To be confirmed",
        "status": "booked",
    }

    try:
        supabase.table("test_drive_bookings").insert(booking).execute()
    except Exception as e:
        print(f"Warning: could not save test drive booking to DB: {e}")

    dealer_name = os.getenv("DEALER_NAME", "")
    address = os.getenv("DEALER_ADDRESS", "")
    result = whatsapp.send_test_drive_confirmation(
        to_phone=phone,
        car=car,
        date=date,
        time=time or "To be confirmed",
        customer_name=customer_name,
        dealer_name=dealer_name,
        address=address,
    )

    if result.get("ok"):
        return f"Test drive booked for {date} {time}. Confirmation sent to {phone} on WhatsApp. Let the customer know."
    wa_err = result.get("error", "")
    return f"Test drive booked for {date} {time} but WhatsApp confirmation failed ({wa_err}). Confirm the details verbally with the customer."