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
    query = supabase.table("inventory").select("*")

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