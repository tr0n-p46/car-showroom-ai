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

def search_cars(budget=None, model=None, fuel_type=None):
    query = supabase.table("inventory").select("*").eq("status", "available")
    
    if budget:
        budget_inr = _parse_budget_to_inr(budget)
        if budget_inr is not None:
            query = query.lte("price", budget_inr)
    if model:
        # Users often say the make (e.g., "BMW") in the "model" slot.
        # Match make OR model.
        term = str(model).strip()
        if term:
            query = query.or_(f"make.ilike.%{term}%,model.ilike.%{term}%")
    if fuel_type:
        query = query.eq("fuel_type", str(fuel_type).strip().title())
        
    res = query.execute()
    # Fixed line below
    return res.data if res.data else "No cars found matching those criteria."

def create_lead(phone, intent, summary):
    data = {
        "phone_number": phone,
        "intent": intent,
        "requirement_summary": summary
    }
    res = supabase.table("leads").insert(data).execute()
    return "Lead recorded successfully. Tell the user a representative will contact them soon."